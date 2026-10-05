from datetime import datetime
from enum import StrEnum

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class DcStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class DistributionCenterCreate(BaseModel):
    dc_code: str = Field(min_length=1, max_length=64)
    dc_name: str = Field(min_length=1, max_length=255)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    status: DcStatus = DcStatus.ACTIVE

    @field_validator("dc_code", "dc_name")
    @classmethod
    def strip_nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class DistributionCenterRead(DistributionCenterCreate):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime
    updated_at: datetime


class LocationType(StrEnum):
    DC = "DC"
    BRANCH = "BRANCH"
    CURRENT_LOCATION = "CURRENT_LOCATION"


class VehicleProfile(StrEnum):
    FOUR_WHEEL = "4W"
    SIX_WHEEL = "6W"
    TEN_WHEEL = "10W"


class RouteEndpoint(BaseModel):
    type: LocationType
    code: str = Field(min_length=1, max_length=64, validation_alias=AliasChoices("code", "id"))


class RouteCalculateRequest(BaseModel):
    origin: RouteEndpoint
    destination: RouteEndpoint
    vehicle_profile: VehicleProfile


class SafeRouteCalculateRequest(BaseModel):
    origin: RouteEndpoint
    destination: RouteEndpoint
    vehicle_profile: VehicleProfile
    origin_coordinates: list[float] | None = Field(default=None, min_length=2, max_length=2)

    @field_validator("origin_coordinates")
    @classmethod
    def valid_coordinates(cls, value: list[float] | None) -> list[float] | None:
        if value is not None and (not all(map(lambda x: isinstance(x, (int, float)), value))
                                  or not -180 <= value[0] <= 180 or not -90 <= value[1] <= 90):
            raise ValueError("origin_coordinates must be [longitude, latitude]")
        return value


class RouteSafetyState(StrEnum):
    SAFE = "SAFE"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"
    UNVERIFIED = "UNVERIFIED"


class SafeRouteRead(BaseModel):
    route_id: str | None = None
    origin_type: LocationType
    origin_code: str
    destination_type: LocationType
    destination_code: str
    vehicle_profile: VehicleProfile
    distance_km: float
    duration_minutes: float
    route_geometry: dict
    routing_provider: str
    calculated_at: datetime
    safety_state: RouteSafetyState
    avoidance_attempted: bool
    blocking_hazards: list[dict]
    warning_hazards: list[dict]
    evidence: dict
    navigation_waypoints: list[list[float]]


class RouteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    route_id: str
    origin_type: LocationType
    origin_code: str
    destination_type: LocationType
    destination_code: str
    vehicle_profile: VehicleProfile
    distance_km: float
    duration_minutes: float
    route_geometry: dict
    routing_provider: str
    provider_route_id: str | None = None
    calculated_at: datetime
