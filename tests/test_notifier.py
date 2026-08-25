"""Tests for watch-thread creation, routing, recovery, and archiving."""

from src.database import Database
from src.models import Listing
from src.notifier import DiscordNotifier


class FakeThread:
    """Capture messages and archive state for one Discord thread."""

    def __init__(self, thread_id: int, *, archived: bool = False) -> None:
        self.id = thread_id
        self.archived = archived
        self.messages = []
        self.edit_calls = []

    async def send(self, *, content, embed=None) -> None:
        self.archived = False
        self.messages.append((content, embed))

    async def edit(self, *, archived: bool, reason: str) -> None:
        self.archived = archived
        self.edit_calls.append((archived, reason))


class FakeMarketplaceChannel:
    """Create deterministic public threads for tests."""

    def __init__(self, client, first_thread_id: int = 7001) -> None:
        self.client = client
        self.next_thread_id = first_thread_id
        self.create_calls = []

    async def create_thread(self, **kwargs):
        self.create_calls.append(kwargs)
        thread = FakeThread(self.next_thread_id)
        self.next_thread_id += 1
        self.client.channels[thread.id] = thread
        return thread


class FakeClient:
    """Resolve fake channels without connecting to Discord."""

    def __init__(self) -> None:
        self.channels = {}
        self.fetched_ids = []

    def get_channel(self, channel_id: int):
        return self.channels.get(channel_id)

    async def fetch_channel(self, channel_id: int):
        self.fetched_ids.append(channel_id)
        return self.channels.get(channel_id)


def _listing() -> Listing:
    return Listing(
        external_id="mock-office-chair",
        title="Herman Miller Office Chair",
        price=125,
        url="https://example.com/listings/mock-office-chair",
        image_url="https://example.com/images/mock-office-chair.jpg",
        source="mock",
    )


async def test_discord_notifier_creates_thread_and_sends_listing_embed(
    tmp_path,
) -> None:
    database = Database(tmp_path / "notifier.db")
    watch = database.create_watch(
        discord_user_id=101,
        query="office chair",
        max_price=150,
        provider="mock",
    )
    client = FakeClient()
    parent = FakeMarketplaceChannel(client)
    client.channels[5001] = parent
    notifier = DiscordNotifier(client, database, marketplace_channel_id=5001)

    await notifier.notify(101, watch, _listing())

    stored_watch = database.get_watch(watch.id, 101)
    assert stored_watch is not None
    assert stored_watch.discord_thread_id == 7001
    thread = client.channels[7001]
    assert parent.create_calls[0]["name"] == "Watch #1 — office chair"
    assert thread.messages[0][0] == "<@101> created a marketplace watch."
    content, embed = thread.messages[1]
    assert content == "<@101> New marketplace listing found!"
    assert embed.title == "Herman Miller Office Chair"
    assert embed.url == "https://example.com/listings/mock-office-chair"
    assert embed.description == "$125.00"
    assert embed.thumbnail.url == "https://example.com/images/mock-office-chair.jpg"
    assert [field.value for field in embed.fields] == [
        "Mock",
        '#1: "office chair"',
    ]
    database.close()


async def test_discord_notifier_reuses_and_unarchives_existing_thread(tmp_path) -> None:
    database = Database(tmp_path / "notifier.db")
    watch = database.create_watch(101, "desk", provider="mock")
    database.update_watch_thread_id(watch.id, 7001)
    watch = database.get_watch(watch.id, 101)
    assert watch is not None
    client = FakeClient()
    thread = FakeThread(7001, archived=True)
    client.channels[7001] = thread
    notifier = DiscordNotifier(client, database, marketplace_channel_id=5001)

    await notifier.notify(101, watch, _listing())

    assert thread.archived is False
    assert len(thread.messages) == 1
    database.close()


async def test_discord_notifier_recreates_a_missing_thread(tmp_path) -> None:
    database = Database(tmp_path / "notifier.db")
    watch = database.create_watch(101, "desk", provider="mock")
    database.update_watch_thread_id(watch.id, 6999)
    watch = database.get_watch(watch.id, 101)
    assert watch is not None
    client = FakeClient()
    parent = FakeMarketplaceChannel(client, first_thread_id=7002)
    client.channels[5001] = parent
    notifier = DiscordNotifier(client, database, marketplace_channel_id=5001)

    await notifier.notify(101, watch, _listing())

    stored_watch = database.get_watch(watch.id, 101)
    assert stored_watch is not None
    assert stored_watch.discord_thread_id == 7002
    assert client.fetched_ids == [6999]
    database.close()


async def test_discord_notifier_archives_removed_watch_thread(tmp_path) -> None:
    database = Database(tmp_path / "notifier.db")
    watch = database.create_watch(101, "desk", provider="mock")
    database.update_watch_thread_id(watch.id, 7001)
    watch = database.get_watch(watch.id, 101)
    assert watch is not None
    client = FakeClient()
    thread = FakeThread(7001)
    client.channels[7001] = thread
    notifier = DiscordNotifier(client, database, marketplace_channel_id=5001)

    await notifier.archive_watch_thread(watch)

    assert thread.messages[0][0] == f"Watch #{watch.id} was removed."
    assert thread.archived is True
    database.close()
