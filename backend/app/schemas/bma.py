from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BmaRoadWaterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_record_id: str
    master_station_id: str | None
    station_id: str | None
    station_name: str | None
    station_old_code: str | None
    road_name: str | None
    tunnel_description: str | None
    water_level_cm: float | None
    source_status: str | None
    observed_at: datetime | None
    flood_start_at: datetime | None
    flood_stop_at: datetime | None
    flood_max_cm: float | None
    flood_max_at: datetime | None
    agency: str | None
    api_source: str | None
    province: str | None
    amphoe: str | None
    tambon: str | None
    source_latitude: float
    source_longitude: float
    source_created_at: datetime | None
    source_updated_at: datetime | None
    is_active: bool
    synced_at: datetime
    created_at: datetime
    updated_at: datetime
Completely output file numbers: 1–10.

Remaining file numbers: 11–20.
