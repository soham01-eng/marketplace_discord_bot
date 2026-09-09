"""Distance calculations independent of Facebook's search behavior."""

import pytest

from src.geo import SearchArea


def test_distance_from_48202_to_nearby_and_faraway_cities() -> None:
    area = SearchArea(42.377, -83.0796, 20)
    assert area.distance_miles(42.377, -83.0796) == 0
    assert 8 < area.distance_miles(42.4895, -83.1446) < 9  # Royal Oak
    assert 32 < area.distance_miles(42.2808, -83.7430) < 36  # Ann Arbor
    assert 75 < area.distance_miles(42.7325, -84.5555) < 85  # Lansing


def test_distance_handles_dateline_and_antipodes() -> None:
    area = SearchArea(0, 179.9, 20)
    assert 13 < area.distance_miles(0, -179.9) < 15
    assert 12_400 < area.distance_miles(0, -0.1) < 12_500


@pytest.mark.parametrize(
    "values",
    [
        (91, 0, 20),
        (0, -181, 20),
        (0, 0, 0),
        (0, 0, -1),
        (float("nan"), 0, 20),
        (0, float("inf"), 20),
        (0, 0, float("inf")),
    ],
)
def test_invalid_search_area_is_rejected(values) -> None:
    with pytest.raises(ValueError):
        SearchArea(*values)


def test_one_degree_of_latitude_is_about_69_miles() -> None:
    assert SearchArea(0, 0, 20).distance_miles(1, 0) == pytest.approx(
        69.0934, abs=0.001
    )
