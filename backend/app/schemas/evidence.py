"""Provider-neutral evidence vocabulary for current and future source adapters."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class EvidenceSource(StrEnum):
    GISTDA = "GISTDA"
    PUBLIC = "PUBLIC"
    HDMS = "HDMS"
    BMA = "BMA"


class EvidenceType(StrEnum):
    FLOOD_AREA = "FLOOD_AREA"
    ROAD_FLOOD = "ROAD_FLOOD"
    ROAD_IMPASSABLE = "ROAD_IMPASSABLE"
    ROAD_PASSABLE = "ROAD_PASSABLE"
    PUBLIC_FLOOD_REPORT = "PUBLIC_FLOOD_REPORT"
    WATER_LEVEL = "WATER_LEVEL"


class OfficialRoadStatus(StrEnum):
    PASSABLE = "PASSABLE"
    IMPASSABLE = "IMPASSABLE"
    UNKNOWN = "UNKNOWN"


class NormalizedEvidence(BaseModel):
    """Read-only cross-source projection; source tables remain authoritative."""

    source: EvidenceSource
    original_source: str
    source_record_id: str
    evidence_type: EvidenceType
    geometry: dict[str, Any] | None
    geometry_type: str | None
    observed_at: datetime | None
    updated_at_source: datetime | None
    water_depth_cm: float | None
    road_status: OfficialRoadStatus | None
    official_status: bool
    metadata: dict[str, Any]
