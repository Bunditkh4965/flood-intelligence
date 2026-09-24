from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RoadStatus = Literal["PASSABLE", "PARTIAL", "BLOCKED", "UNKNOWN"]
VehicleStatus = Literal["PASSABLE", "BLOCKED", "UNKNOWN"]
VerificationStatus = Literal["VERIFIED", "PENDING_REVIEW", "UNVERIFIED"]
ReportStatus = Literal["ACTIVE", "REVIEWED", "REJECTED", "CLOSED"]


class FloodReportCreate(BaseModel):
    """Coordinates originate from map selection and device GPS, never text fields."""

    model_config = ConfigDict(extra="forbid")
    flood_latitude: float = Field(ge=-90, le=90)
    flood_longitude: float = Field(ge=-180, le=180)
    reporter_latitude: float | None = Field(default=None, ge=-90, le=90)
    reporter_longitude: float | None = Field(default=None, ge=-180, le=180)
    reporter_gps_accuracy_m: float | None = Field(default=None, ge=0)
    water_level_cm: float = Field(ge=0)
    road_status: RoadStatus = "UNKNOWN"
    vehicle_4w_status: VehicleStatus = "UNKNOWN"
    vehicle_6w_status: VehicleStatus = "UNKNOWN"
    vehicle_10w_status: VehicleStatus = "UNKNOWN"
    description: str | None = Field(default=None, max_length=2000)
    has_photo: bool = False
    reported_at: datetime | None = None

    @model_validator(mode="after")
    def reporter_coordinates_are_a_pair(self) -> "FloodReportCreate":
        if (self.reporter_latitude is None) != (self.reporter_longitude is None):
            raise ValueError("reporter_latitude and reporter_longitude must be supplied together")
        return self


class LocationRead(BaseModel):
    latitude: float
    longitude: float


class FloodReportRead(BaseModel):
    report_code: str
    flood_location: LocationRead
    water_level_cm: float
    road_status: RoadStatus
    vehicle_4w_status: VehicleStatus
    vehicle_6w_status: VehicleStatus
    vehicle_10w_status: VehicleStatus
    description: str | None
    has_photo: bool
    verification_status: VerificationStatus
    verification_reason: str
    source: Literal["PUBLIC", "COMPANY", "GISTDA", "SYSTEM"]
    status: ReportStatus
    reported_at: datetime


class FloodReportPhotoRead(BaseModel):
    report_code: str
    has_photo: bool
    verification_status: VerificationStatus
    verification_reason: str
