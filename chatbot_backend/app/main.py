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
    Return a mocked/demo current weather response for a given city.

    This stubs the live API and returns realistic, static sample data in the
    same shape as the expected processed output. A `mocked` flag and source note
    are included so consumers know this is demo data.
    """
    normalized = _normalize_city(city)
    # Simple, realistic mock set for some known cities; default fallback otherwise.
    mock_catalog: Dict[str, Dict[str, Any]] = {
        "Pune": {
            "city": "Pune",
            "country": "IN",
            "description": "clear sky",
            "temperature_c": 29.0,
            "feels_like_c": 30.0,
            "humidity_pct": 48,
            "pressure_hpa": 1012,
            "wind_speed_ms": 3.2,
            "wind_deg": 110,
        },
        "San Francisco": {
            "city": "San Francisco",
            "country": "US",
            "description": "light drizzle",
            "temperature_c": 16.0,
            "feels_like_c": 15.0,
            "humidity_pct": 82,
            "pressure_hpa": 1015,
            "wind_speed_ms": 5.5,
            "wind_deg": 240,
        },
        "London": {
            "city": "London",
            "country": "GB",
            "description": "broken clouds",
            "temperature_c": 18.0,
            "feels_like_c": 17.0,
            "humidity_pct": 65,
            "pressure_hpa": 1018,
            "wind_speed_ms": 4.0,
            "wind_deg": 200,
        },
        "New York": {
            "city": "New York",
            "country": "US",
            "description": "overcast clouds",
            "temperature_c": 22.0,
            "feels_like_c": 22.0,
            "humidity_pct": 60,
            "pressure_hpa": 1013,
            "wind_speed_ms": 3.8,
            "wind_deg": 180,
        },
    }

    data = mock_catalog.get(normalized) or {
        "city": normalized,
        "country": None,
        "description": "partly cloudy",
        "temperature_c": 24.0,
        "feels_like_c": 25.0,
        "humidity_pct": 55,
        "pressure_hpa": 1014,
        "wind_speed_ms": 3.0,
        "wind_deg": 135,
    }

    # Add metadata marking as mocked
    data["source"] = "mocked-openweathermap"
    data["mocked"] = True
    return data


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
    mocked_note = " [mocked demo data]" if data.get("mocked") else ""
    yield (NDJSONChunk(type="token", value=details + "." + mocked_note + " ").model_dump_json() + "\n").encode()

    # refs
    refs = [
        {
            "title": "OpenWeatherMap - Current Weather Data",
            "url": "https://openweathermap.org/current",
            "snippet": "This answer uses mocked/demo weather data shaped like OpenWeatherMap output.",
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
        "the backend returns realistic mocked/demo data shaped like OpenWeatherMap output."
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
    - Weather questions return mocked/demo weather data; no external API is called.
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
