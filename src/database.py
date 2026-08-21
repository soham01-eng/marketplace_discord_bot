"""SQLite persistence for marketplace watches and listing deduplication."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from src.models import Watch


class Database:
    """Own the application's SQLite connection and persistence operations."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)

        self._connection = sqlite3.connect(str(path))
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        """Create the current schema if this is a new database."""
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS watches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_user_id INTEGER NOT NULL,
                query TEXT NOT NULL,
                min_price REAL,
                max_price REAL,
                provider TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                created_at TEXT NOT NULL,
                last_checked TEXT,
                CHECK (min_price IS NULL OR min_price >= 0),
                CHECK (max_price IS NULL OR max_price >= 0),
                CHECK (
                    min_price IS NULL
                    OR max_price IS NULL
                    OR min_price <= max_price
                )
            );

            CREATE TABLE IF NOT EXISTS seen_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                watch_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                external_id TEXT NOT NULL,
                title TEXT NOT NULL,
                price REAL,
                url TEXT NOT NULL,
                image_url TEXT,
                first_seen TEXT NOT NULL,
                FOREIGN KEY (watch_id) REFERENCES watches(id) ON DELETE CASCADE,
                UNIQUE (watch_id, provider, external_id)
            );
            """
        )
        self._connection.commit()

    def create_watch(
        self,
        discord_user_id: int,
        query: str,
        max_price: float | None = None,
        *,
        min_price: float | None = None,
        provider: str = "mock",
    ) -> Watch:
        """Persist a watch and return its complete stored representation."""
        created_at = _utc_now()
        cursor = self._connection.execute(
            """
            INSERT INTO watches (
                discord_user_id,
                query,
                min_price,
                max_price,
                provider,
                enabled,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (
                discord_user_id,
                query,
                min_price,
                max_price,
                provider,
                created_at,
            ),
        )
        self._connection.commit()
        row = self._connection.execute(
            "SELECT * FROM watches WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        if row is None:  # pragma: no cover - SQLite returns the inserted row.
            raise RuntimeError("The newly created watch could not be loaded")
        return _watch_from_row(row)

    def list_watches(self, discord_user_id: int) -> list[Watch]:
        """Return a user's watches in creation order."""
        rows = self._connection.execute(
            """
            SELECT *
            FROM watches
            WHERE discord_user_id = ?
            ORDER BY id
            """,
            (discord_user_id,),
        ).fetchall()
        return [_watch_from_row(row) for row in rows]

    def list_enabled_watches(self) -> list[Watch]:
        """Return every enabled watch in creation order for scanning."""
        rows = self._connection.execute(
            """
            SELECT *
            FROM watches
            WHERE enabled = 1
            ORDER BY id
            """
        ).fetchall()
        return [_watch_from_row(row) for row in rows]

    def update_watch_last_checked(
        self,
        watch_id: int,
        checked_at: str | None = None,
    ) -> bool:
        """Record when a watch was last attempted by the scanner."""
        timestamp = _utc_now() if checked_at is None else checked_at
        cursor = self._connection.execute(
            """
            UPDATE watches
            SET last_checked = ?
            WHERE id = ?
            """,
            (timestamp, watch_id),
        )
        self._connection.commit()
        return cursor.rowcount == 1

    def delete_watch(self, watch_id: int, discord_user_id: int) -> bool:
        """Delete a watch only when it belongs to the requesting Discord user."""
        cursor = self._connection.execute(
            """
            DELETE FROM watches
            WHERE id = ? AND discord_user_id = ?
            """,
            (watch_id, discord_user_id),
        )
        self._connection.commit()
        return cursor.rowcount == 1

    def has_seen_listing(
        self,
        watch_id: int,
        provider: str,
        external_id: str,
    ) -> bool:
        """Report whether a listing has already been recorded for a watch."""
        row = self._connection.execute(
            """
            SELECT 1
            FROM seen_listings
            WHERE watch_id = ? AND provider = ? AND external_id = ?
            """,
            (watch_id, provider, external_id),
        ).fetchone()
        return row is not None

    def save_seen_listing(
        self,
        watch_id: int,
        provider: str,
        external_id: str,
        title: str,
        price: float | None,
        url: str,
        image_url: str | None = None,
    ) -> bool:
        """Record a listing, returning false when it was already seen."""
        cursor = self._connection.execute(
            """
            INSERT INTO seen_listings (
                watch_id,
                provider,
                external_id,
                title,
                price,
                url,
                image_url,
                first_seen
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (watch_id, provider, external_id) DO NOTHING
            """,
            (
                watch_id,
                provider,
                external_id,
                title,
                price,
                url,
                image_url,
                _utc_now(),
            ),
        )
        self._connection.commit()
        return cursor.rowcount == 1

    def close(self) -> None:
        """Close the SQLite connection."""
        self._connection.close()


def _watch_from_row(row: sqlite3.Row) -> Watch:
    """Convert a SQLite watch row to the public data model."""
    return Watch(
        id=row["id"],
        discord_user_id=row["discord_user_id"],
        query=row["query"],
        min_price=row["min_price"],
        max_price=row["max_price"],
        provider=row["provider"],
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
        last_checked=row["last_checked"],
    )


def _utc_now() -> str:
    """Return a sortable, timezone-aware UTC timestamp."""
    return datetime.now(UTC).isoformat()
