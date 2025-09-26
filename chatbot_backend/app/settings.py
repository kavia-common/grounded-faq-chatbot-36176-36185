import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Load .env if present (local dev). In production, rely on real environment variables.
load_dotenv()

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # OpenAI (RAG path)
    OPENAI_API_KEY: str | None = None
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # Database (RAG path)
    DATABASE_URL: str | None = None

    # RAG
    RAG_TOP_K: int = 4

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8080

    # External APIs
    # OpenWeatherMap API key is not strictly required if you don't use weather questions.
    OPENWEATHERMAP_API_KEY: str | None = None

settings = Settings()

# Simple helper to validate presence of critical secrets at startup
def validate_critical_env():
    missing = []
    if not settings.OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    if not settings.DATABASE_URL:
        missing.append("DATABASE_URL")
    if missing:
        raise RuntimeError(f"Missing required environment variable(s): {', '.join(missing)}")
