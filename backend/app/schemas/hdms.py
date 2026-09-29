from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class HdmsIncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_record_id: str
    case_id: str | None
    gid: str | None
    road_code: str | None
    section_code: str | None
    section_name: str | None
    km_start: str | None
    km_end: str | None
    province: str | None
    amphoe: str | None
    tambon: str | None
    water_depth_cm: float | None
    road_status: Literal["PASSABLE", "IMPASSABLE", "UNKNOWN"]
    incident_at: datetime | None
    report_at: datetime | None
    source_updated_at: datetime | None
    survey_at: datetime | None
    source_status: str | None
    is_active: bool
    geometry_available: bool
    synced_at: datetime
    created_at: datetime
    updated_at: datetime
