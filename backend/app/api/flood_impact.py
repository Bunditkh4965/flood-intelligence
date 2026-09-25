from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.flood_impact import (
    BranchFloodImpactResponse, ImpactClassification, SingleBranchFloodImpactResponse,
)
from app.services.flood_impact import calculate_branch_impact, calculate_branch_impacts

router = APIRouter(prefix="/api/v1/flood-impact", tags=["flood-impact"])
DbSession = Annotated[Session, Depends(get_db)]
Period = Literal["1DAY", "3DAYS", "7DAYS", "30DAYS"]


@router.get("/branches", response_model=BranchFloodImpactResponse)
def branch_impacts(
    db: DbSession,
    period: Period = "3DAYS",
    proximity_km: float = Query(10, gt=0, le=500),
    classification: ImpactClassification | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> BranchFloodImpactResponse:
    page = calculate_branch_impacts(db, period, proximity_km, classification, limit, offset)
    return BranchFloodImpactResponse(period=period, proximity_km=proximity_km,
                                     data_available=page.data_available, summary=page.summary,
                                     limit=limit, offset=offset, items=page.items)


@router.get("/branches/{store_number}", response_model=SingleBranchFloodImpactResponse)
def branch_impact(
    store_number: str,
    db: DbSession,
    period: Period = "3DAYS",
    proximity_km: float = Query(10, gt=0, le=500),
) -> SingleBranchFloodImpactResponse:
    result = calculate_branch_impact(db, store_number, period, proximity_km)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
    available, item = result
    return SingleBranchFloodImpactResponse(period=period, proximity_km=proximity_km,
                                           data_available=available, item=item)
