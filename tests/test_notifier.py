"""Tests for Discord direct-message listing notifications."""

from src.models import Listing, Watch
from src.notifier import DiscordNotifier


class FakeUser:
    """Capture Discord direct messages."""

    def __init__(self) -> None:
        self.messages = []

    async def send(self, *, content, embed) -> None:
        self.messages.append((content, embed))


class FakeClient:
    """Return a cached fake Discord user."""

    def __init__(self, user: FakeUser) -> None:
        self.user = user

    def get_user(self, discord_user_id: int) -> FakeUser:
        assert discord_user_id == 101
        return self.user


async def test_discord_notifier_sends_basic_listing_embed() -> None:
    watch = Watch(
        id=3,
        discord_user_id=101,
        query="office chair",
        min_price=None,
        max_price=150,
        provider="mock",
        enabled=True,
        created_at="2026-08-21T00:00:00+00:00",
        last_checked=None,
    )
    listing = Listing(
        external_id="mock-office-chair",
        title="Herman Miller Office Chair",
        price=125,
        url="https://example.com/listings/mock-office-chair",
        image_url="https://example.com/images/mock-office-chair.jpg",
        source="mock",
    )
    user = FakeUser()
    notifier = DiscordNotifier(FakeClient(user))

    await notifier.notify(101, watch, listing)

    content, embed = user.messages[0]
    assert content == "New marketplace listing found!"
    assert embed.title == "Herman Miller Office Chair"
    assert embed.url == "https://example.com/listings/mock-office-chair"
    assert embed.description == "$125.00"
    assert embed.thumbnail.url == "https://example.com/images/mock-office-chair.jpg"
    assert [field.value for field in embed.fields] == [
        "Mock",
        '#3: "office chair"',
    ]
