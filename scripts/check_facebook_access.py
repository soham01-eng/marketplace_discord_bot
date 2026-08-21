"""Run one bounded anonymous Facebook Marketplace provider check."""

import argparse
import asyncio
import os

from dotenv import load_dotenv

from src.models import Watch
from src.providers import FacebookProvider, FacebookProviderError


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check anonymous Facebook Marketplace access with Playwright.",
    )
    parser.add_argument("--query", default="office chair")
    parser.add_argument(
        "--location",
        default=os.environ.get("FACEBOOK_MARKETPLACE_LOCATION", "detroit"),
    )
    parser.add_argument("--max-results", type=int, default=5)
    return parser.parse_args()


async def _search(arguments: argparse.Namespace) -> int:
    watch = Watch(
        id=0,
        discord_user_id=0,
        query=arguments.query,
        min_price=None,
        max_price=None,
        provider="facebook",
        enabled=True,
        created_at="manual-check",
        last_checked=None,
    )
    provider = FacebookProvider(
        location_slug=arguments.location,
        max_results=arguments.max_results,
    )
    try:
        listings = await provider.search(watch)
    except FacebookProviderError as error:
        print(f"Anonymous Facebook Marketplace check failed: {error}")
        return 1

    print(f"Retrieved {len(listings)} normalized listings:")
    for listing in listings:
        price = "unknown price" if listing.price is None else f"${listing.price:,.2f}"
        print(f"- {listing.external_id}: {listing.title} — {price}")
        print(f"  {listing.url}")
    return 0


def main() -> int:
    """Load local configuration and run the standalone access experiment."""
    load_dotenv()
    return asyncio.run(_search(_arguments()))


if __name__ == "__main__":
    raise SystemExit(main())
