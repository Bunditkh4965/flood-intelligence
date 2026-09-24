from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.flood_report import FloodReportCreate, FloodReportRead, ReportStatus, VerificationStatus
from app.services.flood_reports import create_public_report, get_report, list_reports, serialize_report

router = APIRouter(prefix="/api/v1/flood-reports", tags=["flood-reports"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=FloodReportRead, status_code=status.HTTP_201_CREATED)
def create_flood_report(payload: FloodReportCreate, db: DbSession) -> FloodReportRead:
    """Public, rate-limit-ready endpoint; attach a rate-limit dependency when deployed."""
    return serialize_report(create_public_report(db, payload))


@router.get("", response_model=list[FloodReportRead])
def get_flood_reports(
    db: DbSession, status_filter: ReportStatus | None = Query(None, alias="status"),
    verification_status: VerificationStatus | None = None, reported_from: datetime | None = None,
    reported_to: datetime | None = None, min_latitude: float | None = Query(None, ge=-90, le=90),
    max_latitude: float | None = Query(None, ge=-90, le=90), min_longitude: float | None = Query(None, ge=-180, le=180),
    max_longitude: float | None = Query(None, ge=-180, le=180),
) -> list[FloodReportRead]:
    if min_latitude is not None and max_latitude is not None and min_latitude > max_latitude:
        raise HTTPException(status_code=422, detail="min_latitude must not exceed max_latitude")
    if min_longitude is not None and max_longitude is not None and min_longitude > max_longitude:
        raise HTTPException(status_code=422, detail="min_longitude must not exceed max_longitude")
    return [serialize_report(report) for report in list_reports(db, status=status_filter, verification_status=verification_status, reported_from=reported_from, reported_to=reported_to, min_latitude=min_latitude, max_latitude=max_latitude, min_longitude=min_longitude, max_longitude=max_longitude)]


@router.get("/{report_code}", response_model=FloodReportRead)
def get_flood_report(report_code: str, db: DbSession) -> FloodReportRead:
    report = get_report(db, report_code)
    if report is None:
        raise HTTPException(status_code=404, detail="Flood report not found")
    return serialize_report(report)
