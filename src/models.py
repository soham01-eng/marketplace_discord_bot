"""Application data models shared across storage and bot layers."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Watch:
    """A persisted marketplace search owned by one Discord user."""

    id: int
    discord_user_id: int
    query: str
    min_price: float | None
    max_price: float | None
    provider: str
    enabled: bool
    created_at: str
    last_checked: str | None


@dataclass(frozen=True, slots=True)
class Listing:
    """A marketplace-independent listing returned by every provider.

    Price is ``None`` when a provider cannot safely determine it. Image URLs
    are optional because some marketplaces do not expose an image for every
    result.
    """

    external_id: str
    title: str
    price: float | None
    url: str
    image_url: str | None
    source: str
