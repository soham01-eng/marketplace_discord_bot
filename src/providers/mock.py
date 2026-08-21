"""Deterministic local listing provider for development and demos."""

import json
from collections.abc import Mapping
from pathlib import Path

from src.models import Listing, Watch
from src.providers.base import ListingProvider

_DEFAULT_LISTINGS_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "sample_listings.json"
)


class MockProvider(ListingProvider):
    """Load predictable listings from JSON without using the network."""

    source = "mock"

    def __init__(self, listings_path: str | Path | None = None) -> None:
        self.listings_path = (
            Path(listings_path) if listings_path is not None else _DEFAULT_LISTINGS_PATH
        )

    async def search(self, watch: Watch) -> list[Listing]:
        """Return normalized fixture listings matching every query word."""
        raw_records = json.loads(self.listings_path.read_text(encoding="utf-8"))
        if not isinstance(raw_records, list):
            raise ValueError("Mock listing data must contain a JSON list")

        listings = [_normalize_listing(record) for record in raw_records]
        query_words = watch.query.casefold().split()
        return [
            listing
            for listing in listings
            if all(word in listing.title.casefold() for word in query_words)
        ]


def _normalize_listing(record: object) -> Listing:
    """Convert one JSON record into the provider-independent model."""
    if not isinstance(record, Mapping):
        raise ValueError("Each mock listing must be a JSON object")

    return Listing(
        external_id=_required_text(record, "external_id"),
        title=_required_text(record, "title"),
        price=_optional_price(record.get("price")),
        url=_required_text(record, "url"),
        image_url=_optional_text(record.get("image_url")),
        source=MockProvider.source,
    )


def _required_text(record: Mapping[object, object], field: str) -> str:
    """Read a required, non-empty text field from a mock record."""
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Mock listing field {field!r} must be non-empty text")
    return value.strip()


def _optional_text(value: object) -> str | None:
    """Normalize an optional text field, treating blank text as missing."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Optional mock listing text must be a string or null")
    return value.strip() or None


def _optional_price(value: object) -> float | None:
    """Normalize an optional numeric price."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("Mock listing price must be a number or null")
    return float(value)
