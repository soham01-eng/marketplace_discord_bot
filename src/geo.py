"""Small, offline helpers for straight-line search distances."""

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SearchArea:
    """A radius around an approximate latitude/longitude center, in miles."""

    latitude: float
    longitude: float
    radius_miles: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.latitude) or not -90 <= self.latitude <= 90:
            raise ValueError("Search latitude must be between -90 and 90")
        if not math.isfinite(self.longitude) or not -180 <= self.longitude <= 180:
            raise ValueError("Search longitude must be between -180 and 180")
        if not math.isfinite(self.radius_miles) or self.radius_miles <= 0:
            raise ValueError("Search radius must be a finite number greater than zero")

    def distance_miles(self, latitude: float, longitude: float) -> float:
        """Return great-circle distance using the haversine formula."""
        lat1, lat2 = math.radians(self.latitude), math.radians(latitude)
        delta_lat = lat2 - lat1
        delta_lon = math.radians(longitude - self.longitude)
        haversine = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
        )
        return 3958.7613 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, haversine))))

    @property
    def description(self) -> str:
        return (
            f"{self.radius_miles:g} miles around "
            f"({self.latitude:g}, {self.longitude:g})"
        )
