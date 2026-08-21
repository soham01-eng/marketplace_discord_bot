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
