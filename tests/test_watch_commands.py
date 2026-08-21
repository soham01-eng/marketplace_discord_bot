"""Integration tests for Discord watch commands and SQLite persistence."""

from types import SimpleNamespace

import pytest
from discord import app_commands

from src.bot import create_bot
from src.database import Database


class FakeResponse:
    """Capture an interaction response without connecting to Discord."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, bool]] = []

    async def send_message(self, message: str, *, ephemeral: bool) -> None:
        self.messages.append((message, ephemeral))


class FakeInteraction:
    """Provide the interaction attributes used by watch commands."""

    def __init__(self, user_id: int) -> None:
        self.user = SimpleNamespace(id=user_id)
        self.response = FakeResponse()


@pytest.mark.asyncio
async def test_watch_commands_create_list_and_remove_owned_watch(tmp_path) -> None:
    database = Database(tmp_path / "commands.db")
    bot = create_bot(guild_id=123456789, database=database)
    watch_group = bot.tree.get_command("watch", guild=bot.development_guild)
    assert isinstance(watch_group, app_commands.Group)

    add_command = watch_group.get_command("add")
    list_command = watch_group.get_command("list")
    remove_command = watch_group.get_command("remove")
    assert add_command is not None
    assert list_command is not None
    assert remove_command is not None

    owner_interaction = FakeInteraction(user_id=101)
    await add_command.callback(owner_interaction, "  office chair  ", 125)
    assert owner_interaction.response.messages == [
        ('Saved watch #1 for "office chair" (maximum $125.00, provider: mock).', True)
    ]

    list_interaction = FakeInteraction(user_id=101)
    await list_command.callback(list_interaction)
    assert (
        '#1 — "office chair" — maximum $125.00 — mock'
        in (list_interaction.response.messages[0][0])
    )

    other_user_interaction = FakeInteraction(user_id=202)
    await remove_command.callback(other_user_interaction, 1)
    assert other_user_interaction.response.messages == [
        ("Watch #1 was not found in your watches.", True)
    ]

    remove_interaction = FakeInteraction(user_id=101)
    await remove_command.callback(remove_interaction, 1)
    assert remove_interaction.response.messages == [("Removed watch #1.", True)]
    assert database.list_watches(101) == []
    database.close()
