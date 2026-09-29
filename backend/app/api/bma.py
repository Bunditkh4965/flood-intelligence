from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.bma import BmaRoadWaterObservation
from app.schemas.bma import BmaRoadWaterRead
from app.services.bma import list_observations

router = APIRouter(prefix="/api/v1/bma", tags=["bma"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/road-water", response_model=list[BmaRoadWaterRead])
def road_water(db: DbSession, active: bool | None = Query(True), status_text: str | None = Query(None, alias="status"),
               road_name: str | None = None, minimum_water_level: float | None = Query(None, ge=0),
               limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)) -> list[BmaRoadWaterRead]:
    return [BmaRoadWaterRead.model_validate(row) for row in list_observations(
        db, active, status_text, road_name, minimum_water_level, limit, offset)]


@router.get("/road-water/{observation_id}", response_model=BmaRoadWaterRead)
def road_water_observation(observation_id: int, db: DbSession) -> BmaRoadWaterRead:
    row = db.get(BmaRoadWaterObservation, observation_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={
            "code": "BMA_OBSERVATION_NOT_FOUND", "message": f"BMA observation '{observation_id}' was not found"})
    return BmaRoadWaterRead.model_validate(row)
