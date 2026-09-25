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
