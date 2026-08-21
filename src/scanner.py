"""Centralized marketplace scanning workflow."""

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from src.database import Database
from src.filters import matches_watch
from src.models import Listing, Watch
from src.notifier import Notifier
from src.providers import ListingProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ScanResult:
    """Counts produced by one complete scan attempt."""

    watches_scanned: int
    listings_found: int
    new_listings: int
    notifications_sent: int
    failures: int


class Scanner:
    """Scan enabled watches through replaceable listing providers."""

    def __init__(
        self,
        database: Database,
        providers: Mapping[str, ListingProvider],
        notifier: Notifier,
    ) -> None:
        self.database = database
        self.providers = dict(providers)
        self.notifier = notifier
        self.last_started_at: str | None = None
        self.last_finished_at: str | None = None
        self.last_result: ScanResult | None = None
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        """Report whether a manual or scheduled scan currently owns the lock."""
        return self._lock.locked()

    async def scan_watches(self) -> ScanResult:
        """Scan every enabled watch while isolating provider and notification errors."""
        async with self._lock:
            self.last_started_at = _utc_now()
            watches = self.database.list_enabled_watches()
            listings_found = 0
            new_listings = 0
            notifications_sent = 0
            failures = 0
            logger.info("Scan started for %s enabled watches", len(watches))

            for watch in watches:
                try:
                    provider = self._provider_for(watch)
                    listings = await provider.search(watch)
                    listings_found += len(listings)
                    logger.info(
                        "Watch %s returned %s listings from %s",
                        watch.id,
                        len(listings),
                        watch.provider,
                    )
                    for listing in listings:
                        if not matches_watch(listing, watch):
                            continue
                        is_new = self._save_new_listing(watch, listing)
                        if not is_new:
                            continue

                        new_listings += 1
                        try:
                            await self.notifier.notify(
                                watch.discord_user_id,
                                watch,
                                listing,
                            )
                            notifications_sent += 1
                        except Exception:
                            failures += 1
                            logger.exception(
                                "Notification failed for watch %s listing %s",
                                watch.id,
                                listing.external_id,
                            )
                except Exception:
                    failures += 1
                    logger.exception("Scan failed for watch %s", watch.id)
                finally:
                    try:
                        self.database.update_watch_last_checked(watch.id)
                    except Exception:
                        failures += 1
                        logger.exception(
                            "Could not update last-checked time for watch %s",
                            watch.id,
                        )

            result = ScanResult(
                watches_scanned=len(watches),
                listings_found=listings_found,
                new_listings=new_listings,
                notifications_sent=notifications_sent,
                failures=failures,
            )
            self.last_finished_at = _utc_now()
            self.last_result = result
            logger.info(
                "Scan completed: %s new listings, %s notifications, %s failures",
                result.new_listings,
                result.notifications_sent,
                result.failures,
            )
            return result

    def _provider_for(self, watch: Watch) -> ListingProvider:
        """Return the configured provider for a watch or raise a clear error."""
        provider = self.providers.get(watch.provider)
        if provider is None:
            raise LookupError(f"No provider configured for {watch.provider!r}")
        return provider

    def _save_new_listing(self, watch: Watch, listing: Listing) -> bool:
        """Persist a matching listing before any notification is attempted."""
        return self.database.save_seen_listing(
            watch_id=watch.id,
            provider=listing.source,
            external_id=listing.external_id,
            title=listing.title,
            price=listing.price,
            url=listing.url,
            image_url=listing.image_url,
        )


def _utc_now() -> str:
    """Return a timezone-aware timestamp for scanner health reporting."""
    return datetime.now(UTC).isoformat()
