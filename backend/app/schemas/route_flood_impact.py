"""Provider-neutral factual evidence detected against a persisted road route."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

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
    public_route_impact_radius_meters: float
    source_data_status: RouteFloodSourceDataStatus
    evaluated_at: datetime
