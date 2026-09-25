from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.transport import DistributionCenterCreate, DistributionCenterRead
from app.services.distribution_centers import (
    DuplicateDistributionCenter, create_distribution_center, get_distribution_center, list_distribution_centers,
)

router = APIRouter(prefix="/api/v1/distribution-centers", tags=["distribution-centers"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[DistributionCenterRead])
def distribution_centers(db: DbSession) -> list[DistributionCenterRead]:
    return list_distribution_centers(db)


@router.get("/{dc_code}", response_model=DistributionCenterRead)
def distribution_center(dc_code: str, db: DbSession) -> DistributionCenterRead:
    dc = get_distribution_center(db, dc_code)
    if dc is None:
        raise HTTPException(status_code=404, detail={"code": "DC_NOT_FOUND", "message": "Distribution center not found"})
    return dc


@router.post("", response_model=DistributionCenterRead, status_code=status.HTTP_201_CREATED)
def add_distribution_center(payload: DistributionCenterCreate, db: DbSession) -> DistributionCenterRead:
    try:
        return create_distribution_center(db, payload)
    except DuplicateDistributionCenter as exc:
        raise HTTPException(status_code=409, detail={"code": "DUPLICATE_DC_CODE", "message": "dc_code already exists"}) from exc
