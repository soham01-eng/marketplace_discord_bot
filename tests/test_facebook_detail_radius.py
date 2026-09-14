"""Exercise bounded detail lookups using the observed geographic report shape."""

import json
from pathlib import Path

import pytest

from src.database import Database
from src.geo import SearchArea
from src.models import Watch
from src.providers.facebook import (
    FacebookAccessError,
    FacebookMarkupError,
    FacebookProvider,
    RetrievedPage,
)
from src.scanner import Scanner

AREA = SearchArea(42.377, -83.0796, 20)
WATCH = Watch(1, 101, "office chair", None, None, "facebook", True, "test", None)
FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/facebook_detail_locations.json").read_text()
)


def _json_html(objects):
    return '<script type="application/json">' + json.dumps(objects) + "</script>"


def _search_html(ids, objects=()):
    return "".join(
        f'<a href="/marketplace/item/{item}/">Office chair</a>' for item in ids
    ) + _json_html(objects)


def _location(item, lat=42.377, lon=-83.0796):
    return {"id": str(item), "location": {"latitude": lat, "longitude": lon}}


def _provider(ids, details, *, search_objects=(), limit=20, area=AREA):
    visited = []

    async def fetch(url, timeout_ms):
        if "/search/" in url:
            return RetrievedPage(_search_html(ids, search_objects), url)
        item = url.rstrip("/").split("/")[-1]
        visited.append(item)
        value = details[item]
        if isinstance(value, Exception):
            raise value
        if isinstance(value, RetrievedPage):
            return value
        return RetrievedPage(_json_html(value), url)

    return FacebookProvider(
        page_fetcher=fetch, search_area=area, max_results=limit
    ), visited


async def test_observed_details_filter_conflicts_and_distant_items_before_alerting(
    tmp_path,
):
    details = {item["listing_id"]: item["objects"] for item in FIXTURE["details"]}
    details["104"] = [_location("104", 42.7325, -84.5555)]  # Farther than 20 miles
    provider, visited = _provider(details, details)
    notified = []

    class Notifier:
        async def notify(self, user_id, watch, listing):
            notified.append(listing.external_id)

    database = Database(tmp_path / "details.db")
    try:
        watch = database.create_watch(101, "office chair", provider="facebook")
        scanner = Scanner(database, {"facebook": provider}, Notifier())
        result = await scanner.scan_watches()
        assert result.failures == 0
        assert notified == ["101", "102"]
        assert visited == ["101", "102", "103", "104"]
        assert not database.has_seen_listing(watch.id, "facebook", "103")
        assert not database.has_seen_listing(watch.id, "facebook", "104")
        assert (await scanner.scan_watches()).notifications_sent == 0
    finally:
        database.close()


async def test_detail_budget_never_exceeds_ten_requests():
    ids = [str(i) for i in range(101, 113)]
    details = {item: [] for item in ids}
    details["111"] = [_location("111")]
    provider, visited = _provider(ids, details)
    with pytest.raises(FacebookMarkupError, match="Cannot verify listing locations"):
        await provider.search(WATCH)
    assert visited == ids[:10]


async def test_limit_counts_nearby_results_and_known_search_locations_skip_fetches():
    details = {"101": [_location("101", 42.7325, -84.5555)], "103": [_location("103")]}
    provider, visited = _provider(
        ["101", "102", "103", "104"],
        details,
        search_objects=[_location("102")],
        limit=2,
    )
    assert [item.external_id for item in await provider.search(WATCH)] == ["102", "103"]
    assert visited == ["101", "103"]


async def test_city_only_mode_does_not_visit_detail_pages():
    provider, visited = _provider(["101", "102"], {}, area=None)
    assert len(await provider.search(WATCH)) == 2
    assert visited == []


async def test_search_conflict_cannot_be_overridden_by_a_detail_lookup():
    provider, visited = _provider(
        ["101", "102"],
        {},
        search_objects=[_location("101"), _location("101", 40, -85), _location("102")],
    )
    assert [item.external_id for item in await provider.search(WATCH)] == ["102"]
    assert visited == []


@pytest.mark.parametrize(
    "failure",
    [
        RetrievedPage("login", "https://www.facebook.com/login/"),
        RetrievedPage("challenge", "https://www.facebook.com/checkpoint/"),
        FacebookAccessError("browser timeout"),
    ],
)
async def test_access_failure_stops_more_detail_visits_but_retains_verified_results(
    failure,
):
    details = {"101": [_location("101")], "102": failure}
    provider, visited = _provider(["101", "102", "103"], details)
    assert [item.external_id for item in await provider.search(WATCH)] == ["101"]
    assert visited == ["101", "102"]


async def test_initial_detail_access_failure_is_not_reported_as_no_nearby_results():
    provider, visited = _provider(
        ["101", "102"], {"101": FacebookAccessError("browser timeout")}
    )
    with pytest.raises(FacebookMarkupError, match="Cannot verify listing locations"):
        await provider.search(WATCH)
    assert visited == ["101"]


async def test_unrelated_locations_and_wrong_detail_redirects_never_verify_an_item():
    details = {
        "101": [
            _location("999"),
            {"location": {"latitude": 42.377, "longitude": -83.0796}},
            {"id": "101", "seller": _location("101")},
        ],
        "102": RetrievedPage(
            _json_html([_location("102")]),
            "https://www.facebook.com/marketplace/item/999/",
        ),
        "103": [_location("103")],
    }
    # Seller coordinates deliberately have no own listing ID.
    details["101"][2]["seller"].pop("id")
    provider, visited = _provider(["101", "102", "103"], details)
    assert [item.external_id for item in await provider.search(WATCH)] == ["103"]
    assert visited == ["101", "102", "103"]
