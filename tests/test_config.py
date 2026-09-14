"""Tests for environment-based configuration."""

from pathlib import Path

import pytest

from src.config import ConfigurationError, load_search_area, load_settings
from src.geo import SearchArea


def test_load_settings_accepts_valid_values() -> None:
    settings = load_settings(
        {
            "DISCORD_TOKEN": "example-token",
            "DISCORD_GUILD_ID": "123456789",
            "DISCORD_MARKETPLACE_CHANNEL_ID": "987654321",
            "SCAN_INTERVAL_MINUTES": "30",
        }
    )

    assert settings.discord_token == "example-token"
    assert settings.discord_guild_id == 123456789
    assert settings.discord_marketplace_channel_id == 987654321
    assert settings.scan_interval_minutes == 30
    assert settings.database_path == Path("data/marketplace.db")
    assert settings.facebook_marketplace_location == "detroit"
    assert settings.facebook_search_area is None


def test_load_settings_accepts_custom_database_path() -> None:
    settings = load_settings(
        {
            "DISCORD_TOKEN": "example-token",
            "DISCORD_GUILD_ID": "123456789",
            "DISCORD_MARKETPLACE_CHANNEL_ID": "987654321",
            "DATABASE_PATH": "custom/watches.sqlite3",
        }
    )

    assert settings.database_path == Path("custom/watches.sqlite3")


def test_load_settings_accepts_custom_facebook_location() -> None:
    settings = load_settings(
        {
            "DISCORD_TOKEN": "example-token",
            "DISCORD_GUILD_ID": "123456789",
            "DISCORD_MARKETPLACE_CHANNEL_ID": "987654321",
            "FACEBOOK_MARKETPLACE_LOCATION": "Ann-Arbor",
        }
    )

    assert settings.facebook_marketplace_location == "ann-arbor"


def test_radius_settings_are_passed_through_without_discord_secrets() -> None:
    environment = {
        "FACEBOOK_SEARCH_LATITUDE": "42.377",
        "FACEBOOK_SEARCH_LONGITUDE": "-83.0796",
        "FACEBOOK_SEARCH_RADIUS_MILES": "20",
    }
    assert load_search_area(environment) == SearchArea(42.377, -83.0796, 20)
    settings = load_settings(
        {
            **environment,
            "DISCORD_TOKEN": "example-token",
            "DISCORD_GUILD_ID": "123456789",
            "DISCORD_MARKETPLACE_CHANNEL_ID": "987654321",
        }
    )
    assert settings.facebook_search_area == SearchArea(42.377, -83.0796, 20)


def test_blank_radius_settings_preserve_city_only_searches() -> None:
    assert load_search_area({"FACEBOOK_SEARCH_RADIUS_MILES": "  "}) is None


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("FACEBOOK_SEARCH_LATITUDE", ""),
        ("FACEBOOK_SEARCH_LONGITUDE", ""),
        ("FACEBOOK_SEARCH_RADIUS_MILES", ""),
        ("FACEBOOK_SEARCH_LATITUDE", "91"),
        ("FACEBOOK_SEARCH_LONGITUDE", "-181"),
        ("FACEBOOK_SEARCH_RADIUS_MILES", "0"),
        ("FACEBOOK_SEARCH_RADIUS_MILES", "nan"),
        ("FACEBOOK_SEARCH_RADIUS_MILES", "inf"),
        ("FACEBOOK_SEARCH_RADIUS_MILES", "twenty"),
    ],
)
def test_radius_settings_reject_partial_or_invalid_configuration(key, value) -> None:
    environment = {
        "FACEBOOK_SEARCH_LATITUDE": "42.377",
        "FACEBOOK_SEARCH_LONGITUDE": "-83.0796",
        "FACEBOOK_SEARCH_RADIUS_MILES": "20",
        key: value,
    }
    with pytest.raises(ConfigurationError, match="FACEBOOK_SEARCH"):
        load_search_area(environment)


@pytest.mark.parametrize(
    "missing_name",
    [
        "DISCORD_TOKEN",
        "DISCORD_GUILD_ID",
        "DISCORD_MARKETPLACE_CHANNEL_ID",
    ],
)
def test_load_settings_rejects_missing_required_values(missing_name: str) -> None:
    environment = {
        "DISCORD_TOKEN": "example-token",
        "DISCORD_GUILD_ID": "123456789",
        "DISCORD_MARKETPLACE_CHANNEL_ID": "987654321",
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
                "DISCORD_MARKETPLACE_CHANNEL_ID": "987654321",
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
                "DISCORD_MARKETPLACE_CHANNEL_ID": "987654321",
                "FACEBOOK_MARKETPLACE_LOCATION": location,
            }
        )
