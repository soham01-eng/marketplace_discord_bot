"""Tests for SQLite watch persistence and listing deduplication."""

from src.database import Database


def test_watch_crud_persists_across_connections(tmp_path) -> None:
    database_path = tmp_path / "nested" / "marketplace.db"
    database = Database(database_path)

    first_watch = database.create_watch(
        discord_user_id=101,
        query="standing desk",
        max_price=250,
    )
    database.create_watch(
        discord_user_id=202,
        query="desk lamp",
        max_price=40,
    )

    assert first_watch.id > 0
    assert first_watch.query == "standing desk"
    assert first_watch.max_price == 250
    assert first_watch.provider == "mock"
    assert first_watch.enabled is True
    assert first_watch.last_checked is None
    assert [watch.id for watch in database.list_watches(101)] == [first_watch.id]
    database.close()

    reopened_database = Database(database_path)
    assert reopened_database.list_watches(101) == [first_watch]
    assert reopened_database.delete_watch(first_watch.id, discord_user_id=101) is True
    assert reopened_database.list_watches(101) == []
    reopened_database.close()


def test_watch_can_only_be_deleted_by_its_owner(tmp_path) -> None:
    database = Database(tmp_path / "marketplace.db")
    watch = database.create_watch(discord_user_id=101, query="bicycle")

    assert database.delete_watch(watch.id, discord_user_id=202) is False
    assert database.list_watches(101) == [watch]
    database.close()


def test_seen_listing_is_saved_once_per_watch(tmp_path) -> None:
    database = Database(tmp_path / "marketplace.db")
    watch = database.create_watch(discord_user_id=101, query="camera")

    assert database.has_seen_listing(watch.id, "mock", "listing-1") is False
    assert (
        database.save_seen_listing(
            watch_id=watch.id,
            provider="mock",
            external_id="listing-1",
            title="Mirrorless camera",
            price=500,
            url="https://example.com/listings/1",
            image_url="https://example.com/images/1.jpg",
        )
        is True
    )
    assert database.has_seen_listing(watch.id, "mock", "listing-1") is True
    assert (
        database.save_seen_listing(
            watch_id=watch.id,
            provider="mock",
            external_id="listing-1",
            title="Duplicate camera",
            price=450,
            url="https://example.com/listings/1",
        )
        is False
    )
    database.close()


def test_deleting_watch_cascades_to_seen_listings(tmp_path) -> None:
    database = Database(tmp_path / "marketplace.db")
    watch = database.create_watch(discord_user_id=101, query="monitor")
    database.save_seen_listing(
        watch_id=watch.id,
        provider="mock",
        external_id="listing-1",
        title="Ultrawide monitor",
        price=300,
        url="https://example.com/listings/1",
    )

    assert database.delete_watch(watch.id, discord_user_id=101) is True
    assert database.has_seen_listing(watch.id, "mock", "listing-1") is False
    database.close()
