"""Smoke tests for the Discord command scaffold."""

from discord import app_commands

from src.bot import create_bot
from src.database import Database
from src.geo import SearchArea
from src.providers import FacebookProvider, MockProvider


def test_bot_registers_planned_commands(tmp_path) -> None:
    """The test guild should contain the complete MVP command surface."""
    database = Database(tmp_path / "commands.db")
    area = SearchArea(42.377, -83.0796, 20)
    bot = create_bot(
        guild_id=123456789,
        marketplace_channel_id=987654321,
        database=database,
        facebook_search_area=area,
    )
    commands = {
        command.name: command
        for command in bot.tree.get_commands(guild=bot.development_guild)
    }

    assert set(commands) == {"watch", "scan", "status"}
    assert isinstance(commands["watch"], app_commands.Group)
    assert {command.name for command in commands["watch"].commands} == {
        "add",
        "list",
        "remove",
    }
    assert isinstance(bot.scanner.providers["mock"], MockProvider)
    assert isinstance(bot.scanner.providers["facebook"], FacebookProvider)
    assert bot.scanner.providers["facebook"].search_area == area
    assert bot.facebook_search_area == area
    database.close()
