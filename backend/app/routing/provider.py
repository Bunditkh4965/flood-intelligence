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


class RoutingProviderError(RuntimeError):
    """Safe, application-level failure raised by a routing adapter."""

    code = "ROUTING_PROVIDER_ERROR"
    status_code = 502


class RoutingProviderTimeout(RoutingProviderError):
    code = "ROUTING_PROVIDER_TIMEOUT"
    status_code = 504


class RoutingProviderConnectionError(RoutingProviderError):
    code = "ROUTING_PROVIDER_CONNECTION_FAILED"


class RoutingProviderResponseError(RoutingProviderError):
    code = "ROUTING_PROVIDER_BAD_RESPONSE"


class NoRouteFound(RoutingProviderError):
    code = "ROUTE_NOT_FOUND"
    status_code = 422


class NoRoutingProvider:
    """Safe default: never fabricates a route when no engine is configured."""

    def calculate_route(self, origin: Coordinates, destination: Coordinates, vehicle_profile: str) -> RouteProviderResult:
        raise RoutingProviderNotConfigured("No routing provider is configured")


_provider: RoutingProvider = NoRoutingProvider()


def get_routing_provider() -> RoutingProvider:
    from app.core import get_settings

    settings = get_settings()
    selection = settings.routing_provider.strip().lower()
    if not selection or selection in {"none", "disabled"}:
        return _provider
    if selection == "valhalla" and settings.valhalla_url.strip():
        from app.routing.valhalla import ValhallaRoutingProvider

        return ValhallaRoutingProvider(settings.valhalla_url, settings.valhalla_timeout_seconds)
    raise RoutingProviderNotConfigured(
        "ROUTING_PROVIDER must select a configured provider (supported: valhalla)"
    )
