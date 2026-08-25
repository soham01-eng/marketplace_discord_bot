"""Integration tests for Discord watch commands and SQLite persistence."""

from types import SimpleNamespace

import pytest
from discord import app_commands

from src.bot import create_bot
from src.database import Database


class FakeResponse:
    """Capture immediate and deferred interaction responses."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, bool]] = []
        self.deferred = False

    async def send_message(self, message: str, *, ephemeral: bool) -> None:
        self.messages.append((message, ephemeral))

    async def defer(self, *, ephemeral: bool, thinking: bool) -> None:
        self.deferred = ephemeral and thinking


class FakeFollowup:
    """Capture follow-ups sent after thread creation."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, bool]] = []

    async def send(self, message: str, *, ephemeral: bool) -> None:
        self.messages.append((message, ephemeral))


class FakeInteraction:
    """Provide the interaction attributes used by watch commands."""

    def __init__(self, user_id: int) -> None:
        self.user = SimpleNamespace(id=user_id)
        self.response = FakeResponse()
        self.followup = FakeFollowup()


class FakeThread:
    """Capture watch setup, listing, and archive operations."""

    def __init__(self, thread_id: int) -> None:
        self.id = thread_id
        self.messages = []
        self.archived = False

    async def send(self, *, content, embed=None) -> None:
        self.messages.append((content, embed))

    async def edit(self, *, archived: bool, reason: str) -> None:
        self.archived = archived


class FakeMarketplaceChannel:
    """Create one fake watch thread."""

    def __init__(self, thread: FakeThread) -> None:
        self.thread = thread

    async def create_thread(self, **kwargs):
        return self.thread


class FailingMarketplaceChannel:
    """Simulate a missing Discord thread permission."""

    async def create_thread(self, **kwargs):
        raise RuntimeError("Missing Create Public Threads permission")


def _configure_channels(monkeypatch, bot, parent, thread) -> None:
    channels = {
        bot.marketplace_channel_id: parent,
        thread.id: thread,
    }
    monkeypatch.setattr(bot, "get_channel", channels.get)


@pytest.mark.asyncio
async def test_watch_commands_create_list_and_remove_owned_watch(
    tmp_path,
    monkeypatch,
) -> None:
    database = Database(tmp_path / "commands.db")
    bot = create_bot(
        guild_id=123456789,
        marketplace_channel_id=987654321,
        database=database,
    )
    thread = FakeThread(7001)
    parent = FakeMarketplaceChannel(thread)
    _configure_channels(monkeypatch, bot, parent, thread)
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
    assert owner_interaction.response.deferred is True
    assert owner_interaction.followup.messages == [
        (
            'Saved watch #1 for "office chair" '
            "(maximum $125.00, provider: facebook). Alerts: <#7001>",
            True,
        )
    ]

    list_interaction = FakeInteraction(user_id=101)
    await list_command.callback(list_interaction)
    assert (
        '#1 — "office chair" — maximum $125.00 — facebook'
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
    assert thread.archived is True
    assert database.list_watches(101) == []
    database.close()


@pytest.mark.asyncio
async def test_watch_add_accepts_explicit_mock_provider(
    tmp_path,
    monkeypatch,
) -> None:
    database = Database(tmp_path / "commands.db")
    bot = create_bot(
        guild_id=123456789,
        marketplace_channel_id=987654321,
        database=database,
    )
    thread = FakeThread(7001)
    _configure_channels(monkeypatch, bot, FakeMarketplaceChannel(thread), thread)
    watch_group = bot.tree.get_command("watch", guild=bot.development_guild)
    assert isinstance(watch_group, app_commands.Group)
    add_command = watch_group.get_command("add")
    assert add_command is not None

    interaction = FakeInteraction(user_id=101)
    await add_command.callback(interaction, "office chair", 150, "mock")

    assert "provider: mock" in interaction.followup.messages[0][0]
    assert database.list_watches(101)[0].provider == "mock"
    database.close()


@pytest.mark.asyncio
async def test_watch_add_rolls_back_when_thread_creation_fails(
    tmp_path,
    monkeypatch,
) -> None:
    database = Database(tmp_path / "commands.db")
    bot = create_bot(
        guild_id=123456789,
        marketplace_channel_id=987654321,
        database=database,
    )
    monkeypatch.setattr(
        bot,
        "get_channel",
        lambda channel_id: FailingMarketplaceChannel(),
    )
    watch_group = bot.tree.get_command("watch", guild=bot.development_guild)
    assert isinstance(watch_group, app_commands.Group)
    add_command = watch_group.get_command("add")
    assert add_command is not None

    interaction = FakeInteraction(user_id=101)
    await add_command.callback(interaction, "office chair", 150)

    assert interaction.response.deferred is True
    assert "alert thread could not be created" in interaction.followup.messages[0][0]
    assert database.list_watches(101) == []
    database.close()
