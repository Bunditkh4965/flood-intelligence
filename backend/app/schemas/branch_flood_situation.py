"""Contracts for factual, source-separated branch flood situations."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas.flood_impact import ImpactClassification
from app.schemas.public_flood_impact import PublicImpactClassification


class SituationCategory(StrEnum):
    GISTDA_DIRECT = "GISTDA_DIRECT"
    MULTI_SOURCE_NEARBY = "MULTI_SOURCE_NEARBY"
    GISTDA_NEARBY = "GISTDA_NEARBY"
    PUBLIC_NEARBY = "PUBLIC_NEARBY"
    NO_NEARBY_FLOOD = "NO_NEARBY_FLOOD"
    SOURCE_DATA_INCOMPLETE = "SOURCE_DATA_INCOMPLETE"


class GistdaSituation(BaseModel):
    data_available: bool
    period: str
    classification: ImpactClassification | None
    inside_flood_polygon: bool
    nearest_flood_distance_km: float | None
    nearest_flood_feature_id: int | None


class PublicSituation(BaseModel):
    data_available: bool
    lookback_hours: int
    classification: PublicImpactClassification | None
    nearest_report_code: str | None
    nearest_report_distance_km: float | None
    nearest_report_verification_status: str | None
    nearest_report_reported_at: datetime | None


class BranchFloodSituation(BaseModel):
    store_number: str
    store_name: str
    city: str
    latitude: float
    longitude: float
    situation: SituationCategory
    gistda: GistdaSituation
    public: PublicSituation


class SituationSummary(BaseModel):
    gistda_direct: int = 0
    multi_source_nearby: int = 0
    gistda_nearby: int = 0
    public_nearby: int = 0
    no_nearby_flood: int = 0
    source_data_incomplete: int = 0


class BranchFloodSituationResponse(BaseModel):
    period: str
    gistda_proximity_km: float = Field(gt=0, le=500)
    public_proximity_km: float = Field(gt=0, le=100)
    public_lookback_hours: int = Field(gt=0, le=168)
    summary: SituationSummary
    limit: int
    offset: int
    items: list[BranchFloodSituation]
