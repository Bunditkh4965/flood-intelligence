from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0088


def straight_line_distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate great-circle distance using the Haversine formula."""
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return EARTH_RADIUS_KM * 2 * asin(sqrt(a))
