from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.integrations.gistda.client import GistdaClient
from app.models.gistda import GistdaFloodFeature, GistdaSyncRun, PERIODS


@dataclass(frozen=True)
class ParsedFeature:
    external_id: str | None
    geometry: dict[str, Any]
    properties: dict[str, Any]
    source_hash: str
    observed_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True)
class Rejection:
    index: int
    reason: str


def normalize_period(period: str) -> str:
    normalized = period.upper()
    aliases = {"1DAY": "1DAY", "3DAYS": "3DAYS", "7DAYS": "7DAYS", "30DAYS": "30DAYS"}
    if normalized not in aliases:
        raise ValueError(f"Unsupported GISTDA period: {period}")
    return aliases[normalized]


def _date(properties: dict[str, Any], keys: tuple[str, ...]) -> datetime | None:
    for key in keys:
        value = properties.get(key)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def source_hash(geometry: dict[str, Any], properties: dict[str, Any], external_id: str | None) -> str:
    # Prefer the publisher's stable identity. When absent, canonical source
    # content provides repeatable identity without inventing a random ID.
    stable = {"external_feature_id": external_id} if external_id is not None else {"geometry": geometry, "properties": properties}
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def parse_feature(feature: Any) -> ParsedFeature:
    if not isinstance(feature, dict) or feature.get("type") != "Feature":
        raise ValueError("item is not a GeoJSON Feature")
    properties = feature.get("properties")
    if not isinstance(properties, dict):
        raise ValueError("properties must be an object")
    geometry_data = feature.get("geometry")
    if not isinstance(geometry_data, dict):
        raise ValueError("geometry is missing")
    if geometry_data.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("unsupported geometry type")
    coordinates = geometry_data.get("coordinates")
    polygons = [coordinates] if geometry_data["type"] == "Polygon" else coordinates
    if not isinstance(polygons, list) or not polygons:
        raise ValueError("coordinates are malformed")
    try:
        for polygon in polygons:
            if not isinstance(polygon, list) or not polygon:
                raise ValueError
            for ring in polygon:
                if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                    raise ValueError
                for position in ring:
                    if not isinstance(position, list) or len(position) < 2:
                        raise ValueError
                    longitude, latitude = position[:2]
                    if isinstance(longitude, bool) or isinstance(latitude, bool):
                        raise ValueError
                    if not isinstance(longitude, (int, float)) or not isinstance(latitude, (int, float)):
                        raise ValueError
                    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
                        raise ValueError("bounds")
    except (TypeError, ValueError) as exc:
        if str(exc) == "bounds":
            raise ValueError("coordinates are outside WGS84 longitude/latitude bounds") from None
        raise ValueError("coordinates are malformed or rings are not closed") from None
    geometry = {"type": "MultiPolygon", "coordinates": polygons}
    identifier = feature.get("id")
    external_id = str(identifier) if identifier is not None else None
    return ParsedFeature(
        external_id=external_id, geometry=geometry, properties=properties,
        source_hash=source_hash(geometry, properties, external_id),
        observed_at=_date(properties, ("observed_at", "observedAt", "observation_date", "date")),
        updated_at=_date(properties, ("updated_at", "updatedAt", "last_updated")),
    )


def _multipolygon_wkt(geometry: dict[str, Any]) -> str:
    def ring_text(ring: list[list[float]]) -> str:
        return "(" + ",".join(f"{point[0]} {point[1]}" for point in ring) + ")"
    polygons = ["(" + ",".join(ring_text(ring) for ring in polygon) + ")" for polygon in geometry["coordinates"]]
    return "MULTIPOLYGON(" + ",".join(polygons) + ")"


def parse_collection(payload: dict[str, Any]) -> tuple[list[ParsedFeature], list[Rejection], int]:
    if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
        raise ValueError("response is not a GeoJSON FeatureCollection")
    parsed, rejected, seen = [], [], set()
    for index, feature in enumerate(payload["features"]):
        try:
            item = parse_feature(feature)
            if item.source_hash in seen:
                raise ValueError("duplicate feature identity")
            seen.add(item.source_hash)
            parsed.append(item)
        except ValueError as exc:
            rejected.append(Rejection(index=index, reason=str(exc)))
    return parsed, rejected, len(payload["features"])


def sync_gistda_flood(db: Session, period: str, client: GistdaClient | None = None) -> GistdaSyncRun:
    normalized = normalize_period(period)
    now = datetime.now(timezone.utc)
    run = GistdaSyncRun(period=normalized, started_at=now, status="RUNNING")
    db.add(run)
    db.commit()
    try:
        if client is None:
            with GistdaClient() as owned_client:
                payload = owned_client.fetch_flood_features(normalized)
        else:
            payload = client.fetch_flood_features(normalized)
        parsed, rejected, received = parse_collection(payload)
        if received == 0 or not parsed:
            raise ValueError("response contains no usable flood features")

        existing = {item.source_hash: item for item in db.scalars(select(GistdaFloodFeature).where(GistdaFloodFeature.period == normalized))}
        active_hashes: set[str] = set()
        inserted = updated = unchanged = 0
        for item in parsed:
            active_hashes.add(item.source_hash)
            row = existing.get(item.source_hash)
            if row is None:
                db.add(GistdaFloodFeature(
                    external_feature_id=item.external_id, period=normalized,
                    geometry=WKTElement(_multipolygon_wkt(item.geometry), srid=4326), source="GISTDA",
                    source_observed_at=item.observed_at, source_updated_at=item.updated_at,
                    synced_at=now, source_properties=item.properties,
                    source_hash=item.source_hash, is_active=True,
                ))
                inserted += 1
            elif (not row.is_active or row.source_properties != item.properties
                  or row.source_observed_at != item.observed_at or row.source_updated_at != item.updated_at):
                row.is_active = True
                row.synced_at = now
                row.geometry = WKTElement(_multipolygon_wkt(item.geometry), srid=4326)
                row.source_properties = item.properties
                row.source_observed_at = item.observed_at
                row.source_updated_at = item.updated_at
                updated += 1
            else:
                row.synced_at = now
                unchanged += 1
        # Only a completely valid snapshot can retire missing rows. During a
        # partial import, an old row may correspond to the rejected feature.
        if not rejected:
            db.execute(update(GistdaFloodFeature).where(
                GistdaFloodFeature.period == normalized,
                GistdaFloodFeature.is_active.is_(True),
                GistdaFloodFeature.source_hash.not_in(active_hashes),
            ).values(is_active=False, updated_at=now))
        run.status = "PARTIAL" if rejected else "SUCCESS"
        run.records_received = received
        run.records_inserted, run.records_updated, run.records_unchanged = inserted, updated, unchanged
        run.records_rejected = len(rejected)
        run.error_message = "; ".join(f"feature {r.index}: {r.reason}" for r in rejected)[:4000] or None
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)
        return run
    except Exception as exc:
        db.rollback()
        failed = db.get(GistdaSyncRun, run.id)
        failed.status = "FAILED"
        failed.finished_at = datetime.now(timezone.utc)
        failed.error_message = f"{type(exc).__name__}: {str(exc)}"[:4000]
        db.commit()
        db.refresh(failed)
        return failed


def list_features(db: Session, period: str | None, active: bool | None) -> list[tuple[GistdaFloodFeature, dict[str, Any]]]:
    query = select(GistdaFloodFeature, func.ST_AsGeoJSON(GistdaFloodFeature.geometry))
    if period:
        query = query.where(GistdaFloodFeature.period == normalize_period(period))
    if active is not None:
        query = query.where(GistdaFloodFeature.is_active == active)
    return [(row, json.loads(geojson) if isinstance(geojson, str) else geojson) for row, geojson in db.execute(query.order_by(GistdaFloodFeature.id))]


def status_rows(db: Session) -> list[dict[str, Any]]:
    output = []
    for period in PERIODS:
        latest = db.scalar(select(GistdaSyncRun).where(GistdaSyncRun.period == period).order_by(GistdaSyncRun.started_at.desc()).limit(1))
        last_success = db.scalar(select(func.max(GistdaSyncRun.finished_at)).where(GistdaSyncRun.period == period, GistdaSyncRun.status.in_(("SUCCESS", "PARTIAL"))))
        count = db.scalar(select(func.count()).select_from(GistdaFloodFeature).where(GistdaFloodFeature.period == period, GistdaFloodFeature.is_active.is_(True))) or 0
        output.append({"period": period, "sync_status": latest.status if latest else None, "last_successful_sync": last_success, "feature_count": count})
    return output
