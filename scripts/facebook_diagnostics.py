"""Opt-in, bounded location diagnostics; never used by automatic watch scans."""

import asyncio
import json
from pathlib import Path

from src.providers.facebook import (
    FacebookProviderError,
    PageFetcher,
    RetrievedPage,
    _listing_coordinates,
    _LocationDataParser,
    _raise_for_access_problem,
    parse_facebook_search_html,
)

_DETAIL_LIMIT = 3
_LOCATION_KEYS = {
    "latitude",
    "longitude",
    "lat",
    "lng",
    "lon",
    "city",
    "state",
    "reverse_geocode",
    "coordinate",
    "coordinates",
    "location",
}


def _location_fields(value: object) -> object:
    """Keep geographic fields only, excluding other page/session metadata."""
    if isinstance(value, dict):
        return {
            key: _location_fields(child)
            for key, child in value.items()
            if key in _LOCATION_KEYS
        }
    if isinstance(value, list):
        return [_location_fields(child) for child in value[:10]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return None


def summarize_locations(page: RetrievedPage, wanted_ids: set[str]) -> dict:
    """Report only locations associated with the requested listing IDs."""
    parser = _LocationDataParser()
    parser.feed(page.html)
    parser.close()
    locations: dict[str, list[dict]] = {key: [] for key in sorted(wanted_ids)}
    pending = list(parser.documents)
    while pending:
        value = pending.pop()
        if isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, dict):
            pending.extend(value.values())
            listing_id = str(value.get("id", ""))
            if listing_id in wanted_ids:
                fields = {
                    key: _location_fields(child)
                    for key, child in value.items()
                    if "location" in key.casefold() or "coordinate" in key.casefold()
                }
                if fields and fields not in locations[listing_id]:
                    locations[listing_id].append(fields)
    return {
        "json_documents": len(parser.documents),
        "listing_locations": locations,
        "verified_coordinates": _listing_coordinates(page.html, wanted_ids),
    }


async def save_location_diagnostics(
    search_page: RetrievedPage,
    output_dir: Path,
    fetch_page: PageFetcher,
    timeout_ms: int,
) -> Path:
    """Save the search and at most three detail pages, with independent errors.

    Raw HTML stays in the specified local directory. The small JSON report
    includes public listing geography, never environment values or cookies.
    Detail-page results do not change filtering or authorize any alerts.
    """
    await asyncio.to_thread(output_dir.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(
        (output_dir / "search.html").write_text, search_page.html, encoding="utf-8"
    )
    report: dict = {"search": {}, "details": []}
    try:
        _raise_for_access_problem(search_page)
        listings = parse_facebook_search_html(search_page.html, max_results=50)
    except FacebookProviderError as error:
        report["search"]["error"] = str(error)
        listings = []
    ids = {listing.external_id for listing in listings}
    report["search"].update(summarize_locations(search_page, ids))
    report["search"]["visible_listings"] = len(listings)
    for listing in listings[:_DETAIL_LIMIT]:
        detail: dict = {"listing_id": listing.external_id}
        print(f"Inspecting anonymous listing page {listing.external_id}...")
        try:
            page = await fetch_page(listing.url, timeout_ms)
            await asyncio.to_thread(
                (output_dir / f"item-{listing.external_id}.html").write_text,
                page.html,
                encoding="utf-8",
            )
            _raise_for_access_problem(page)
            detail.update(summarize_locations(page, {listing.external_id}))
        except FacebookProviderError as error:
            detail["error"] = str(error)
        report["details"].append(detail)
    report_path = output_dir / "location-report.json"
    await asyncio.to_thread(
        report_path.write_text, json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report_path
