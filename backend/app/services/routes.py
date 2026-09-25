import json
import math
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.transport import TransportRoute
from app.routing.provider import RouteProviderResult, RoutingProvider
from app.schemas.transport import RouteCalculateRequest, RouteRead
from app.services.branches import get_branch_by_store_number
from app.services.distribution_centers import get_distribution_center


class RouteLocationError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 404):
        super().__init__(message)
        self.code, self.status_code = code, status_code


def _location(db: Session, location_type: str, code: str):
    value = get_distribution_center(db, code) if location_type == "DC" else get_branch_by_store_number(db, code)
    if value is None:
        raise RouteLocationError(f"{location_type}_NOT_FOUND", f"{location_type.title()} '{code}' was not found")
    if value.status.upper() != "ACTIVE":
        raise RouteLocationError(f"{location_type}_INACTIVE", f"{location_type.title()} '{code}' is inactive", 409)
    return value


def _normalize_result(result: RouteProviderResult) -> RouteProviderResult:
    if not all(math.isfinite(value) and value >= 0 for value in (result.distance_km, result.duration_minutes)):
        raise ValueError("Routing provider returned a negative distance or duration")
    if not result.provider_name.strip():
        raise ValueError("Routing provider name is required")
    geometry_type = result.route_geometry.get("type") if isinstance(result.route_geometry, dict) else None
    if geometry_type != "LineString":
        raise ValueError("Routing provider must return a GeoJSON LineString")
    coordinates = result.route_geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise ValueError("Routing provider returned empty route geometry")
    for coordinate in coordinates:
        if (not isinstance(coordinate, list) or len(coordinate) != 2
                or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in coordinate)
                or not -180 <= coordinate[0] <= 180 or not -90 <= coordinate[1] <= 90):
            raise ValueError("Routing provider returned invalid route coordinates")
    return result


def calculate_and_store_route(db: Session, request: RouteCalculateRequest, provider: RoutingProvider) -> RouteRead:
    if request.origin.type.value != "DC" or request.destination.type.value != "BRANCH":
        raise RouteLocationError(
            "UNSUPPORTED_ROUTE_ENDPOINTS", "Sprint 5A supports DC-to-BRANCH routes only", 422
        )
    origin = _location(db, request.origin.type.value, request.origin.code)
    destination = _location(db, request.destination.type.value, request.destination.code)
    result = _normalize_result(provider.calculate_route(
        (origin.longitude, origin.latitude),
        (destination.longitude, destination.latitude),
        request.vehicle_profile.value,
    ))
    calculated_at = datetime.now(timezone.utc)
    route_id = str(uuid4())
    route = TransportRoute(
        route_id=route_id, origin_type=request.origin.type.value, origin_code=request.origin.code,
        destination_type=request.destination.type.value, destination_code=request.destination.code,
        vehicle_profile=request.vehicle_profile.value, distance_km=result.distance_km,
        duration_minutes=result.duration_minutes,
        route_geometry=func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(result.route_geometry)), 4326),
        routing_provider=result.provider_name, provider_route_id=result.provider_route_id,
        calculated_at=calculated_at,
    )
    db.add(route)
    db.commit()
    db.refresh(route)
    return RouteRead(
        route_id=route_id, origin_type=request.origin.type, origin_code=request.origin.code,
        destination_type=request.destination.type, destination_code=request.destination.code,
        vehicle_profile=request.vehicle_profile, distance_km=result.distance_km,
        duration_minutes=result.duration_minutes, route_geometry=result.route_geometry,
        routing_provider=result.provider_name, provider_route_id=result.provider_route_id,
        calculated_at=calculated_at,
    )
