from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.public_flood_impact import (
    PublicBranchImpactResponse, PublicImpactClassification, SinglePublicBranchImpactResponse,
)
from app.services.public_flood_impact import (
    calculate_public_branch_impact, calculate_public_branch_impacts,
)

router = APIRouter(prefix="/api/v1/public-flood-impact", tags=["public-flood-impact"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/branches", response_model=PublicBranchImpactResponse)
def branch_impacts(
    db: DbSession,
    proximity_km: float = Query(..., gt=0, le=100),
    lookback_hours: int = Query(24, gt=0, le=168),
    classification: PublicImpactClassification | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> PublicBranchImpactResponse:
    page = calculate_public_branch_impacts(
        db, proximity_km, lookback_hours, classification, limit, offset
    )
    return PublicBranchImpactResponse(
        proximity_km=proximity_km, lookback_hours=lookback_hours,
        data_available=page.data_available, summary=page.summary,
        limit=limit, offset=offset, items=page.items,
    )


@router.get("/branches/{store_number}", response_model=SinglePublicBranchImpactResponse)
def branch_impact(
    store_number: str,
    db: DbSession,
    proximity_km: float = Query(..., gt=0, le=100),
    lookback_hours: int = Query(24, gt=0, le=168),
) -> SinglePublicBranchImpactResponse:
    result = calculate_public_branch_impact(db, store_number, proximity_km, lookback_hours)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
    available, item = result
    return SinglePublicBranchImpactResponse(
        proximity_km=proximity_km, lookback_hours=lookback_hours,
        data_available=available, item=item,
    )
