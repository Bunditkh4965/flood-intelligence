from pydantic import BaseModel, ConfigDict, Field


class Coordinates(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class BranchRead(Coordinates):
    model_config = ConfigDict(from_attributes=True)

    store_number: str
    store_name: str
    format: str | None = None
    city: str
    business_hours: str | None = None
    vehicle_type: str | None = None
    status: str


class NearbyBranchRead(BaseModel):
    store_number: str
    store_name: str
    city: str
    latitude: float
    longitude: float
    straight_distance_km: float
