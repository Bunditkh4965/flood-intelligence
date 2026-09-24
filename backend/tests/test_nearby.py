from app.models.branch import Branch
from app.services.branches import find_nearby_branches


class Result:
    def __iter__(self):
        branch = Branch(store_number="1001", store_name="Central", city="Austin", latitude=30.2672, longitude=-97.7431, location="SRID=4326;POINT(-97.7431 30.2672)")
        return iter([(branch, 1234.56)])


class Session:
    def execute(self, query):  # type: ignore[no-untyped-def]
        self.query = query
        return Result()


def test_nearby_branch_search_maps_spatial_query_result() -> None:
    results = find_nearby_branches(Session(), 30.25, -97.75, 5)
    assert results[0].store_number == "1001"
    assert results[0].straight_distance_km == 1.235
