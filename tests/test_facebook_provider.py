"""Deterministic tests for the experimental Facebook Marketplace provider."""

from pathlib import Path

import pytest

from src.models import Listing, Watch
from src.providers import (
    FacebookAccessError,
    FacebookMarkupError,
    FacebookProvider,
    ListingProvider,
    RetrievedPage,
    parse_facebook_search_html,
)

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "facebook_search.html"


def _watch(query: str = "office chair") -> Watch:
    return Watch(
        id=1,
        discord_user_id=101,
        query=query,
        min_price=None,
        max_price=None,
        provider="facebook",
        enabled=True,
        created_at="2026-08-21T00:00:00+00:00",
        last_checked=None,
    )


def test_parser_extracts_normalized_listings_from_saved_fixture() -> None:
    html = _FIXTURE_PATH.read_text(encoding="utf-8")

    listings = parse_facebook_search_html(html)

    assert listings == [
        Listing(
            external_id="123456789012345",
            title="Herman Miller Aeron Office Chair",
            price=125.0,
            url=("https://www.facebook.com/marketplace/item/123456789012345/"),
            image_url="https://example.com/images/aeron.jpg",
            source="facebook",
        ),
        Listing(
            external_id="987654321098765",
            title="Wooden Office Chair",
            price=0.0,
            url=("https://www.facebook.com/marketplace/item/987654321098765/"),
            image_url=None,
            source="facebook",
        ),
        Listing(
            external_id="555555555555555",
            title="Steelcase Leap Office Chair",
            price=None,
            url=("https://www.facebook.com/marketplace/item/555555555555555/"),
            image_url=None,
            source="facebook",
        ),
    ]


def test_parser_bounds_results_and_deduplicates_stable_ids() -> None:
    html = _FIXTURE_PATH.read_text(encoding="utf-8")

    listings = parse_facebook_search_html(html, max_results=2)

    assert [listing.external_id for listing in listings] == [
        "123456789012345",
        "987654321098765",
    ]


def test_parser_reports_listing_without_usable_title() -> None:
    html = """
    <a href="/marketplace/item/123456789/">
      <img src="data:image/gif;base64,placeholder" alt="May be an image">
      <span>$50</span>
    </a>
    """

    with pytest.raises(FacebookMarkupError, match="missing a usable title"):
        parse_facebook_search_html(html)


@pytest.mark.asyncio
async def test_provider_uses_shared_contract_and_encodes_search_query() -> None:
    requested: list[tuple[str, int]] = []

    async def fetch_page(url: str, timeout_ms: int) -> RetrievedPage:
        requested.append((url, timeout_ms))
        return RetrievedPage(
            html=_FIXTURE_PATH.read_text(encoding="utf-8"),
            url=url,
        )

    provider: ListingProvider = FacebookProvider(
        "detroit",
        max_results=1,
        page_fetcher=fetch_page,
    )

    listings = await provider.search(_watch("office chair & desk"))

    assert len(listings) == 1
    assert requested == [
        (
            "https://www.facebook.com/marketplace/detroit/search/"
            "?query=office+chair+%26+desk&exact=false",
            20_000,
        )
    ]


@pytest.mark.asyncio
async def test_provider_reports_anonymous_login_redirect() -> None:
    async def fetch_page(url: str, timeout_ms: int) -> RetrievedPage:
        return RetrievedPage(
            html="<h1>Log into Facebook</h1>",
            url="https://www.facebook.com/login/?next=marketplace",
        )

    provider = FacebookProvider(page_fetcher=fetch_page)

    with pytest.raises(FacebookAccessError, match="login page"):
        await provider.search(_watch())


@pytest.mark.asyncio
async def test_provider_reports_access_challenge() -> None:
    async def fetch_page(url: str, timeout_ms: int) -> RetrievedPage:
        return RetrievedPage(
            html="<h1>Verify you are human</h1>",
            url=url,
        )

    provider = FacebookProvider(page_fetcher=fetch_page)

    with pytest.raises(FacebookAccessError, match="access challenge"):
        await provider.search(_watch())


@pytest.mark.asyncio
async def test_provider_reports_checkpoint_redirect() -> None:
    async def fetch_page(url: str, timeout_ms: int) -> RetrievedPage:
        return RetrievedPage(
            html="<main>Security check</main>",
            url="https://www.facebook.com/checkpoint/123/",
        )

    provider = FacebookProvider(page_fetcher=fetch_page)

    with pytest.raises(FacebookAccessError, match="access challenge"):
        await provider.search(_watch())


@pytest.mark.asyncio
async def test_provider_distinguishes_empty_results_from_markup_changes() -> None:
    pages = iter(
        [
            "<main>No listings found</main>",
            "<main>Marketplace results changed unexpectedly</main>",
        ]
    )

    async def fetch_page(url: str, timeout_ms: int) -> RetrievedPage:
        return RetrievedPage(html=next(pages), url=url)

    provider = FacebookProvider(page_fetcher=fetch_page)

    assert await provider.search(_watch("unlikely query")) == []
    with pytest.raises(FacebookMarkupError, match="markup may have changed"):
        await provider.search(_watch())


@pytest.mark.parametrize("location", ["", "detroit/mi", "detroit michigan"])
def test_provider_rejects_unsafe_location_slug(location: str) -> None:
    with pytest.raises(ValueError, match="location"):
        FacebookProvider(location)
