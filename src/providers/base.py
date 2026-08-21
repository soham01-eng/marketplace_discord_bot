"""Contract implemented by all marketplace listing providers."""

from abc import ABC, abstractmethod

from src.models import Listing, Watch


class ListingProvider(ABC):
    """Retrieve normalized listings from one external marketplace."""

    @abstractmethod
    async def search(self, watch: Watch) -> list[Listing]:
        """Return listings for a watch using the shared normalized model."""
