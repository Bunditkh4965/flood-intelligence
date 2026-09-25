from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core import get_settings
from app.db.session import get_db
from app.routing.provider import RoutingProvider, RoutingProviderError, RoutingProviderNotConfigured, get_routing_provider
from app.schemas.route_flood_impact import RouteFloodImpact
from app.schemas.transport import RouteCalculateRequest, RouteRead
from app.services.route_flood_impact import InvalidRouteGeometry, evaluate_route_flood_impact
from app.services.routes import RouteLocationError, calculate_and_store_route

router = APIRouter(prefix="/api/v1/routes", tags=["routes"])
DbSession = Annotated[Session, Depends(get_db)]
Provider = Annotated[RoutingProvider, Depends(get_routing_provider)]


@router.post("/calculate", response_model=RouteRead)
def calculate_route(payload: RouteCalculateRequest, db: DbSession, provider: Provider) -> RouteRead:
    try:
        return calculate_and_store_route(db, payload, provider)
    except RoutingProviderNotConfigured as exc:
        raise HTTPException(status_code=503, detail={"code": "ROUTING_PROVIDER_NOT_CONFIGURED", "message": str(exc)}) from exc
    except RoutingProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc
    except RouteLocationError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc


@router.get("/{route_id}/flood-impact", response_model=RouteFloodImpact)
def route_flood_impact(route_id: str, db: DbSession) -> RouteFloodImpact:
    settings = get_settings()
    try:
        result = evaluate_route_flood_impact(
            db, route_id, settings.route_impact_gistda_period,
            settings.public_route_impact_radius_meters,
            settings.route_impact_public_lookback_hours,
        )
    except InvalidRouteGeometry as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
            detail={"code": "ROUTE_GEOMETRY_INVALID", "message": str(exc)}) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ROUTE_NOT_FOUND", "message": f"Route '{route_id}' was not found"})
    return RouteFloodImpact.model_validate(result)
