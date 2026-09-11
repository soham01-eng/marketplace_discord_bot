"""Location failures and bounded diagnostics for the observed city-only page."""

import argparse
import json
from pathlib import Path

import pytest

from scripts import check_facebook_access
from scripts.facebook_diagnostics import save_location_diagnostics, summarize_locations
from src.geo import SearchArea
from src.models import Watch
from src.providers.facebook import (
    FacebookMarkupError,
    FacebookProvider,
    RetrievedPage,
)

CITY_ONLY = (Path(__file__).parent / "fixtures/facebook_city_only.html").read_text()
SEARCH_PAGE = RetrievedPage(CITY_ONLY, "https://www.facebook.com/marketplace/detroit/")


async def test_captured_city_only_shape_cannot_use_search_center_as_item_location():
    async def fetch(url, timeout_ms):
        return SEARCH_PAGE

    provider = FacebookProvider(
        page_fetcher=fetch, search_area=SearchArea(42.377, -83.0796, 20)
    )
    watch = Watch(1, 101, "chair", None, None, "facebook", True, "test", None)
    with pytest.raises(FacebookMarkupError, match="City names and search-center"):
        await provider.search(watch)
    report = summarize_locations(SEARCH_PAGE, {"101", "102"})
    assert report["verified_coordinates"] == {}
    assert report["listing_locations"]["102"] == [
        {"location": {"reverse_geocode": {"city": "Detroit", "state": "MI"}}}
    ]


async def test_diagnostics_limit_detail_visits_and_keep_report_after_access_error(
    tmp_path,
):
    visited = []

    async def fetch(url, timeout_ms):
        visited.append(url)
        if len(visited) == 1:
            return RetrievedPage("login", "https://www.facebook.com/login/")
        return RetrievedPage(
            '<script type="application/json">'
            '{"id":"102","location":{"latitude":42.377,"longitude":-83.0796,'
            '"session":"DO_NOT_INCLUDE"},'
            '"session":"DO_NOT_INCLUDE"}</script>',
            url,
        )

    path = await save_location_diagnostics(SEARCH_PAGE, tmp_path, fetch, 1000)
    report = json.loads(path.read_text())
    assert len(visited) == 3
    assert all(
        url.startswith("https://www.facebook.com/marketplace/item/") for url in visited
    )
    assert report["search"]["visible_listings"] == 14
    assert report["search"]["verified_coordinates"] == {}
    assert "login" in report["details"][0]["error"]
    assert report["details"][1]["verified_coordinates"] == {"102": [42.377, -83.0796]}
    # Coordinates for another listing must not be attributed to item 103.
    assert report["details"][2]["verified_coordinates"] == {}
    assert "DO_NOT_INCLUDE" not in path.read_text()
    assert len(list(tmp_path.glob("item-*.html"))) == 3


async def test_no_detail_visits_on_search_access_challenge(tmp_path):
    async def fetch(url, timeout_ms):
        pytest.fail("A blocked search must not cause detail-page visits")

    page = RetrievedPage("challenge", "https://www.facebook.com/checkpoint/")
    path = await save_location_diagnostics(page, tmp_path, fetch, 1000)
    report = json.loads(path.read_text())
    assert "challenge" in report["search"]["error"]
    assert report["details"] == []


@pytest.mark.parametrize("diagnostics", [False, True])
async def test_checker_saves_opt_in_diagnostics_without_hiding_radius_failure(
    monkeypatch, tmp_path, diagnostics
):
    for setting in ("LATITUDE", "LONGITUDE", "RADIUS_MILES"):
        monkeypatch.delenv(f"FACEBOOK_SEARCH_{setting}", raising=False)
    calls = []

    async def fetch(url, timeout_ms):
        calls.append(url)
        return RetrievedPage(CITY_ONLY, url)

    monkeypatch.setattr(check_facebook_access, "_fetch_page_with_playwright", fetch)
    arguments = argparse.Namespace(
        query="office chair",
        location="detroit",
        max_results=5,
        latitude=42.377,
        longitude=-83.0796,
        radius_miles=20,
        diagnostics_dir=tmp_path if diagnostics else None,
    )
    assert await check_facebook_access._search(arguments) == 1
    assert len(calls) == (4 if diagnostics else 1)
    assert (tmp_path / "location-report.json").exists() == diagnostics
