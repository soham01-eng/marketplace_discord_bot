"""Smoke tests for the Discord command scaffold."""

from discord import app_commands

from src.bot import create_bot
from src.database import Database


def test_bot_registers_planned_commands(tmp_path) -> None:
    """The test guild should contain the complete MVP command surface."""
    database = Database(tmp_path / "commands.db")
    bot = create_bot(guild_id=123456789, database=database)
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
    database.close()
