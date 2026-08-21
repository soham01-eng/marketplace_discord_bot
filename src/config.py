"""Environment-based application configuration."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class ConfigurationError(ValueError):
    """Raised when required application configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated settings required to run the bot."""

    discord_token: str
    discord_guild_id: int
    scan_interval_minutes: int
    database_path: Path


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Load and validate settings without exposing secret values."""
    source = os.environ if environ is None else environ

    token = source.get("DISCORD_TOKEN", "").strip()
    if not token:
        raise ConfigurationError("DISCORD_TOKEN is missing from .env")

    guild_id = _positive_integer(source.get("DISCORD_GUILD_ID"), "DISCORD_GUILD_ID")
    interval = _positive_integer(
        source.get("SCAN_INTERVAL_MINUTES", "30"),
        "SCAN_INTERVAL_MINUTES",
    )
    if not 15 <= interval <= 45:
        raise ConfigurationError("SCAN_INTERVAL_MINUTES must be between 15 and 45")

    raw_database_path = source.get("DATABASE_PATH", "data/marketplace.db").strip()
    if not raw_database_path:
        raise ConfigurationError("DATABASE_PATH cannot be empty")

    return Settings(
        discord_token=token,
        discord_guild_id=guild_id,
        scan_interval_minutes=interval,
        database_path=Path(raw_database_path),
    )


def _positive_integer(raw_value: str | None, setting_name: str) -> int:
    """Convert a setting to a positive integer with a safe error message."""
    if raw_value is None or not raw_value.strip():
        raise ConfigurationError(f"{setting_name} is missing from .env")

    try:
        value = int(raw_value)
    except ValueError as error:
        raise ConfigurationError(f"{setting_name} must be a whole number") from error

    if value <= 0:
        raise ConfigurationError(f"{setting_name} must be greater than zero")
    return value
