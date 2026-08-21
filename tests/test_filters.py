"""Tests for provider-independent listing filters."""

from dataclasses import replace

from src.filters import matches_watch
from src.models import Listing, Watch


def _watch(**changes) -> Watch:
    watch = Watch(
        id=1,
        discord_user_id=101,
        query="office chair",
        min_price=None,
        max_price=None,
        provider="mock",
        enabled=True,
        created_at="2026-08-21T00:00:00+00:00",
        last_checked=None,
    )
    return replace(watch, **changes)


def _listing(**changes) -> Listing:
    listing = Listing(
        external_id="mock-1",
        title="Herman Miller Office Chair",
        price=125,
        url="https://example.com/listings/1",
        image_url=None,
        source="mock",
    )
    return replace(listing, **changes)


def test_matches_watch_uses_case_insensitive_query_words() -> None:
    assert matches_watch(
        _listing(title="OFFICE desk CHAIR"),
        _watch(query="office chair"),
    )
    assert not matches_watch(_listing(title="Office desk"), _watch())


def test_matches_watch_applies_inclusive_price_bounds() -> None:
    watch = _watch(min_price=100, max_price=150)

    assert matches_watch(_listing(price=100), watch)
    assert matches_watch(_listing(price=150), watch)
    assert not matches_watch(_listing(price=99), watch)
    assert not matches_watch(_listing(price=151), watch)


def test_missing_price_only_matches_without_price_bounds() -> None:
    assert matches_watch(_listing(price=None), _watch())
    assert not matches_watch(_listing(price=None), _watch(max_price=150))
