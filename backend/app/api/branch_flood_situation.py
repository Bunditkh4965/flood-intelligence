from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.branch_flood_situation import (
    BranchFloodSituation, BranchFloodSituationResponse, SituationCategory,
)
from app.services.branch_flood_situation import calculate_situation, calculate_situations

router = APIRouter(prefix="/api/v1/branch-flood-situation", tags=["branch-flood-situation"])
DbSession = Annotated[Session, Depends(get_db)]
Period = Literal["1DAY", "3DAYS", "7DAYS", "30DAYS"]


@router.get("", response_model=BranchFloodSituationResponse)
def list_situations(
    db: DbSession, period: Period = "3DAYS",
    gistda_proximity_km: float = Query(..., gt=0, le=500),
    public_proximity_km: float = Query(..., gt=0, le=100),
    public_lookback_hours: int = Query(24, gt=0, le=168),
    situation: SituationCategory | None = None,
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
) -> BranchFloodSituationResponse:
    page = calculate_situations(db, period, gistda_proximity_km, public_proximity_km,
                                public_lookback_hours, situation, limit, offset)
    return BranchFloodSituationResponse(
        period=period, gistda_proximity_km=gistda_proximity_km,
        public_proximity_km=public_proximity_km,
        public_lookback_hours=public_lookback_hours, summary=page.summary,
        limit=limit, offset=offset, items=page.items,
    )


@router.get("/{store_number}", response_model=BranchFloodSituation)
def get_situation(
    store_number: str, db: DbSession, period: Period = "3DAYS",
    gistda_proximity_km: float = Query(..., gt=0, le=500),
    public_proximity_km: float = Query(..., gt=0, le=100),
    public_lookback_hours: int = Query(24, gt=0, le=168),
) -> BranchFloodSituation:
    item = calculate_situation(db, store_number, period, gistda_proximity_km,
                               public_proximity_km, public_lookback_hours)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
    return BranchFloodSituation.model_validate(item)
