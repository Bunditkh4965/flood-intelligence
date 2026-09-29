from collections.abc import Iterator
from typing import Any

import httpx

from app.core import Settings, get_settings


class BmaAPIError(RuntimeError):
    pass


class BmaClient:
    """Unauthenticated ArcGIS FeatureServer client with transfer-limit pagination."""

    fields = ",".join((
        "OBJECTID_1", "OBJECTID", "STATION_ID", "MASTER_STATION_ID", "DATA_DT",
        "WATER_LEVEL_CM", "ROAD_NAME", "FLOOD_MAX", "FLOOD_MAX_TIME",
        "TUNNEL_SUB_NAME", "CHK_STATUSTXT", "FLOOD_START_TH", "FLOOD_STOP_TH",
        "CREATED_AT", "UPDATED_AT", "STATION_OLDCODE", "STATION_NAME_TH",
        "AGENCY_NAME_TH", "LAT", "F_LNG", "API_SOURCE", "PROV_NAM_T",
        "AMP_NAM_T", "TAM_NAM_T",
    ))

    def __init__(self, settings: Settings | None = None,
                 transport: httpx.BaseTransport | None = None) -> None:
        settings = settings or get_settings()
        self._client = httpx.Client(base_url=settings.bma_base_url.rstrip("/") + "/",
                                    timeout=settings.bma_timeout_seconds, transport=transport)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self) -> None:
        self._client.close()

    def pages(self, page_size: int = 1000) -> Iterator[list[Any]]:
        offset = 0
        while True:
            try:
                response = self._client.get("query", params={
                    "f": "json", "where": "1=1", "outFields": self.fields,
                    "returnGeometry": "true", "outSR": "4326",
                    "resultOffset": str(offset), "resultRecordCount": str(page_size),
                    "orderByFields": "OBJECTID ASC",
                })
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise BmaAPIError(f"BMA request failed: {type(exc).__name__}") from None
            if not isinstance(payload, dict) or payload.get("error"):
                raise BmaAPIError("BMA ArcGIS response reported an error")
            features = payload.get("features")
            if not isinstance(features, list):
                raise BmaAPIError("BMA ArcGIS response has no feature array")
            yield features
            if not payload.get("exceededTransferLimit"):
                break
            if not features:
                raise BmaAPIError("BMA pagination made no progress")
            offset += len(features)
