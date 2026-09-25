from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.routing.provider import RoutingProvider, RoutingProviderError, RoutingProviderNotConfigured, get_routing_provider
from app.schemas.transport import RouteCalculateRequest, RouteRead
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
