import pytest
from pydantic import ValidationError

from app.schemas.branch import Coordinates


@pytest.mark.parametrize("latitude,longitude", [(91, 0), (-91, 0), (0, 181), (0, -181)])
def test_invalid_coordinates_are_rejected(latitude: float, longitude: float) -> None:
    with pytest.raises(ValidationError):
        Coordinates(latitude=latitude, longitude=longitude)
