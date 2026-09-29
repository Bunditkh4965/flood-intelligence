from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from geoalchemy2.elements import WKTElement
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.integrations.bma.client import BmaAPIError, BmaClient
from app.models.bma import BmaRoadWaterObservation, BmaSyncRun
from app.schemas.evidence import EvidenceSource, EvidenceType, NormalizedEvidence


@dataclass(frozen=True)
class ParsedObservation:
    source_record_id: str
    longitude: float
    latitude: float
    values: dict[str, Any]


def _text(value: Any, limit: int = 255) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value[:limit] or None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value / 1000, timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    # BMA does not publish a timezone for its wall-clock strings. Preserve that
    # fact rather than incorrectly asserting UTC; explicit offsets stay intact.
    return parsed


def _coordinate_pair(feature: dict[str, Any], attrs: dict[str, Any]) -> tuple[float, float]:
    points = feature.get("geometry", {}).get("points") if isinstance(feature.get("geometry"), dict) else None
    candidates = points if isinstance(points, list) else []
    for point in candidates:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            lon, lat = point[:2]
            if (not isinstance(lon, bool) and not isinstance(lat, bool)
                    and isinstance(lon, (int, float)) and isinstance(lat, (int, float))
                    and -180 <= lon <= 180 and -90 <= lat <= 90):
                return float(lon), float(lat)
    lon, lat = attrs.get("F_LNG"), attrs.get("LAT")
    if (not isinstance(lon, bool) and not isinstance(lat, bool)):
        try:
            lon, lat = float(lon), float(lat)
            if -180 <= lon <= 180 and -90 <= lat <= 90:
                return lon, lat
        except (TypeError, ValueError):
            pass
    raise ValueError("observation has no usable location")


def parse_observation(feature: Any) -> ParsedObservation:
    if not isinstance(feature, dict) or not isinstance(feature.get("attributes"), dict):
        raise ValueError("feature must contain attributes")
    a = feature["attributes"]
    master, station = _text(a.get("MASTER_STATION_ID"), 128), _text(a.get("STATION_ID"), 128)
    oid, oid1 = _text(a.get("OBJECTID"), 128), _text(a.get("OBJECTID_1"), 128)
    if master:
        identity = f"master:{master}"
    elif station:
        identity = f"station:{station}"
    elif oid or oid1:
        identity = f"object:{oid or ''}:{oid1 or ''}"
    else:
        raise ValueError("observation has no stable source identity")
    lon, lat = _coordinate_pair(feature, a)
    return ParsedObservation(identity, lon, lat, {
        "master_station_id": master, "station_id": station, "object_id": oid, "object_id_1": oid1,
        "station_name": _text(a.get("STATION_NAME_TH")), "station_old_code": _text(a.get("STATION_OLDCODE"), 128),
        "road_name": _text(a.get("ROAD_NAME")), "tunnel_description": _text(a.get("TUNNEL_SUB_NAME")),
        "water_level_cm": _number(a.get("WATER_LEVEL_CM")), "source_status": _text(a.get("CHK_STATUSTXT"), 128),
        "observed_at": _datetime(a.get("DATA_DT")), "flood_start_at": _datetime(a.get("FLOOD_START_TH")),
        "flood_stop_at": _datetime(a.get("FLOOD_STOP_TH")), "flood_max_cm": _number(a.get("FLOOD_MAX")),
        "flood_max_at": _datetime(a.get("FLOOD_MAX_TIME")), "agency": _text(a.get("AGENCY_NAME_TH")),
        "api_source": _text(a.get("API_SOURCE"), 64), "province": _text(a.get("PROV_NAM_T"), 128),
        "amphoe": _text(a.get("AMP_NAM_T"), 128), "tambon": _text(a.get("TAM_NAM_T"), 128),
        "source_latitude": lat, "source_longitude": lon, "source_created_at": _datetime(a.get("CREATED_AT")),
        "source_updated_at": _datetime(a.get("UPDATED_AT")),
        "source_metadata": {
            "coordinate_source": "geometry" if isinstance(feature.get("geometry"), dict)
                                 and feature["geometry"].get("points") else "attributes",
            "timestamp_policy": "SOURCE_WALL_CLOCK_UNLESS_OFFSET_SUPPLIED",
            "raw_timestamps": {key: a.get(key) for key in (
                "DATA_DT", "FLOOD_START_TH", "FLOOD_STOP_TH", "FLOOD_MAX_TIME",
                "CREATED_AT", "UPDATED_AT",
            ) if a.get(key) is not None},
        },
    })


def sync_bma_observations(db: Session, client: BmaClient | None = None) -> BmaSyncRun:
    now = datetime.now(timezone.utc)
    run = BmaSyncRun(started_at=now, status="RUNNING")
    db.add(run); db.commit(); db.refresh(run)
    run_id = run.id
    received = rejected = geometry_failures = 0
    try:
        def synchronize(active_client: BmaClient) -> tuple[int, int, int]:
            nonlocal received, rejected, geometry_failures
            parsed: list[ParsedObservation] = []
            seen: set[str] = set()
            for page in active_client.pages():
                received += len(page)
                for feature in page:
                    try:
                        item = parse_observation(feature)
                        if item.source_record_id in seen:
                            raise ValueError("duplicate source identity")
                        seen.add(item.source_record_id); parsed.append(item)
                    except ValueError as exc:
                        rejected += 1
                        if "location" in str(exc):
                            geometry_failures += 1
            existing = {row.source_record_id: row for row in db.scalars(select(BmaRoadWaterObservation))}
            inserted = updated = unchanged = 0
            for item in parsed:
                fingerprint = hashlib.sha256(json.dumps(
                    {**item.values, "longitude": item.longitude, "latitude": item.latitude},
                    sort_keys=True, default=str, separators=(",", ":"),
                ).encode()).hexdigest()
                values = {**item.values, "fingerprint": fingerprint, "is_active": True, "synced_at": now,
                          "location": WKTElement(f"POINT({item.longitude} {item.latitude})", srid=4326)}
                row = existing.get(item.source_record_id)
                if row is None:
                    db.add(BmaRoadWaterObservation(source_record_id=item.source_record_id, **values)); inserted += 1
                elif row.fingerprint == fingerprint and row.is_active:
                    row.synced_at = now; unchanged += 1
                else:
                    for key, value in values.items():
                        setattr(row, key, value)
                    updated += 1
            db.flush()  # synced_at must reach SQL before stale-row retirement.
            if rejected == 0:
                db.execute(update(BmaRoadWaterObservation).where(
                    BmaRoadWaterObservation.is_active.is_(True), BmaRoadWaterObservation.synced_at != now,
                ).values(is_active=False, updated_at=now))
            return inserted, updated, unchanged

        if client is None:
            with BmaClient() as owned:
                inserted, updated, unchanged = synchronize(owned)
        else:
            inserted, updated, unchanged = synchronize(client)
        run.status = "PARTIAL" if rejected else "SUCCESS"
        run.records_received, run.records_rejected = received, rejected
        run.records_inserted, run.records_updated, run.records_unchanged = inserted, updated, unchanged
        run.geometry_failures = geometry_failures
        run.error_message = f"rejected={rejected}; geometry_failures={geometry_failures}" if rejected else None
        run.finished_at = datetime.now(timezone.utc); db.commit(); db.refresh(run)
        return run
    except Exception as exc:
        db.rollback(); failed = db.get(BmaSyncRun, run_id); failed.status = "FAILED"
        failed.finished_at = datetime.now(timezone.utc); failed.records_received = received
        failed.records_rejected = rejected; failed.geometry_failures = geometry_failures; failed.page_failures = 1
        detail = str(exc) if isinstance(exc, (BmaAPIError, ValueError)) else "unexpected synchronization failure"
        failed.error_message = f"{type(exc).__name__}: {detail}"[:4000]
        db.commit(); db.refresh(failed); return failed


def list_observations(db: Session, active: bool | None = True, status: str | None = None,
                      road_name: str | None = None, minimum_water_level: float | None = None,
                      limit: int = 100, offset: int = 0) -> list[BmaRoadWaterObservation]:
    query = select(BmaRoadWaterObservation).order_by(BmaRoadWaterObservation.id)
    if active is not None: query = query.where(BmaRoadWaterObservation.is_active.is_(active))
    if status: query = query.where(BmaRoadWaterObservation.source_status == status)
    if road_name: query = query.where(BmaRoadWaterObservation.road_name.ilike(f"%{road_name}%"))
    if minimum_water_level is not None: query = query.where(BmaRoadWaterObservation.water_level_cm >= minimum_water_level)
    return list(db.scalars(query.limit(limit).offset(offset)))


def normalized_evidence(row: BmaRoadWaterObservation) -> NormalizedEvidence:
    return NormalizedEvidence(source=EvidenceSource.BMA, original_source=row.api_source or "BMA",
        source_record_id=row.source_record_id, evidence_type=EvidenceType.WATER_LEVEL,
        geometry={"type": "Point", "coordinates": [row.source_longitude, row.source_latitude]}, geometry_type="Point",
        observed_at=row.observed_at, updated_at_source=row.source_updated_at, water_depth_cm=row.water_level_cm,
        road_status=None, official_status=False, metadata={"source_status": row.source_status,
            "road_name": row.road_name, "station_name": row.station_name})
