"""Exercise strict distance filtering using synthetic, inert JSON page data.

These fixtures validate our supported metadata shape, not live Facebook access.
"""

import json
from urllib.parse import parse_qs, urlparse

import pytest

from src.database import Database
from src.geo import SearchArea
from src.models import Watch
from src.providers import FacebookMarkupError, FacebookProvider, RetrievedPage
from src.scanner import Scanner

AREA = SearchArea(42.377, -83.0796, 20)
WATCH = Watch(1, 101, "chair", None, None, "facebook", True, "test", None)


def _page(locations: list[dict]) -> str:
    # Visible cards, including a card without coordinates; metadata alone is not
    # enough to create an alert for an item that was not visible on the page.
    cards = "".join(
        f'<a href="/marketplace/item/{listing_id}/">Office chair</a>'
        for listing_id in ("101", "102", "103")
    )
    return (
        cards
        + '<script type="application/json">'
        + json.dumps({"data": {"edges": [{"node": {"listing": x}} for x in locations]}})
        + "</script>"
    )


def _location(listing_id, latitude, longitude):
    return {
        "id": listing_id,
        "location": {"latitude": latitude, "longitude": longitude},
    }


def _provider(html: str, *, area: SearchArea = AREA, limit: int = 20):
    async def fetch(url, timeout_ms):
        return RetrievedPage(html, url)

    return FacebookProvider(search_area=area, max_results=limit, page_fetcher=fetch)


async def test_only_nearby_verified_visible_cards_reach_notifications(tmp_path):
    html = _page(
        [
            _location("101", 42.7325, -84.5555),  # Lansing: outside 20 miles
            _location("102", 42.4895, -83.1446),  # Royal Oak: inside
            _location("999", 42.377, -83.0796),  # Metadata without a visible card
        ]
    )
    # Limit is applied after distance filtering, so the first faraway card
    # cannot hide a subsequent nearby card.
    provider = _provider(html, limit=1)
    notified = []

    class Notifier:
        async def notify(self, user_id, watch, listing):
            notified.append(listing.external_id)

    database = Database(tmp_path / "radius.db")
    try:
        watch = database.create_watch(101, "office chair", provider="facebook")
        scanner = Scanner(database, {"facebook": provider}, Notifier())
        first = await scanner.scan_watches()
        assert first.failures == 0
        assert notified == ["102"]
        assert (await scanner.scan_watches()).notifications_sent == 0
        assert not database.has_seen_listing(watch.id, "facebook", "101")
        assert not database.has_seen_listing(watch.id, "facebook", "103")
    finally:
        database.close()


def test_search_url_keeps_query_and_includes_coordinate_and_kilometer_hints():
    parameters = parse_qs(
        urlparse(_provider("").build_search_url("chair & desk")).query
    )
    assert parameters == {
        "query": ["chair & desk"],
        "exact": ["false"],
        "latitude": ["42.377"],
        "longitude": ["-83.0796"],
        "radius": ["33"],
    }


@pytest.mark.parametrize(
    "locations",
    [
        [],
        [_location("101", None, None)],
        [_location("101", True, -83.0796)],
        [_location("101", 999, -83.0796)],
        [_location("101", 42.377, float("nan"))],
        [_location("101", "42.377", "-83.0796")],
        [_location("999", 42.377, -83.0796)],
        [_location("101", 42.377, -83.0796), _location("101", 42.7325, -84.5555)],
        [
            {
                "id": "101",
                "seller": {"location": {"latitude": 42.377, "longitude": -83.0796}},
            }
        ],
    ],
)
async def test_unknown_invalid_unrelated_or_conflicting_coordinates_fail_clearly(
    locations,
):
    provider = _provider(_page(locations))
    with pytest.raises(FacebookMarkupError, match="Cannot verify listing locations"):
        await provider.search(WATCH)


async def test_all_known_cards_outside_radius_are_valid_empty_results():
    provider = _provider(_page([_location("101", 42.7325, -84.5555)]))
    assert await provider.search(WATCH) == []


async def test_boundary_is_inclusive_and_one_step_outside_is_excluded():
    latitude = 42.6665
    distance = AREA.distance_miles(latitude, AREA.longitude)
    html = _page([_location("101", latitude, AREA.longitude)])
    watch = WATCH
    inclusive = _provider(
        html, area=SearchArea(AREA.latitude, AREA.longitude, distance)
    )
    assert len(await inclusive.search(watch)) == 1
    exclusive = _provider(
        html, area=SearchArea(AREA.latitude, AREA.longitude, distance - 0.001)
    )
    assert await exclusive.search(watch) == []


async def test_malformed_json_does_not_override_valid_listing_data():
    html = '<script type="application/json">not json</script>' + _page(
        [_location("101", 42.377, -83.0796)]
    )
    listings = await _provider(html).search(WATCH)
    assert [item.external_id for item in listings] == ["101"]
