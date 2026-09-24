from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.schemas.branch import NearbyBranchRead


def list_branches(db: Session) -> list[Branch]:
    return list(db.scalars(select(Branch).order_by(Branch.store_number)))


def get_branch_by_store_number(db: Session, store_number: str) -> Branch | None:
    return db.scalar(select(Branch).where(Branch.store_number == store_number))


def find_nearby_branches(db: Session, lat: float, lng: float, radius_km: float) -> list[NearbyBranchRead]:
    point = func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326)
    distance_m = func.ST_Distance(Branch.location, point)
    query = (
        select(Branch, distance_m.label("distance_m"))
        .where(func.ST_DWithin(Branch.location, point, radius_km * 1000))
        .order_by(distance_m)
    )
    return [
        NearbyBranchRead(
            store_number=branch.store_number, store_name=branch.store_name, city=branch.city,
            latitude=branch.latitude, longitude=branch.longitude,
            straight_distance_km=round(distance / 1000, 3),
        )
        for branch, distance in db.execute(query)
    ]
