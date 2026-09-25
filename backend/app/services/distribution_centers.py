from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.transport import DistributionCenter
from app.schemas.transport import DistributionCenterCreate


class DuplicateDistributionCenter(ValueError):
    pass


def create_distribution_center(db: Session, payload: DistributionCenterCreate) -> DistributionCenter:
    if get_distribution_center(db, payload.dc_code) is not None:
        raise DuplicateDistributionCenter(payload.dc_code)
    dc = DistributionCenter(**payload.model_dump(), location=func.ST_SetSRID(func.ST_MakePoint(payload.longitude, payload.latitude), 4326))
    db.add(dc)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateDistributionCenter(payload.dc_code) from exc
    db.refresh(dc)
    return dc


def list_distribution_centers(db: Session) -> list[DistributionCenter]:
    return list(db.scalars(select(DistributionCenter).order_by(DistributionCenter.dc_code)))


def get_distribution_center(db: Session, dc_code: str) -> DistributionCenter | None:
    return db.scalar(select(DistributionCenter).where(DistributionCenter.dc_code == dc_code))
