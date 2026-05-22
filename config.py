"""
Configuration loader for MonsterLab ClipIt Telegram auto-submit bot.

Loads settings from environment variables (via .env file) and validates
that all required values are present and correctly formatted.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    """Immutable application configuration.

    Attributes:
        telegram_bot_token: Telegram Bot API token from @BotFather.
        monsterlab_api_key: MonsterLab API key (format: ml_xxxxx).
        monsterlab_base_url: Base URL for the MonsterLab API.
        authorized_user_id: Telegram user ID authorized to use the bot.
        db_path: Path to the SQLite database file.
        max_requests_per_minute: Rate limit — requests per minute (conservative).
        max_requests_per_hour: Rate limit — requests per hour (conservative).
        min_interval_seconds: Minimum seconds between consecutive submissions.
    """

    telegram_bot_token: str
    monsterlab_api_key: str
    monsterlab_base_url: str
    authorized_user_id: int
    db_path: str
    max_requests_per_minute: int
    max_requests_per_hour: int
    min_interval_seconds: int


class ConfigError(Exception):
    """Raised when a required configuration value is missing or invalid."""


def load_config(env_path: str | Path | None = None) -> Config:
    """Load and validate configuration from environment variables.

    Args:
        env_path: Optional explicit path to a ``.env`` file.
                  Defaults to ``.env`` in the current working directory.

    Returns:
        A validated :class:`Config` instance.

    Raises:
        ConfigError: If a required variable is missing or has an invalid format.
    """
    load_dotenv(dotenv_path=env_path)

    missing: list[str] = []

    # --- Required values ---------------------------------------------------
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not telegram_bot_token:
        missing.append("TELEGRAM_BOT_TOKEN")

    monsterlab_api_key = os.getenv("MONSTERLAB_API_KEY", "").strip()
    if not monsterlab_api_key:
        missing.append("MONSTERLAB_API_KEY")
    elif not monsterlab_api_key.startswith("ml_"):
        raise ConfigError(
            "MONSTERLAB_API_KEY must start with 'ml_' "
            f"(got '{monsterlab_api_key[:6]}…')"
        )

    authorized_user_id_raw = os.getenv("AUTHORIZED_USER_ID", "").strip()
    if not authorized_user_id_raw:
        missing.append("AUTHORIZED_USER_ID")

    if missing:
        raise ConfigError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + ". Copy .env.example to .env and fill in the values."
        )

    try:
        authorized_user_id = int(authorized_user_id_raw)
    except ValueError as exc:
        raise ConfigError(
            f"AUTHORIZED_USER_ID must be an integer, got '{authorized_user_id_raw}'"
        ) from exc

    # --- Optional values with defaults -------------------------------------
    monsterlab_base_url = os.getenv(
        "MONSTERLAB_BASE_URL", "https://monsterlab.io"
    ).strip().rstrip("/")

    db_path = os.getenv("DB_PATH", "submissions.db").strip()

    max_requests_per_minute = _parse_int_env(
        "MAX_REQUESTS_PER_MINUTE", default=80
    )
    max_requests_per_hour = _parse_int_env(
        "MAX_REQUESTS_PER_HOUR", default=5000
    )
    min_interval_seconds = _parse_int_env(
        "MIN_INTERVAL_SECONDS", default=2
    )

    return Config(
        telegram_bot_token=telegram_bot_token,
        monsterlab_api_key=monsterlab_api_key,
        monsterlab_base_url=monsterlab_base_url,
        authorized_user_id=authorized_user_id,
        db_path=db_path,
        max_requests_per_minute=max_requests_per_minute,
        max_requests_per_hour=max_requests_per_hour,
        min_interval_seconds=min_interval_seconds,
    )


def _parse_int_env(name: str, *, default: int) -> int:
    """Return an integer env var or *default*, raising on bad format."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(
            f"{name} must be an integer, got '{raw}'"
        ) from exc
