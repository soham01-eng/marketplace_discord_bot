"""Tests for SQLite watch persistence and listing deduplication."""

import sqlite3

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
    assert first_watch.provider == "facebook"
    assert first_watch.discord_thread_id is None
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


def test_watch_thread_is_persisted_and_respects_ownership(tmp_path) -> None:
    database = Database(tmp_path / "marketplace.db")
    watch = database.create_watch(discord_user_id=101, query="bicycle")

    assert database.get_watch(watch.id, discord_user_id=202) is None
    assert database.update_watch_thread_id(watch.id, 987654321)
    stored_watch = database.get_watch(watch.id, discord_user_id=101)

    assert stored_watch is not None
    assert stored_watch.discord_thread_id == 987654321
    database.close()


def test_existing_database_is_migrated_without_losing_watches(tmp_path) -> None:
    database_path = tmp_path / "existing.db"
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE watches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_user_id INTEGER NOT NULL,
            query TEXT NOT NULL,
            min_price REAL,
            max_price REAL,
            provider TEXT NOT NULL,
            enabled INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            last_checked TEXT
        )
        """
    )
    connection.execute(
        """
        INSERT INTO watches (
            discord_user_id,
            query,
            provider,
            enabled,
            created_at
        )
        VALUES (101, 'office chair', 'mock', 1, '2026-08-21T00:00:00+00:00')
        """
    )
    connection.commit()
    connection.close()

    database = Database(database_path)
    watches = database.list_watches(101)

    assert len(watches) == 1
    assert watches[0].query == "office chair"
    assert watches[0].discord_thread_id is None
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


def test_enabled_watches_and_last_checked_support_scanning(tmp_path) -> None:
    database = Database(tmp_path / "marketplace.db")
    watch = database.create_watch(discord_user_id=101, query="monitor")

    assert database.list_enabled_watches() == [watch]
    assert database.update_watch_last_checked(
        watch.id,
        checked_at="2026-08-21T12:00:00+00:00",
    )
    assert database.list_enabled_watches()[0].last_checked == (
        "2026-08-21T12:00:00+00:00"
    )
    database.close()
