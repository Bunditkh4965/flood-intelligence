from unittest.mock import Mock

from app.models.branch import Branch
from app.services.branches import get_branch_by_store_number, list_branches


def test_branch_creation_and_listing_query() -> None:
    branch = Branch(store_number="1001", store_name="Central", city="Austin", latitude=30.2672, longitude=-97.7431, location="SRID=4326;POINT(-97.7431 30.2672)")
    session = Mock()
    session.scalars.return_value = [branch]

    assert list_branches(session) == [branch]


def test_branch_query_by_store_number() -> None:
    branch = Branch(store_number="1001", store_name="Central", city="Austin", latitude=30.2672, longitude=-97.7431, location="SRID=4326;POINT(-97.7431 30.2672)")
    session = Mock()
    session.scalar.return_value = branch

    assert get_branch_by_store_number(session, "1001") is branch
