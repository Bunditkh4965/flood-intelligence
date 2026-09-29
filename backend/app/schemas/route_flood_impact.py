"""Provider-neutral factual evidence detected against a persisted road route."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas.transport import RouteEndpoint, VehicleProfile


class RouteFloodSituation(StrEnum):
    GISTDA_DIRECT = "GISTDA_DIRECT"
    MULTI_SOURCE_ROUTE_IMPACT = "MULTI_SOURCE_ROUTE_IMPACT"
    PUBLIC_NEARBY_ROUTE = "PUBLIC_NEARBY_ROUTE"
    NO_DETECTED_ROUTE_IMPACT = "NO_DETECTED_ROUTE_IMPACT"
    SOURCE_DATA_INCOMPLETE = "SOURCE_DATA_INCOMPLETE"


class GistdaRouteEvidence(BaseModel):
    feature_id: int
    external_feature_id: str | None
    period: str
    source: str
    source_observed_at: datetime | None
    source_updated_at: datetime | None
    synced_at: datetime
    intersects: bool
    representative_intersection: dict | None


class PublicRouteEvidence(BaseModel):
    report_id: int
    report_code: str
    verification_status: str
    distance_to_route_meters: float
    water_level_cm: float | None
    road_status: str | None
    vehicle_status: str | None
    reported_at: datetime


class HdmsRouteEvidence(BaseModel):
    incident_id: int
    source_record_id: str
    case_id: str | None
    road_code: str | None
    section_code: str | None
    section_name: str | None
    km_start: str | None
    km_end: str | None
    province: str | None
    water_depth_cm: float | None
    road_status: str
    incident_at: datetime | None
    report_at: datetime | None
    source_updated_at: datetime | None
    survey_at: datetime | None
    geometry_available: bool


class BmaRouteEvidence(BaseModel):
    observation_id: int
    source_record_id: str
    station_id: str | None
    station_name: str | None
    road_name: str | None
    source_status: str | None
    water_level_cm: float | None
    observed_at: datetime | None
    distance_to_route_meters: float


class RouteSourceStatus(BaseModel):
    data_available: bool
    evaluated_period_or_window: str
    latest_source_at: datetime | None


class RouteFloodSourceDataStatus(BaseModel):
    complete: bool
    gistda: RouteSourceStatus
    public: RouteSourceStatus


class RouteFloodImpact(BaseModel):
    route_id: str
    origin: RouteEndpoint
    destination: RouteEndpoint
    vehicle_profile: VehicleProfile
    routing_provider: str
    distance_km: float
    duration_minutes: float
    calculated_at: datetime
    flood_situation: RouteFloodSituation
    gistda_evidence: list[GistdaRouteEvidence]
    public_report_evidence: list[PublicRouteEvidence]
    hdms_evidence: list[HdmsRouteEvidence] = Field(default_factory=list)
    bma_evidence: list[BmaRouteEvidence] = Field(default_factory=list)
    official_road_closure: bool = False
    public_route_impact_radius_meters: float
    bma_route_proximity_meters: float = 50
    source_data_status: RouteFloodSourceDataStatus
    evaluated_at: datetime
