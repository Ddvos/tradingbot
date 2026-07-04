"""Runtime configuration — Pydantic Settings at the system boundary.

Values come from environment variables, with `backend/.env` as the local
fallback (copy `.env.example` and fill in). Secrets are `SecretStr` so they
never leak into logs or reprs.
"""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://tradingbot:tradingbot@localhost:5432/tradingbot"
    """SQLAlchemy URL; the default matches docker-compose.yml."""

    walkforward_dir: Path = Path("data/processed/walkforward")
    """Where scripts/walkforward.py writes its run artifacts. Relative to the
    process working directory — backend/, matching how uvicorn is started."""

    kraken_api_key: SecretStr = SecretStr("")
    kraken_api_secret: SecretStr = SecretStr("")
    """Not needed until Slice 5+ (account data / orders) — the charts API is public."""

    cors_origins: list[str] = ["http://localhost:5173"]
    """Frontend origins allowed to call the API (SvelteKit dev server by default)."""
