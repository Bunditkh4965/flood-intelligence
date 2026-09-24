from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.branch import BranchRead, NearbyBranchRead
from app.services.branches import find_nearby_branches, get_branch_by_store_number, list_branches

router = APIRouter(prefix="/api/v1/branches", tags=["branches"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/nearby", response_model=list[NearbyBranchRead])
def nearby_branches(
    db: DbSession,
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    radius_km: float = Query(gt=0, le=500),
) -> list[NearbyBranchRead]:
    return find_nearby_branches(db, lat, lng, radius_km)


@router.get("/{store_number}", response_model=BranchRead)
def get_branch(store_number: str, db: DbSession) -> BranchRead:
    branch = get_branch_by_store_number(db, store_number)
    if branch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
    return branch


@router.get("", response_model=list[BranchRead])
def branches(db: DbSession) -> list[BranchRead]:
    return list_branches(db)
