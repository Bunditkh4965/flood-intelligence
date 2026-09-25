import math
from collections.abc import Sequence

import httpx

from app.routing.provider import (
    Coordinates,
    NoRouteFound,
    RouteProviderResult,
    RoutingProviderConnectionError,
    RoutingProviderResponseError,
    RoutingProviderTimeout,
)


def decode_polyline6(encoded: str) -> list[list[float]]:
    """Decode Valhalla's polyline6 into GeoJSON [longitude, latitude] pairs."""
    if not isinstance(encoded, str) or not encoded:
        raise RoutingProviderResponseError("Valhalla returned an empty route shape")
    coordinates: list[list[float]] = []
    latitude = longitude = index = 0
    try:
        while index < len(encoded):
            deltas: list[int] = []
            for _ in range(2):
                result = shift = 0
                while True:
                    value = ord(encoded[index]) - 63
                    index += 1
                    if value < 0 or value > 63:
                        raise ValueError
                    result |= (value & 0x1F) << shift
                    shift += 5
                    if value < 0x20:
                        break
                    if shift > 30:
                        raise ValueError
                deltas.append(~(result >> 1) if result & 1 else result >> 1)
            latitude += deltas[0]
            longitude += deltas[1]
            coordinates.append([longitude / 1_000_000, latitude / 1_000_000])
    except (IndexError, ValueError) as exc:
        raise RoutingProviderResponseError("Valhalla returned a malformed route shape") from exc
    if len(coordinates) < 2:
        raise RoutingProviderResponseError("Valhalla route shape has fewer than two coordinates")
    return coordinates


class ValhallaRoutingProvider:
    """HTTP adapter for shared Valhalla infrastructure.

    All current application vehicle profiles intentionally use Valhalla's
    generic auto costing until authoritative vehicle restriction data exists.
    """

    provider_name = "VALHALLA"
    _supported_profiles = {"4W", "6W", "10W"}

    def __init__(self, base_url: str, timeout_seconds: float = 10.0, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.client = client

    def _request_body(self, origin: Coordinates, destination: Coordinates, vehicle_profile: str) -> dict:
        if vehicle_profile not in self._supported_profiles:
            raise ValueError(f"Unsupported vehicle profile: {vehicle_profile}")
        return {
            "locations": [
                {"lat": origin[1], "lon": origin[0]},
                {"lat": destination[1], "lon": destination[0]},
            ],
            "costing": "auto",
            "units": "kilometers",
            "shape_format": "polyline6",
        }

    def calculate_route(self, origin: Coordinates, destination: Coordinates, vehicle_profile: str) -> RouteProviderResult:
        try:
            requester = self.client or httpx
            response = requester.post(
                f"{self.base_url}/route",
                json=self._request_body(origin, destination, vehicle_profile),
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise RoutingProviderTimeout("Valhalla routing request timed out") from exc
        except httpx.RequestError as exc:
            raise RoutingProviderConnectionError("Could not connect to Valhalla") from exc

        if not 200 <= response.status_code < 300:
            if response.status_code in {404, 422}:
                raise NoRouteFound("Valhalla could not find a route")
            raise RoutingProviderResponseError(
                f"Valhalla returned HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RoutingProviderResponseError("Valhalla returned invalid JSON") from exc
        try:
            trip = payload["trip"]
            summary = trip["summary"]
            legs = trip["legs"]
            if not isinstance(legs, Sequence) or isinstance(legs, (str, bytes)) or not legs:
                raise KeyError("legs")
            shapes = [leg["shape"] for leg in legs]
            distance = float(summary["length"])
            duration_seconds = float(summary["time"])
        except (KeyError, TypeError, ValueError) as exc:
            # A valid Valhalla no-path response may contain an empty trip/legs.
            if isinstance(payload, dict) and (payload.get("error_code") or payload.get("trip") == {}):
                raise NoRouteFound("Valhalla could not find a route") from exc
            raise RoutingProviderResponseError("Valhalla response is missing route fields") from exc
        if not all(math.isfinite(value) and value > 0 for value in (distance, duration_seconds)):
            raise RoutingProviderResponseError("Valhalla returned invalid distance or duration")

        decoded_legs = [decode_polyline6(shape) for shape in shapes]
        coordinates = decoded_legs[0]
        for leg in decoded_legs[1:]:
            coordinates.extend(leg[1:] if coordinates[-1] == leg[0] else leg)
        return RouteProviderResult(
            distance_km=distance,
            duration_minutes=duration_seconds / 60,
            route_geometry={"type": "LineString", "coordinates": coordinates},
            provider_name=self.provider_name,
            provider_route_id=str(trip["id"]) if trip.get("id") is not None else None,
        )
