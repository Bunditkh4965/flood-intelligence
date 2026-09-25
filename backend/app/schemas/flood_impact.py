from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.gistda import PERIODS


class ImpactClassification(StrEnum):
    DIRECT = "DIRECT"
    NEARBY = "NEARBY"
    NONE = "NONE"


class BranchFloodImpact(BaseModel):
    store_number: str
    store_name: str
    city: str
    latitude: float
    longitude: float
    branch_status: str
    impact_classification: ImpactClassification
    inside_flood_polygon: bool
    nearest_flood_distance_km: float | None
    nearest_flood_feature_id: int | None
    gistda_period: str


class ImpactSummary(BaseModel):
    direct: int = 0
    nearby: int = 0
    none: int = 0


class BranchFloodImpactResponse(BaseModel):
    period: str
    proximity_km: float = Field(gt=0, le=500)
    data_available: bool
    summary: ImpactSummary
    limit: int
    offset: int
    items: list[BranchFloodImpact]


class SingleBranchFloodImpactResponse(BaseModel):
    period: str
    proximity_km: float = Field(gt=0, le=500)
    data_available: bool
    item: BranchFloodImpact


Period = str
VALID_PERIODS = PERIODS
