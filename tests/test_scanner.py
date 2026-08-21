"""Tests for scanning, deduplication, notification, and failure isolation."""

from src.database import Database
from src.models import Listing, Watch
from src.providers import ListingProvider
from src.scanner import Scanner


class FakeProvider(ListingProvider):
    """Return configured listings or a configured error."""

    def __init__(
        self,
        listings: list[Listing] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.listings = listings or []
        self.error = error
        self.calls: list[Watch] = []

    async def search(self, watch: Watch) -> list[Listing]:
        self.calls.append(watch)
        if self.error is not None:
            raise self.error
        return self.listings


class FakeNotifier:
    """Capture notifications or simulate a delivery failure."""

    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.notifications: list[tuple[int, Watch, Listing]] = []

    async def notify(
        self,
        discord_user_id: int,
        watch: Watch,
        listing: Listing,
    ) -> None:
        if self.should_fail:
            raise RuntimeError("Discord unavailable")
        self.notifications.append((discord_user_id, watch, listing))


def _listing(
    external_id: str = "mock-office-chair",
    *,
    title: str = "Herman Miller Office Chair",
    price: float | None = 125,
) -> Listing:
    return Listing(
        external_id=external_id,
        title=title,
        price=price,
        url=f"https://example.com/listings/{external_id}",
        image_url=None,
        source="mock",
    )


async def test_scanner_notifies_once_and_updates_last_checked(tmp_path) -> None:
    database = Database(tmp_path / "scanner.db")
    watch = database.create_watch(101, "office chair", max_price=150)
    provider = FakeProvider(
        [
            _listing(),
            _listing("mock-expensive-chair", price=500),
        ]
    )
    notifier = FakeNotifier()
    scanner = Scanner(database, {"mock": provider}, notifier)

    first_result = await scanner.scan_watches()
    second_result = await scanner.scan_watches()

    assert first_result.watches_scanned == 1
    assert first_result.listings_found == 2
    assert first_result.new_listings == 1
    assert first_result.notifications_sent == 1
    assert first_result.failures == 0
    assert second_result.new_listings == 0
    assert second_result.notifications_sent == 0
    assert len(notifier.notifications) == 1
    assert database.has_seen_listing(watch.id, "mock", "mock-office-chair")
    assert not database.has_seen_listing(watch.id, "mock", "mock-expensive-chair")
    assert database.list_watches(101)[0].last_checked is not None
    database.close()


async def test_provider_failure_does_not_stop_other_watches(tmp_path) -> None:
    database = Database(tmp_path / "scanner.db")
    failed_watch = database.create_watch(101, "camera", provider="broken")
    working_watch = database.create_watch(202, "desk lamp", provider="working")
    failing_provider = FakeProvider(error=RuntimeError("Provider unavailable"))
    working_provider = FakeProvider(
        [_listing("mock-desk-lamp", title="Vintage Desk Lamp", price=None)]
    )
    notifier = FakeNotifier()
    scanner = Scanner(
        database,
        {"broken": failing_provider, "working": working_provider},
        notifier,
    )

    result = await scanner.scan_watches()

    assert result.watches_scanned == 2
    assert result.new_listings == 1
    assert result.notifications_sent == 1
    assert result.failures == 1
    assert len(notifier.notifications) == 1
    assert database.list_watches(101)[0].last_checked is not None
    assert database.list_watches(202)[0].last_checked is not None
    assert failing_provider.calls[0].id == failed_watch.id
    assert working_provider.calls[0].id == working_watch.id
    database.close()


async def test_listing_is_saved_before_failed_notification(tmp_path) -> None:
    database = Database(tmp_path / "scanner.db")
    watch = database.create_watch(101, "office chair")
    scanner = Scanner(
        database,
        {"mock": FakeProvider([_listing()])},
        FakeNotifier(should_fail=True),
    )

    first_result = await scanner.scan_watches()
    second_result = await scanner.scan_watches()

    assert first_result.new_listings == 1
    assert first_result.notifications_sent == 0
    assert first_result.failures == 1
    assert second_result.new_listings == 0
    assert second_result.failures == 0
    assert database.has_seen_listing(watch.id, "mock", "mock-office-chair")
    database.close()
