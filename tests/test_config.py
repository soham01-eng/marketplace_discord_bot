"""Tests for environment-based configuration."""

from pathlib import Path

import pytest

from src.config import ConfigurationError, load_settings


def test_load_settings_accepts_valid_values() -> None:
    settings = load_settings(
        {
            "DISCORD_TOKEN": "example-token",
            "DISCORD_GUILD_ID": "123456789",
            "SCAN_INTERVAL_MINUTES": "30",
        }
    )

    assert settings.discord_token == "example-token"
    assert settings.discord_guild_id == 123456789
    assert settings.scan_interval_minutes == 30
    assert settings.database_path == Path("data/marketplace.db")
    assert settings.facebook_marketplace_location == "detroit"


def test_load_settings_accepts_custom_database_path() -> None:
    settings = load_settings(
        {
            "DISCORD_TOKEN": "example-token",
            "DISCORD_GUILD_ID": "123456789",
            "DATABASE_PATH": "custom/watches.sqlite3",
        }
    )

    assert settings.database_path == Path("custom/watches.sqlite3")


def test_load_settings_accepts_custom_facebook_location() -> None:
    settings = load_settings(
        {
            "DISCORD_TOKEN": "example-token",
            "DISCORD_GUILD_ID": "123456789",
            "FACEBOOK_MARKETPLACE_LOCATION": "Ann-Arbor",
        }
    )

    assert settings.facebook_marketplace_location == "ann-arbor"


@pytest.mark.parametrize("missing_name", ["DISCORD_TOKEN", "DISCORD_GUILD_ID"])
def test_load_settings_rejects_missing_required_values(missing_name: str) -> None:
    environment = {
        "DISCORD_TOKEN": "example-token",
        "DISCORD_GUILD_ID": "123456789",
    }
    environment.pop(missing_name)

    with pytest.raises(ConfigurationError, match=missing_name):
        load_settings(environment)


@pytest.mark.parametrize("interval", ["14", "46", "not-a-number"])
def test_load_settings_rejects_invalid_scan_intervals(interval: str) -> None:
    with pytest.raises(ConfigurationError, match="SCAN_INTERVAL_MINUTES"):
        load_settings(
            {
                "DISCORD_TOKEN": "example-token",
                "DISCORD_GUILD_ID": "123456789",
                "SCAN_INTERVAL_MINUTES": interval,
            }
        )


@pytest.mark.parametrize("location", ["", "detroit/mi", "detroit michigan"])
def test_load_settings_rejects_invalid_facebook_location(location: str) -> None:
    with pytest.raises(ConfigurationError, match="FACEBOOK_MARKETPLACE_LOCATION"):
        load_settings(
            {
                "DISCORD_TOKEN": "example-token",
                "DISCORD_GUILD_ID": "123456789",
                "FACEBOOK_MARKETPLACE_LOCATION": location,
            }
        )
