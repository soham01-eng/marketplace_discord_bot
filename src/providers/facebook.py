"""Experimental anonymous Facebook Marketplace listing provider."""

import json
import logging
import math
import re
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlencode, urlparse

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from src.geo import SearchArea
from src.models import Listing, Watch
from src.providers.base import ListingProvider

logger = logging.getLogger(__name__)

_FACEBOOK_ORIGIN = "https://www.facebook.com"
_ITEM_HREF_PATTERN = re.compile(r"/marketplace/item/(?P<listing_id>\d+)(?:[/?#]|$)")
_PRICE_PATTERN = re.compile(r"(?:US\$|\$)\s*(?P<amount>\d[\d,]*(?:\.\d{1,2})?)")
_LOCATION_PATTERN = re.compile(r"[A-Za-z0-9-]+")
_GENERIC_TITLES = {
    "facebook",
    "marketplace",
    "marketplace listing",
    "pending",
    "photo",
    "sold",
    "sponsored",
}


class FacebookProviderError(RuntimeError):
    """Base error raised for expected Facebook provider failures."""


class FacebookAccessError(FacebookProviderError):
    """Raised when Facebook requires login or presents an access challenge."""


class FacebookMarkupError(FacebookProviderError):
    """Raised when Marketplace markup cannot be parsed safely."""


@dataclass(frozen=True, slots=True)
class RetrievedPage:
    """HTML and final URL returned by one bounded browser visit."""

    html: str
    url: str


PageFetcher = Callable[[str, int], Awaitable[RetrievedPage]]


@dataclass(slots=True)
class _RawListingCard:
    listing_id: str
    aria_label: str | None
    text_parts: list[str]
    image_url: str | None = None
    image_alt: str | None = None


class _ListingAnchorParser(HTMLParser):
    """Collect listing anchors without depending on generated CSS classes."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[_RawListingCard] = []
        self._active_card: _RawListingCard | None = None
        self._nested_anchor_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        if tag == "a":
            if self._active_card is not None:
                self._nested_anchor_depth += 1
                return

            href = attributes.get("href") or ""
            match = _ITEM_HREF_PATTERN.search(href)
            if match is None:
                return
            self._active_card = _RawListingCard(
                listing_id=match.group("listing_id"),
                aria_label=_clean_text(attributes.get("aria-label")),
                text_parts=[],
            )
            return

        if tag == "img" and self._active_card is not None:
            image_url = attributes.get("src") or attributes.get("data-src")
            self._active_card.image_url = _http_url_or_none(image_url)
            self._active_card.image_alt = _clean_text(attributes.get("alt"))

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._active_card is None:
            return
        if self._nested_anchor_depth:
            self._nested_anchor_depth -= 1
            return
        self.cards.append(self._active_card)
        self._active_card = None

    def handle_data(self, data: str) -> None:
        if self._active_card is None:
            return
        text = _clean_text(data)
        if text:
            self._active_card.text_parts.append(text)


class FacebookProvider(ListingProvider):
    """Retrieve a small anonymous Marketplace result page with Playwright."""

    source = "facebook"

    def __init__(
        self,
        location_slug: str = "detroit",
        *,
        max_results: int = 20,
        timeout_ms: int = 20_000,
        page_fetcher: PageFetcher | None = None,
        search_area: SearchArea | None = None,
    ) -> None:
        normalized_location = location_slug.strip().lower()
        if (
            not normalized_location
            or _LOCATION_PATTERN.fullmatch(normalized_location) is None
        ):
            raise ValueError(
                "Facebook Marketplace location must contain only letters, numbers, "
                "and hyphens"
            )
        if not 1 <= max_results <= 50:
            raise ValueError("Facebook max_results must be between 1 and 50")
        if timeout_ms < 1_000:
            raise ValueError("Facebook timeout_ms must be at least 1000")

        self.location_slug = normalized_location
        self.max_results = max_results
        self.timeout_ms = timeout_ms
        self.search_area = search_area
        self._page_fetcher = page_fetcher or _fetch_page_with_playwright

    async def search(self, watch: Watch) -> list[Listing]:
        """Return normalized listings from one bounded Marketplace search page."""
        search_url = self.build_search_url(watch.query)
        page = await self._page_fetcher(search_url, self.timeout_ms)
        _raise_for_access_problem(page)

        listings = parse_facebook_search_html(
            page.html,
            max_results=50 if self.search_area is not None else self.max_results,
        )
        if listings:
            if self.search_area is not None:
                return self._filter_by_distance(listings, page.html)[: self.max_results]
            return listings
        if _is_known_empty_result_page(page.html):
            return []
        raise FacebookMarkupError(
            "Facebook Marketplace returned no recognizable listing links; "
            "its page markup may have changed"
        )

    def build_search_url(self, query: str) -> str:
        """Build a location-scoped search URL without storing Facebook credentials."""
        parameters = {"query": query.strip(), "exact": "false"}
        if self.search_area is not None:
            # URL hints are best-effort; the local check enforces the actual radius.
            parameters.update(
                latitude=str(self.search_area.latitude),
                longitude=str(self.search_area.longitude),
                radius=str(math.ceil(self.search_area.radius_miles * 1.609344)),
            )
        return (
            f"{_FACEBOOK_ORIGIN}/marketplace/{self.location_slug}/search/"
            f"?{urlencode(parameters)}"
        )

    def _filter_by_distance(self, listings: list[Listing], html: str) -> list[Listing]:
        """Exclude distant and unlocated cards before persistence or notification."""
        assert self.search_area is not None
        coordinates = _listing_coordinates(
            html, {item.external_id for item in listings}
        )
        if not coordinates:
            raise FacebookMarkupError(
                "Cannot verify listing locations for the configured radius; "
                "Facebook did not expose usable coordinates. No alerts were sent "
                "for this watch. Run scripts.check_facebook_access locally."
            )
        nearby = []
        unknown = 0
        for listing in listings:
            location = coordinates.get(listing.external_id)
            if location is None:
                unknown += 1
                continue
            if (
                self.search_area.distance_miles(*location)
                <= self.search_area.radius_miles
            ):
                nearby.append(listing)
        logger.info(
            "Facebook radius filter: %s nearby, %s outside radius, %s unknown location",
            len(nearby),
            len(listings) - len(nearby) - unknown,
            unknown,
        )
        if unknown:
            logger.warning(
                "Skipped %s Facebook listings with unverified locations", unknown
            )
        return nearby


class _LocationDataParser(HTMLParser):
    """Read inert JSON page data; never execute scripts or infer from seller cities."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.documents: list[object] = []
        self._parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" and dict(attrs).get("type") == "application/json":
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._parts is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._parts is not None:
            with suppress(ValueError, RecursionError):
                self.documents.append(json.loads("".join(self._parts)))
            self._parts = None


def _listing_coordinates(
    html: str, wanted_ids: set[str]
) -> dict[str, tuple[float, float]]:
    """Join each visible card to its own JSON listing location by stable ID.

    Coordinates are accepted only from the same object as the listing ID.
    Missing, invalid, or conflicting locations remain unverified.
    """
    parser = _LocationDataParser()
    parser.feed(html)
    parser.close()
    locations: dict[str, tuple[float, float]] = {}
    conflicts: set[str] = set()
    pending = list(parser.documents)
    while pending:
        value = pending.pop()
        if isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, dict):
            pending.extend(value.values())
            listing_id = str(value.get("id", ""))
            if listing_id not in wanted_ids or listing_id in conflicts:
                continue
            location = value.get("location")
            if not isinstance(location, dict):
                continue
            latitude, longitude = location.get("latitude"), location.get("longitude")
            if (
                isinstance(latitude, bool)
                or isinstance(longitude, bool)
                or not isinstance(latitude, (int, float))
                or not isinstance(longitude, (int, float))
                or not math.isfinite(latitude)
                or not math.isfinite(longitude)
                or not -90 <= latitude <= 90
                or not -180 <= longitude <= 180
            ):
                continue
            coordinate = (float(latitude), float(longitude))
            if listing_id in locations and locations[listing_id] != coordinate:
                locations.pop(listing_id)
                conflicts.add(listing_id)
            else:
                locations[listing_id] = coordinate
    return locations


async def _fetch_page_with_playwright(url: str, timeout_ms: int) -> RetrievedPage:
    """Load one page anonymously and always close its temporary browser."""
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page(locale="en-US")
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
                if not urlparse(page.url).path.casefold().startswith("/login"):
                    with suppress(PlaywrightTimeoutError):
                        await page.locator(
                            'a[href*="/marketplace/item/"]'
                        ).first.wait_for(
                            state="attached",
                            timeout=min(5_000, timeout_ms // 2),
                        )
                await page.wait_for_timeout(500)
                return RetrievedPage(html=await page.content(), url=page.url)
            finally:
                await browser.close()
    except PlaywrightTimeoutError as error:
        raise FacebookAccessError(
            "Facebook Marketplace did not load before the browser timeout"
        ) from error
    except FacebookProviderError:
        raise
    except Exception as error:
        raise FacebookProviderError(
            "Facebook Marketplace page retrieval failed; confirm that Playwright "
            "Chromium is installed"
        ) from error


def parse_facebook_search_html(
    html: str,
    *,
    max_results: int = 20,
) -> list[Listing]:
    """Parse stable listing links from saved or live Marketplace HTML."""
    if not 1 <= max_results <= 50:
        raise ValueError("Facebook max_results must be between 1 and 50")

    parser = _ListingAnchorParser()
    parser.feed(html)
    parser.close()

    listings: list[Listing] = []
    seen_ids: set[str] = set()
    invalid_messages: list[str] = []
    for card in parser.cards:
        if card.listing_id in seen_ids:
            continue
        try:
            listing = _normalize_card(card)
        except FacebookMarkupError as error:
            invalid_messages.append(str(error))
            continue

        seen_ids.add(card.listing_id)
        listings.append(listing)
        if len(listings) == max_results:
            break

    if not listings and invalid_messages:
        raise FacebookMarkupError(invalid_messages[0])
    for message in invalid_messages:
        logger.warning(message)
    return listings


def _normalize_card(card: _RawListingCard) -> Listing:
    """Convert one structural listing anchor into the shared model."""
    title = _listing_title(card)
    if title is None:
        raise FacebookMarkupError(
            f"Facebook listing {card.listing_id} is missing a usable title"
        )

    return Listing(
        external_id=card.listing_id,
        title=title,
        price=_listing_price(card.text_parts),
        url=f"{_FACEBOOK_ORIGIN}/marketplace/item/{card.listing_id}/",
        image_url=card.image_url,
        source=FacebookProvider.source,
    )


def _listing_title(card: _RawListingCard) -> str | None:
    """Prefer accessible labels, then visible card text, then useful image alt text."""
    candidates = [card.aria_label, *card.text_parts, card.image_alt]
    for candidate in candidates:
        title = _clean_title_candidate(candidate, card.listing_id)
        if title is not None:
            return title
    return None


def _clean_title_candidate(value: str | None, listing_id: str) -> str | None:
    text = _clean_text(value)
    if text is None:
        return None

    lowered = text.casefold()
    for prefix in ("marketplace listing:", "listing:"):
        if lowered.startswith(prefix):
            text = text[len(prefix) :].strip()
            lowered = text.casefold()
            break

    parts = [part.strip() for part in text.split(",")]
    listing_marker = re.fullmatch(
        rf"listing\s*:?\s*{re.escape(listing_id)}",
        parts[-1],
        flags=re.IGNORECASE,
    )
    if listing_marker is not None:
        title_parts = parts[:-3] if len(parts) >= 4 else parts[:-1]
        text = ", ".join(part for part in title_parts if part).strip()

    text = _PRICE_PATTERN.sub("", text).strip(" -|·,")
    lowered = text.casefold()
    if not text or lowered in _GENERIC_TITLES or lowered == "free":
        return None
    if lowered.startswith(("may be an image", "image may contain")):
        return None
    return text


def _listing_price(text_parts: list[str]) -> float | None:
    for text in text_parts:
        if text.casefold() == "free":
            return 0.0
        match = _PRICE_PATTERN.search(text)
        if match is not None:
            return float(match.group("amount").replace(",", ""))
    return None


def _raise_for_access_problem(page: RetrievedPage) -> None:
    path = urlparse(page.url).path.casefold()
    if path.startswith("/login"):
        raise FacebookAccessError(
            "Facebook redirected anonymous Marketplace access to its login page"
        )
    if path.startswith("/checkpoint"):
        raise FacebookAccessError(
            "Facebook presented an access challenge; manual attention may be required"
        )

    if _ITEM_HREF_PATTERN.search(page.html) is not None:
        return
    if _is_known_empty_result_page(page.html):
        return

    lowered = page.html.casefold()
    challenge_phrases = (
        "verify you are human",
        "unusual activity",
        "temporarily blocked",
        "security check required",
        "/checkpoint/",
    )
    if any(phrase in lowered for phrase in challenge_phrases):
        raise FacebookAccessError(
            "Facebook presented an access challenge; manual attention may be required"
        )
    if "log into facebook" in lowered or "login_form" in lowered:
        raise FacebookAccessError("Facebook requires login for this Marketplace search")


def _is_known_empty_result_page(html: str) -> bool:
    lowered = html.casefold()
    return "no listings found" in lowered or "no results for" in lowered


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    return normalized or None


def _http_url_or_none(value: str | None) -> str | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"}:
        return None
    return cleaned
