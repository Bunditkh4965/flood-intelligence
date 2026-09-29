from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from geoalchemy2.elements import WKTElement
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.integrations.hdms.client import HdmsAPIError, HdmsClient
from app.models.hdms import HdmsIncident, HdmsSyncRun

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParsedIncident:
    source_record_id: str
    values: dict[str, Any]


def normalize_road_status(lane_closure: Any) -> str:
    # HDMS's field name is misleading: true is officially passable.
    if lane_closure is True:
        return "PASSABLE"
    if lane_closure is False:
        return "IMPASSABLE"
    return "UNKNOWN"


def _text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result[:limit] or None


def _datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _depth(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _source_identity(record: dict[str, Any]) -> str:
    case_id = _text(record.get("case_id"), 128)
    if case_id:
        return f"case:{case_id}"
    gid = _text(record.get("gid"), 128)
    if gid:
        return f"gid:{gid}"
    stable = {key: record.get(key) for key in (
        "road_code", "section_code", "km_start", "km_end", "start_date", "incident_type_id",
    )}
    if not any(value not in (None, "") for value in stable.values()):
        raise ValueError("record has no stable source identity")
    digest = hashlib.sha256(json.dumps(stable, sort_keys=True, default=str).encode()).hexdigest()
    return f"fallback:{digest}"


def parse_incident(record: Any) -> ParsedIncident:
    if not isinstance(record, dict):
        raise ValueError("incident must be an object")
    metadata = {key: record.get(key) for key in (
        "ticketType", "incident_type_id", "cause_of_roads_closure_id", "risk_area",
        "section_status", "publish", "end_date",
    ) if key in record}
    return ParsedIncident(_source_identity(record), {
        "case_id": _text(record.get("case_id"), 128),
        "gid": _text(record.get("gid"), 128),
        "road_code": _text(record.get("road_code"), 32),
        "section_code": _text(record.get("section_code"), 32),
        "section_name": _text(record.get("section_name"), 255),
        "km_start": _text(record.get("km_start"), 32),
        "km_end": _text(record.get("km_end"), 32),
        "province": _text(record.get("province"), 128),
        "amphoe": _text(record.get("amphoe"), 128),
        "tambon": _text(record.get("tambon"), 128),
        "water_depth_cm": _depth(record.get("flood_level")),
        "road_status": normalize_road_status(record.get("lane_closure")),
        "incident_at": _datetime(record.get("start_date")),
        "report_at": _datetime(record.get("report_date")),
        "source_updated_at": _datetime(record.get("updated_date")),
        "survey_at": _datetime(record.get("survey_date")),
        "source_status": _text(record.get("status"), 64),
        "source_metadata": metadata,
    })


def parse_linestring(payload: Any) -> dict[str, Any]:
    geometry = payload.get("geom") if isinstance(payload, dict) else None
    if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
        raise ValueError("HDMS section geometry is not a LineString")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise ValueError("HDMS LineString requires at least two positions")
    normalized = []
    for position in coordinates:
        if not isinstance(position, list) or len(position) < 2:
            raise ValueError("HDMS LineString position is malformed")
        lon, lat = position[:2]
        if (isinstance(lon, bool) or isinstance(lat, bool)
                or not isinstance(lon, (int, float)) or not isinstance(lat, (int, float))
                or not -180 <= lon <= 180 or not -90 <= lat <= 90):
            raise ValueError("HDMS LineString position is outside lon/lat bounds")
        normalized.append([float(lon), float(lat)])
    return {"type": "LineString", "coordinates": normalized}


def _linestring_wkt(geometry: dict[str, Any]) -> str:
    return "LINESTRING(" + ",".join(f"{lon} {lat}" for lon, lat in geometry["coordinates"]) + ")"


def _dashboard_records(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "results", "items"):
            if isinstance(payload.get(key), list):
                return payload[key]
    raise ValueError("HDMS dashboard response does not contain an incident array")


def sync_hdms_incidents(db: Session, start: date, end: date,
                        client: HdmsClient | None = None) -> HdmsSyncRun:
    now = datetime.now(timezone.utc)
    run = HdmsSyncRun(started_at=now, status="RUNNING")
    db.add(run)
    db.commit()
    db.refresh(run)
    run_id = run.id
    received = rejected = geometry_failures = 0
    try:
        def synchronize(active_client: HdmsClient) -> tuple[int, int, int]:
            nonlocal received, rejected, geometry_failures
            records = _dashboard_records(active_client.fetch_dashboard(start, end))
            received = len(records)
            parsed: list[tuple[ParsedIncident, dict[str, Any] | None]] = []
            seen: set[str] = set()
            for record in records:
                try:
                    incident = parse_incident(record)
                    if incident.source_record_id in seen:
                        raise ValueError("duplicate incident identity")
                    seen.add(incident.source_record_id)
                except ValueError:
                    rejected += 1
                    continue
                geometry = None
                fields = incident.values
                required = (fields["road_code"], fields["section_code"], fields["km_start"], fields["km_end"])
                if all(required):
                    try:
                        geometry = parse_linestring(active_client.fetch_section_geometry(*required))
                    except (HdmsAPIError, ValueError):
                        geometry_failures += 1
                        logger.warning("HDMS geometry unavailable source_record_id=%s", incident.source_record_id)
                parsed.append((incident, geometry))

            existing = {row.source_record_id: row for row in db.scalars(select(HdmsIncident))}
            inserted = updated = unchanged = 0
            for incident, geometry in parsed:
                values = dict(incident.values)
                fingerprint_input = {**values, "geometry": geometry}
                fingerprint = hashlib.sha256(json.dumps(
                    fingerprint_input, sort_keys=True, default=str, separators=(",", ":"),
                ).encode()).hexdigest()
                values["source_metadata"] = {**values["source_metadata"], "_fingerprint": fingerprint}
                values.update(is_active=True, geometry_available=geometry is not None, synced_at=now,
                              road_geometry=WKTElement(_linestring_wkt(geometry), srid=4326) if geometry else None)
                row = existing.get(incident.source_record_id)
                if row is None:
                    db.add(HdmsIncident(source_record_id=incident.source_record_id, **values)); inserted += 1
                elif row.source_metadata.get("_fingerprint") == fingerprint and row.is_active:
                    row.synced_at = now; unchanged += 1
                else:
                    for key, value in values.items():
                        setattr(row, key, value)
                    updated += 1
            db.flush()
            # A partially malformed dashboard is not trusted to retire history.
            if rejected == 0:
                db.execute(update(HdmsIncident).where(
                    HdmsIncident.is_active.is_(True), HdmsIncident.synced_at != now,
                ).values(is_active=False, updated_at=now))
            return inserted, updated, unchanged

        if client is None:
            with HdmsClient() as owned:
                inserted, updated, unchanged = synchronize(owned)
        else:
            inserted, updated, unchanged = synchronize(client)
        run.status = "PARTIAL" if rejected or geometry_failures else "SUCCESS"
        run.records_received, run.records_rejected = received, rejected
        run.records_inserted, run.records_updated, run.records_unchanged = inserted, updated, unchanged
        run.geometry_failures = geometry_failures
        run.error_message = (
            f"rejected={rejected}; geometry_unavailable={geometry_failures}" if rejected or geometry_failures else None
        )
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)
        return run
    except Exception as exc:
        db.rollback()
        failed = db.get(HdmsSyncRun, run_id)
        failed.status = "FAILED"
        failed.finished_at = datetime.now(timezone.utc)
        failed.records_received = received
        failed.records_rejected = rejected
        failed.geometry_failures = geometry_failures
        detail = str(exc) if isinstance(exc, (HdmsAPIError, ValueError)) else "unexpected synchronization failure"
        failed.error_message = f"{type(exc).__name__}: {detail}"[:4000]
        db.commit()
        db.refresh(failed)
        return failed


def list_incidents(db: Session, active: bool | None = True) -> list[HdmsIncident]:
    query = select(HdmsIncident).order_by(HdmsIncident.id)
    if active is not None:
        query = query.where(HdmsIncident.is_active.is_(active))
    return list(db.scalars(query))


def get_incident(db: Session, incident_id: int) -> HdmsIncident | None:
    return db.get(HdmsIncident, incident_id)

