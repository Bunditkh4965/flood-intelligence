from unittest.mock import Mock

import httpx
import pytest

from app.core import get_settings
from app.routing.provider import (
    NoRouteFound,
    NoRoutingProvider,
    RoutingProviderConnectionError,
    RoutingProviderNotConfigured,
    RoutingProviderResponseError,
    RoutingProviderTimeout,
    get_routing_provider,
)
from app.routing.valhalla import ValhallaRoutingProvider, decode_polyline6


# Polyline6 for (lat, lon): (13.75, 100.5), (13.8, 100.6), (13.81, 100.61).
SHAPE = "_nffY_a`u~D_t`B_ibE_pR_pR"


def _response(status: int = 200, payload: object | None = None) -> httpx.Response:
    request = httpx.Request("POST", "http://valhalla/route")
    return httpx.Response(status, request=request, json=payload if payload is not None else {
        "trip": {"summary": {"length": 11.255, "time": 832.9}, "legs": [{"shape": SHAPE}]}
    })


def test_polyline6_decoding_and_geojson_coordinate_order() -> None:
    assert decode_polyline6(SHAPE) == [
        [100.5, 13.75], [100.6, 13.8], [100.61, 13.81]
    ]


def test_valhalla_request_and_successful_response() -> None:
    client = Mock()
    client.post.return_value = _response()
    provider = ValhallaRoutingProvider("http://valhalla/", 2.5, client)
    result = provider.calculate_route((100.5, 13.75), (100.61, 13.81), "6W")
    client.post.assert_called_once_with(
        "http://valhalla/route",
        json={
            "locations": [{"lat": 13.75, "lon": 100.5}, {"lat": 13.81, "lon": 100.61}],
            "costing": "auto", "units": "kilometers", "shape_format": "polyline6",
        },
        timeout=2.5,
    )
    assert result.distance_km == 11.255
    assert result.duration_minutes == pytest.approx(832.9 / 60)
    assert result.provider_name == "VALHALLA"
    assert result.route_geometry == {"type": "LineString", "coordinates": decode_polyline6(SHAPE)}


@pytest.mark.parametrize("profile", ["4W", "6W", "10W"])
def test_profiles_use_safe_common_auto_costing(profile: str) -> None:
    body = ValhallaRoutingProvider("http://valhalla")._request_body((1, 2), (3, 4), profile)
    assert body["costing"] == "auto"
    assert "costing_options" not in body


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (httpx.ReadTimeout("late"), RoutingProviderTimeout),
        (httpx.ConnectError("down"), RoutingProviderConnectionError),
    ],
)
def test_transport_errors_are_application_errors(side_effect: Exception, error: type[Exception]) -> None:
    client = Mock()
    client.post.side_effect = side_effect
    with pytest.raises(error):
        ValhallaRoutingProvider("http://valhalla", client=client).calculate_route((1, 2), (3, 4), "4W")


def test_non_2xx_response() -> None:
    client = Mock(post=Mock(return_value=_response(503, {"error": "unavailable"})))
    with pytest.raises(RoutingProviderResponseError, match="HTTP 503"):
        ValhallaRoutingProvider("http://valhalla", client=client).calculate_route((1, 2), (3, 4), "4W")


@pytest.mark.parametrize("payload", [{}, {"trip": {"summary": {}, "legs": [{}]}}])
def test_malformed_response(payload: object) -> None:
    client = Mock(post=Mock(return_value=_response(payload=payload)))
    with pytest.raises(RoutingProviderResponseError):
        ValhallaRoutingProvider("http://valhalla", client=client).calculate_route((1, 2), (3, 4), "4W")


def test_no_route_response() -> None:
    client = Mock(post=Mock(return_value=_response(payload={"error_code": 442, "error": "No path"})))
    with pytest.raises(NoRouteFound):
        ValhallaRoutingProvider("http://valhalla", client=client).calculate_route((1, 2), (3, 4), "4W")


def test_provider_selection(monkeypatch) -> None:
    monkeypatch.setenv("ROUTING_PROVIDER", "valhalla")
    monkeypatch.setenv("VALHALLA_URL", "http://shared:8002")
    get_settings.cache_clear()
    try:
        provider = get_routing_provider()
        assert isinstance(provider, ValhallaRoutingProvider)
        assert provider.base_url == "http://shared:8002"
    finally:
        get_settings.cache_clear()


def test_provider_disabled_and_incomplete(monkeypatch) -> None:
    monkeypatch.delenv("ROUTING_PROVIDER", raising=False)
    monkeypatch.delenv("VALHALLA_URL", raising=False)
    get_settings.cache_clear()
    assert isinstance(get_routing_provider(), NoRoutingProvider)
    monkeypatch.setenv("ROUTING_PROVIDER", "valhalla")
    get_settings.cache_clear()
    with pytest.raises(RoutingProviderNotConfigured):
        get_routing_provider()
    get_settings.cache_clear()
