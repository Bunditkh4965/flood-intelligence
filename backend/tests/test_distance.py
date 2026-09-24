import pytest

from app.services.distance import straight_line_distance_km


def test_distance_calculation_for_one_degree_at_equator() -> None:
    assert straight_line_distance_km(0, 0, 0, 1) == pytest.approx(111.195, abs=0.01)
