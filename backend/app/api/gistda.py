from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.gistda import GeoJSONFeature, GeoJSONFeatureCollection, GistdaFeatureProperties, GistdaStatus
from app.services.gistda import list_features, status_rows

router = APIRouter(prefix="/api/v1/gistda", tags=["gistda"])
DbSession = Annotated[Session, Depends(get_db)]
Period = Literal["1day", "3days", "7days", "30days"]


@router.get("/flood", response_model=GeoJSONFeatureCollection)
def get_gistda_flood(db: DbSession, period: Period | None = None, active: bool | None = Query(True)) -> GeoJSONFeatureCollection:
    features = []
    for row, geometry in list_features(db, period, active):
        properties = GistdaFeatureProperties(
            id=row.id, external_feature_id=row.external_feature_id, period=row.period, source=row.source,
            source_observed_at=row.source_observed_at, source_updated_at=row.source_updated_at,
            synced_at=row.synced_at, source_properties=row.source_properties,
            source_hash=row.source_hash, is_active=row.is_active,
        )
        features.append(GeoJSONFeature(geometry=geometry, properties=properties))
    return GeoJSONFeatureCollection(features=features)


@router.get("/status", response_model=list[GistdaStatus])
def get_gistda_status(db: DbSession) -> list[GistdaStatus]:
    return [GistdaStatus(**row) for row in status_rows(db)]
