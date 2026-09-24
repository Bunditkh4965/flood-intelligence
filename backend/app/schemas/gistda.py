from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class GistdaFeatureProperties(BaseModel):
    id: int
    external_feature_id: str | None
    period: Literal["1DAY", "3DAYS", "7DAYS", "30DAYS"]
    source: Literal["GISTDA"]
    source_observed_at: datetime | None
    source_updated_at: datetime | None
    synced_at: datetime
    source_properties: dict[str, Any]
    source_hash: str
    is_active: bool


class GeoJSONFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any]
    properties: GistdaFeatureProperties


class GeoJSONFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[GeoJSONFeature]


class GistdaStatus(BaseModel):
    period: str
    last_successful_sync: datetime | None
    feature_count: int
    sync_status: str | None
