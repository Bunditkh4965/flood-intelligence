from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core import get_settings
from app.schemas.flood_report import FloodReportCreate, FloodReportPhotoRead, FloodReportRead, ReportStatus, VerificationStatus
from app.services.flood_reports import create_public_report, get_report, list_reports, record_photo_and_recalculate, serialize_report
from app.services.photo_storage import InvalidPhoto, LocalPhotoStorage

router = APIRouter(prefix="/api/v1/flood-reports", tags=["flood-reports"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=FloodReportRead, status_code=status.HTTP_201_CREATED)
def create_flood_report(payload: FloodReportCreate, db: DbSession) -> FloodReportRead:
    """Public, rate-limit-ready endpoint; attach a rate-limit dependency when deployed."""
    return serialize_report(create_public_report(db, payload))


@router.post("/{report_code}/photos", response_model=FloodReportPhotoRead, status_code=status.HTTP_201_CREATED)
async def upload_flood_report_photo(report_code: str, request: Request, db: DbSession) -> FloodReportPhotoRead:
    report = get_report(db, report_code)
    if report is None:
        raise HTTPException(status_code=404, detail="Flood report not found")
    settings = get_settings()
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("multipart/form-data") or "boundary=" not in content_type:
        raise HTTPException(status_code=415, detail="multipart photo is required")
    boundary = content_type.split("boundary=", 1)[1].strip().strip('"').encode()
    chunks: list[bytes] = []
    body_size = 0
    # Bound memory before joining the request; allowance covers multipart headers.
    async for chunk in request.stream():
        body_size += len(chunk)
        if body_size > settings.photo_max_bytes + 16_384:
            raise HTTPException(status_code=413, detail="photo exceeds the configured size limit")
        chunks.append(chunk)
    body = b"".join(chunks)
    parts = body.split(b"--" + boundary)
    data = b""
    for part in parts:
        headers, marker, candidate = part.partition(b"\r\n\r\n")
        if marker and b'name="photo"' in headers:
            data = candidate.removesuffix(b"\r\n")
            break
    storage = LocalPhotoStorage(settings.photo_storage_directory, settings.photo_max_bytes)
    try:
        stored = storage.save(data)
    except InvalidPhoto as exc:
        raise HTTPException(status_code=415 if len(data) <= settings.photo_max_bytes else 413, detail=str(exc)) from exc
    try:
        record_photo_and_recalculate(db, report, storage_key=stored.key, content_type=stored.content_type, file_size=stored.size)
    except Exception:
        db.rollback()
        storage.delete(stored.key)
        raise
    return FloodReportPhotoRead(report_code=report.report_code, has_photo=True, verification_status=report.verification_status, verification_reason=report.verification_reason)


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
