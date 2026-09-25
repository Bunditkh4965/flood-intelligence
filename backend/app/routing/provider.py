from dataclasses import dataclass
from typing import Protocol


Coordinates = tuple[float, float]  # (longitude, latitude)


@dataclass(frozen=True)
class RouteProviderResult:
    """Provider-neutral real road-network result; geometry is GeoJSON."""

    distance_km: float
    duration_minutes: float
    route_geometry: dict
    provider_name: str
    provider_route_id: str | None = None


class RoutingProvider(Protocol):
    def calculate_route(
        self, origin: Coordinates, destination: Coordinates, vehicle_profile: str
    ) -> RouteProviderResult: ...


class RoutingProviderNotConfigured(RuntimeError):
    pass


class NoRoutingProvider:
    """Safe default: never fabricates a route when no engine is configured."""

    def calculate_route(self, origin: Coordinates, destination: Coordinates, vehicle_profile: str) -> RouteProviderResult:
        raise RoutingProviderNotConfigured("No routing provider is configured")


_provider: RoutingProvider = NoRoutingProvider()


def get_routing_provider() -> RoutingProvider:
    return _provider
