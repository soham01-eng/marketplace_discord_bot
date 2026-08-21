"""Tests for the normalized provider contract and local mock provider."""

import json

import pytest

from src.models import Listing, Watch
from src.providers import ListingProvider, MockProvider


def _watch(query: str) -> Watch:
    return Watch(
        id=1,
        discord_user_id=101,
        query=query,
        min_price=None,
        max_price=None,
        provider="mock",
        enabled=True,
        created_at="2026-08-21T00:00:00+00:00",
        last_checked=None,
    )


@pytest.mark.asyncio
async def test_mock_provider_returns_deterministic_normalized_listings() -> None:
    provider: ListingProvider = MockProvider()

    first_result = await provider.search(_watch("office chair"))
    second_result = await provider.search(_watch("OFFICE CHAIR"))

    assert first_result == second_result
    assert first_result == [
        Listing(
            external_id="mock-1003",
            title="Herman Miller Office Chair",
            price=125.0,
            url="https://example.com/listings/mock-1003",
            image_url=None,
            source="mock",
        )
    ]


@pytest.mark.asyncio
async def test_mock_provider_handles_missing_optional_fields(tmp_path) -> None:
    listings_path = tmp_path / "listings.json"
    listings_path.write_text(
        json.dumps(
            [
                {
                    "external_id": "mock-missing-fields",
                    "title": "Desk Lamp",
                    "url": "https://example.com/listings/missing-fields",
                }
            ]
        ),
        encoding="utf-8",
    )

    listings = await MockProvider(listings_path).search(_watch("desk"))

    assert listings[0].price is None
    assert listings[0].image_url is None


@pytest.mark.asyncio
async def test_mock_provider_returns_empty_list_for_unmatched_query() -> None:
    listings = await MockProvider().search(_watch("mountain bicycle"))

    assert listings == []


@pytest.mark.asyncio
async def test_mock_provider_rejects_non_list_fixture(tmp_path) -> None:
    listings_path = tmp_path / "listings.json"
    listings_path.write_text('{"title": "not a list"}', encoding="utf-8")

    with pytest.raises(ValueError, match="JSON list"):
        await MockProvider(listings_path).search(_watch("anything"))
