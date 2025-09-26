from typing import Any, AsyncGenerator, Dict, List, Optional
import json
import re
import os

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .settings import settings, validate_critical_env

# Initialize FastAPI with OpenAPI metadata
app = FastAPI(
    title="Ocean Chat Backend",
    description=(
        "FastAPI backend for a RAG chatbot with streaming NDJSON responses. "
        "Includes special handling for current weather queries using OpenWeatherMap."
    ),
    version="1.0.0",
    openapi_tags=[
        {
            "name": "chat",
            "description": "Chat endpoints providing streaming NDJSON responses.",
        },
        {
            "name": "realtime",
            "description": "Notes and usage information for any streaming connections.",
        },
    ],
)

# Validate critical env (excluding DB for this minimal example; RAG path can validate separately)
try:
    # We keep OPENAI/DATABASE validation optional to not block weather-only flows in this step.
    # validate_critical_env()
    pass
except RuntimeError as exc:
    # Expose in logs but do not crash app in this task scope.
    print(f"[WARN] Environment validation: {exc}")


class Message(BaseModel):
    role: str = Field(..., description="Role of the message author: user or assistant.")
    content: str = Field(..., description="Message content text.")


class AskRequest(BaseModel):
    prompt: str = Field(..., description="User's new question/prompt.")
    history: Optional[List[Message]] = Field(
        default=None, description="Optional chat history."
    )


class NDJSONChunk(BaseModel):
    type: str = Field(..., description="Chunk type: start | token | refs | done | error")
    value: Optional[Any] = Field(default=None, description="Payload for the chunk.")
    messageId: Optional[str] = Field(
        default=None, description="Optional message id carried on start chunk."
    )


# ---- Weather detection and OpenWeatherMap client ----

WEATHER_REGEX = re.compile(
    r"\b(?:weather|temperature|temp|forecast)\b(?:.*\b(in|at)\b\s+([\\w\\s\\-\\.]+))?",
    flags=re.IGNORECASE,
)

CITY_FROM_TODAY_REGEX = re.compile(
    r"\b(?:today|current|now)\b.*\bweather\b.*\b(in|at)\b\s+([\\w\\s\\-\\.]+)",
    flags=re.IGNORECASE,
)


def _normalize_city(value: str) -> str:
    """Normalize extracted city name."""
    value = value.strip(" .,!?:;\"'()[]{}")
    # Capitalize each word
    return " ".join(w.capitalize() for w in value.split())


async def fetch_openweather_current(city: str) -> Dict[str, Any]:
    """
    Fetch current weather for a city using OpenWeatherMap Current Weather Data API.
    Uses environment variable OPENWEATHERMAP_API_KEY for authentication.
    """
    api_key = os.getenv("OPENWEATHERMAP_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="Weather API not configured. Missing OPENWEATHERMAP_API_KEY.",
        )

    # API docs: https://openweathermap.org/current
    # Example endpoint: https://api.openweathermap.org/data/2.5/weather?q=Pune&appid=API_KEY&units=metric
    params = {"q": city, "appid": api_key, "units": "metric"}
    url = "https://api.openweathermap.org/data/2.5/weather"

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params)
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"City not found: {city}")
        if resp.status_code != 200:
            try:
                j = resp.json()
            except Exception:
                j = {"error": resp.text}
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"OpenWeatherMap error: {j}",
            )
        data = resp.json()
        # Narrow useful fields
        main = data.get("main", {})
        weather = (data.get("weather") or [{}])[0]
        wind = data.get("wind", {})
        sys = data.get("sys", {})
        name = data.get("name") or city
        result = {
            "city": name,
            "country": sys.get("country"),
            "description": weather.get("description"),
            "temperature_c": main.get("temp"),
            "feels_like_c": main.get("feels_like"),
            "humidity_pct": main.get("humidity"),
            "pressure_hpa": main.get("pressure"),
            "wind_speed_ms": wind.get("speed"),
            "wind_deg": wind.get("deg"),
            "source": "openweathermap",
        }
        return result


def detect_weather_city(prompt: str) -> Optional[str]:
    """
    Detect if the user's prompt asks for current weather in a city.
    Returns normalized city name if detected, otherwise None.
    """
    # Stronger pattern: "today/current/now weather in X"
    m2 = CITY_FROM_TODAY_REGEX.search(prompt)
    if m2 and m2.lastindex and m2.group(2):
        return _normalize_city(m2.group(2))

    # Generic 'weather ... in X' or 'forecast ... at X'
    m = WEATHER_REGEX.search(prompt)
    if m and m.lastindex and m.group(2):
        return _normalize_city(m.group(2))

    return None


async def ndjson_weather_stream(city: str) -> AsyncGenerator[bytes, None]:
    """
    Stream NDJSON response for a weather question.
    Order: start -> token(s) -> refs -> done
    """
    # start
    yield (NDJSONChunk(type="start", messageId=None).model_dump_json() + "\n").encode()

    try:
        data = await fetch_openweather_current(city)
    except HTTPException as he:
        err = NDJSONChunk(type="error", value=he.detail)
        yield (err.model_dump_json() + "\n").encode()
        return
    except Exception as e:
        err = NDJSONChunk(type="error", value=str(e))
        yield (err.model_dump_json() + "\n").encode()
        return

    # Create a concise message in a couple tokens
    # token 1: header
    header = f"Current weather in {data.get('city')}, {data.get('country') or ''}: "
    yield (NDJSONChunk(type="token", value=header).model_dump_json() + "\n").encode()

    # token 2: details
    temp = data.get("temperature_c")
    desc = data.get("description")
    feels = data.get("feels_like_c")
    hum = data.get("humidity_pct")
    wind = data.get("wind_speed_ms")
    details_parts = []
    if desc:
        details_parts.append(desc)
    if temp is not None:
        details_parts.append(f"{temp}°C")
    if feels is not None:
        details_parts.append(f"feels like {feels}°C")
    if hum is not None:
        details_parts.append(f"humidity {hum}%")
    if wind is not None:
        details_parts.append(f"wind {wind} m/s")
    details = ", ".join(details_parts) if details_parts else "no details"
    yield (NDJSONChunk(type="token", value=details + ". ").model_dump_json() + "\n").encode()

    # refs
    refs = [
        {
            "title": "OpenWeatherMap - Current Weather Data",
            "url": "https://openweathermap.org/current",
            "snippet": "Live current weather information provided by OpenWeatherMap.",
        }
    ]
    yield (NDJSONChunk(type="refs", value=refs).model_dump_json() + "\n").encode()

    # done
    yield (NDJSONChunk(type="done").model_dump_json() + "\n").encode()


# PUBLIC_INTERFACE
@app.post(
    "/api/ask",
    summary="Ask a question (streaming NDJSON)",
    description=(
        "Accepts a chat question and streams back NDJSON chunks. "
        "If the question is about current weather in a city (e.g., 'today's weather in Pune'), "
        "the backend calls OpenWeatherMap and streams a live answer."
    ),
    tags=["chat"],
    responses={
        200: {"description": "NDJSON streaming response."},
        400: {"description": "Invalid request."},
        500: {"description": "Internal server error."},
    },
)
async def ask(req: AskRequest):
    """
    Handle a chat question with streaming NDJSON response.

    Request body:
    - prompt: The user's question.
    - history: Optional prior messages.

    Returns:
    - A StreamingResponse with content-type application/x-ndjson. Chunks include:
      { "type": "start" }
      { "type": "token", "value": "..." }
      { "type": "refs", "value": [ ... ] }
      { "type": "done" }
      or on error:
      { "type": "error", "error": "..." }

    Notes:
    - Weather questions trigger OpenWeatherMap lookup using OPENWEATHERMAP_API_KEY.
    """
    prompt = (req.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Empty prompt.")

    city = detect_weather_city(prompt)
    if city:
        generator = ndjson_weather_stream(city)
        return StreamingResponse(generator, media_type="application/x-ndjson")

    # Fallback demo behavior for non-weather prompts: return simple streaming stub
    async def demo_stream() -> AsyncGenerator[bytes, None]:
        yield (NDJSONChunk(type="start").model_dump_json() + "\n").encode()
        yield (NDJSONChunk(type="token", value="I'm a demo response for non-weather queries. ").model_dump_json() + "\n").encode()
        yield (
            NDJSONChunk(
                type="refs",
                value=[
                    {
                        "title": "FAQ Docs",
                        "url": "https://example.com/docs",
                        "snippet": "Placeholder reference for demo path.",
                    }
                ],
            ).model_dump_json()
            + "\n"
        ).encode()
        yield (NDJSONChunk(type="done").model_dump_json() + "\n").encode()

    return StreamingResponse(demo_stream(), media_type="application/x-ndjson")


# PUBLIC_INTERFACE
@app.get(
    "/api/realtime-info",
    summary="Realtime connection usage notes",
    description="Provides usage notes for NDJSON streaming and any realtime connections.",
    tags=["realtime"],
    responses={200: {"description": "Usage notes."}},
)
def realtime_info() -> Dict[str, str]:
    """
    Return informational notes about streaming NDJSON usage and websocket hints.
    """
    return {
        "ndjson": "POST /api/ask streams NDJSON with chunks: start, token, refs, done (or error).",
        "websocket": "No websocket endpoints in this demo; use HTTP streaming.",
    }
