"""Provider-independent matching rules for normalized listings."""

from src.models import Listing, Watch


def matches_watch(listing: Listing, watch: Watch) -> bool:
    """Return whether a listing satisfies a watch's query and price bounds."""
    title = listing.title.casefold()
    if not all(word in title for word in watch.query.casefold().split()):
        return False

    if listing.price is None:
        return watch.min_price is None and watch.max_price is None
    if watch.min_price is not None and listing.price < watch.min_price:
        return False
    return watch.max_price is None or listing.price <= watch.max_price
