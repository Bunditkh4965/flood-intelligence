from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.hdms import HdmsIncidentRead
from app.services.hdms import get_incident, list_incidents

router = APIRouter(prefix="/api/v1/hdms", tags=["hdms"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/incidents", response_model=list[HdmsIncidentRead])
def hdms_incidents(db: DbSession, active: bool | None = Query(True)) -> list[HdmsIncidentRead]:
    return [HdmsIncidentRead.model_validate(item) for item in list_incidents(db, active)]


@router.get("/incidents/{incident_id}", response_model=HdmsIncidentRead)
def hdms_incident(incident_id: int, db: DbSession) -> HdmsIncidentRead:
    item = get_incident(db, incident_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={
            "code": "HDMS_INCIDENT_NOT_FOUND", "message": f"HDMS incident '{incident_id}' was not found",
        })
    return HdmsIncidentRead.model_validate(item)
