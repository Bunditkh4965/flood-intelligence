from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded exclusively from environment variables."""

    database_url: str = "postgresql+psycopg://flood:flood@localhost:5432/flood_intelligence"
    reporter_gps_verify_radius_m: float = 300.0
    gistda_api_key: str = ""
    gistda_api_base_url: str = "https://api-gateway.gistda.or.th/api/2.0/resources"
    gistda_stac_base_url: str = "https://disaster.gistda.or.th/app-api/services/stac/flood/"
    gistda_connect_timeout_seconds: float = 30.0
    gistda_read_timeout_seconds: float = 30.0
    photo_storage_directory: str = "./var/flood-report-photos"
    photo_max_bytes: int = 8 * 1024 * 1024
    cors_allowed_origins: str = "http://localhost:3000"
    routing_provider: str = ""
    valhalla_url: str = ""
    valhalla_timeout_seconds: float = 10.0
    public_route_impact_radius_meters: float = Field(default=300.0, gt=0)
    route_impact_public_lookback_hours: int = Field(default=24, gt=0)
    route_impact_gistda_period: str = Field(default="3DAYS", pattern="^(1DAY|3DAYS|7DAYS|30DAYS)$")
    hdms_enabled: bool = False
    hdms_base_url: str = "https://hdms.doh.go.th/internal-api"
    hdms_timeout_seconds: float = Field(default=15.0, gt=0)
    bma_enabled: bool = False
    bma_base_url: str = "https://gis-portal.disaster.go.th/arcgis/rest/services/Map116/DPM_RUNOFF_STATION_DDS_DSS/FeatureServer/1"
    bma_timeout_seconds: float = Field(default=15.0, gt=0)
    # A small road-association radius limits false matches on Bangkok's dense network.
    bma_route_proximity_meters: float = Field(default=50.0, gt=0)
    # Reserved for evidence-policy configuration in the next stage. An empty
    # mapping means no water-depth-based vehicle passability is inferred.
    vehicle_water_depth_thresholds_cm: dict[str, float] = Field(default_factory=dict)
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
