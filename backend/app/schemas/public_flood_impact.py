"""API contracts for public-observation branch proximity results."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class PublicImpactClassification(StrEnum):
    PUBLIC_NEARBY = "PUBLIC_NEARBY"
    PUBLIC_NONE = "PUBLIC_NONE"


class PublicBranchImpact(BaseModel):
    store_number: str
    store_name: str
    city: str
    latitude: float
    longitude: float
    branch_status: str
    public_impact_classification: PublicImpactClassification
    nearest_report_code: str | None
    nearest_report_distance_km: float | None
    nearest_report_verification_status: str | None
    nearest_report_reported_at: datetime | None
    source: str = "PUBLIC"


class PublicImpactSummary(BaseModel):
    nearby: int = 0
    none: int = 0


class PublicBranchImpactResponse(BaseModel):
    source: str = "PUBLIC"
    proximity_km: float = Field(gt=0, le=100)
    lookback_hours: int = Field(gt=0, le=168)
    data_available: bool
    summary: PublicImpactSummary
    limit: int
    offset: int
    items: list[PublicBranchImpact]


class SinglePublicBranchImpactResponse(BaseModel):
    source: str = "PUBLIC"
    proximity_km: float = Field(gt=0, le=100)
    lookback_hours: int = Field(gt=0, le=168)
    data_available: bool
    item: PublicBranchImpact
