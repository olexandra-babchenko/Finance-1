"""Application settings loaded from the project's local .env file."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    openrouter_api_key: str
    openrouter_model: str


def get_settings() -> Settings:
    """Return validated settings, failing with an actionable message."""
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    model = os.getenv("OPENROUTER_MODEL", "openrouter/free").strip()

    missing = []
    if not telegram_token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not openrouter_key:
        missing.append("OPENROUTER_API_KEY")
    if not model:
        missing.append("OPENROUTER_MODEL")
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(f"Missing required settings in .env: {names}")

    return Settings(
        telegram_bot_token=telegram_token,
        openrouter_api_key=openrouter_key,
        openrouter_model=model,
    )
