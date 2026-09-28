from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

import httpx

from app.core import Settings, get_settings

logger = logging.getLogger(__name__)
ENDPOINTS = {"1DAY": "1day", "3DAYS": "3days", "7DAYS": "7days", "30DAYS": "30days"}
MAX_GEOJSON_PAGES = 20_000


class GistdaConfigurationError(RuntimeError):
    pass


class GistdaAPIError(RuntimeError):
    pass


class GistdaClient:
    """Small client for GISTDA's GeoJSON feature API.

    The official OAS declares an ``API-Key`` header security scheme. Header
    values are deliberately never included in log or exception messages.
    """

    def __init__(self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings or get_settings()
        stac_url = self.settings.gistda_stac_base_url.strip()
        if not stac_url and not self.settings.gistda_api_key.strip():
            raise GistdaConfigurationError("GISTDA_API_KEY is required when STAC is not configured")
        if not stac_url and not self.settings.gistda_api_base_url.strip():
            raise GistdaConfigurationError("GISTDA_API_BASE_URL is required when STAC is not configured")
        self._uses_stac = bool(stac_url)
        self._client = httpx.Client(
            base_url=(stac_url or self.settings.gistda_api_base_url).rstrip("/") + "/",
            # The Disaster Platform STAC API is public. Never send the API
            # gateway credential to a different host.
            headers={} if stac_url else {"API-Key": self.settings.gistda_api_key},
            timeout=httpx.Timeout(self.settings.gistda_read_timeout_seconds, connect=self.settings.gistda_connect_timeout_seconds),
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def _get_json(self, url: str | httpx.URL, period: str) -> tuple[dict[str, Any], httpx.URL]:
        try:
            response = self._client.get(url)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Never interpolate the request, headers, body, or upstream text.
            raise GistdaAPIError(f"GISTDA request failed for {period}: {type(exc).__name__}") from None
        if not isinstance(payload, dict):
            raise GistdaAPIError("GISTDA response must be a JSON object")
        return payload, response.url

    @staticmethod
    def _link(payload: dict[str, Any], relation: str) -> str | None:
        links = payload.get("links", [])
        if not isinstance(links, list):
            raise GistdaAPIError("GISTDA links must be an array")
        matches = [link for link in links if isinstance(link, dict) and link.get("rel") == relation]
        if not matches:
            return None
        href = matches[0].get("href")
        if not isinstance(href, str) or not href.strip():
            raise GistdaAPIError(f"GISTDA {relation} link is missing href")
        return href

    @staticmethod
    def _feature_asset(item: dict[str, Any]) -> str:
        assets = item.get("assets")
        if not isinstance(assets, dict):
            raise GistdaAPIError("GISTDA STAC item has no assets")

        def valid(asset: Any) -> bool:
            if not isinstance(asset, dict) or not isinstance(asset.get("href"), str):
                return False
            media_type = str(asset.get("type", "")).lower().split(";", 1)[0].strip()
            roles = asset.get("roles", [])
            semantic_role = isinstance(roles, list) and any(str(role).lower() == "features" for role in roles)
            return media_type in {"application/geo+json", "application/vnd.geo+json"} or semantic_role

        preferred = assets.get("data")
        if valid(preferred):
            return preferred["href"]
        matches = [asset["href"] for asset in assets.values() if valid(asset)]
        if len(matches) != 1:
            raise GistdaAPIError("GISTDA STAC item must contain one GeoJSON Features asset")
        return matches[0]

    def _discover_geojson(self, payload: dict[str, Any], url: httpx.URL,
                          period: str) -> tuple[dict[str, Any], httpx.URL]:
        # The compatibility endpoint may already resolve to the GeoJSON asset.
        features = payload.get("features")
        if payload.get("type") == "FeatureCollection" and isinstance(features, list):
            stac_items = [item for item in features if isinstance(item, dict) and "assets" in item]
            if not stac_items:
                return payload, url
            asset_url = url.join(self._feature_asset(stac_items[0]))
            return self._get_json(asset_url, period)
        if payload.get("type") == "Feature" and "assets" in payload:
            return self._get_json(url.join(self._feature_asset(payload)), period)

        items_href = self._link(payload, "items")
        if items_href is None:
            raise GistdaAPIError("GISTDA response is neither GeoJSON nor a STAC collection")
        items, items_url = self._get_json(url.join(items_href), period)
        return self._discover_geojson(items, items_url, period)

    def _stac_collection(self, period: str) -> tuple[dict[str, Any], httpx.URL]:
        listing, listing_url = self._get_json("collections", period)
        collections = listing.get("collections")
        if not isinstance(collections, list):
            raise GistdaAPIError("GISTDA STAC collections response is malformed")
        token = ENDPOINTS[period]
        expected_prefix = f"flood{token}"
        candidates = []
        for collection in collections:
            if not isinstance(collection, dict) or not isinstance(collection.get("id"), str):
                continue
            normalized_id = re.sub(r"[^a-z0-9]", "", collection["id"].lower())
            if normalized_id.startswith(expected_prefix):
                candidates.append(collection)
        if len(candidates) != 1:
            raise GistdaAPIError(
                f"GISTDA STAC discovery found {len(candidates)} collections for {period}"
            )
        collection = candidates[0]
        self_href = self._link(collection, "self")
        collection_url = (
            listing_url.join(self_href) if self_href
            else listing_url.join(f"collections/{quote(collection['id'], safe='')}")
        )
        return self._get_json(collection_url, period)

    def iter_flood_feature_pages(self, period: str) -> Iterator[dict[str, Any]]:
        normalized = period.upper()
        if normalized not in ENDPOINTS:
            raise ValueError(f"Unsupported GISTDA period: {period}")
        logger.info("Fetching GISTDA flood features for %s", normalized)
        if self._uses_stac:
            payload, url = self._stac_collection(normalized)
        else:
            payload, url = self._get_json(f"features/flood/{ENDPOINTS[normalized]}", normalized)
        payload, url = self._discover_geojson(payload, url, normalized)
        visited: set[str] = set()
        for _ in range(MAX_GEOJSON_PAGES):
            canonical_url = str(url)
            if canonical_url in visited:
                raise GistdaAPIError("GISTDA pagination cycle detected")
            visited.add(canonical_url)
            if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
                raise GistdaAPIError("GISTDA page is not a GeoJSON FeatureCollection")
            yield payload
            next_href = self._link(payload, "next")
            if next_href is None:
                return
            payload, url = self._get_json(url.join(next_href), normalized)
        raise GistdaAPIError(f"GISTDA pagination exceeded {MAX_GEOJSON_PAGES} pages")

    def fetch_flood_features(self, period: str) -> dict[str, Any]:
        """Return a combined collection for callers using the original client contract."""
        features: list[Any] = []
        for page in self.iter_flood_feature_pages(period):
            features.extend(page["features"])
        return {"type": "FeatureCollection", "features": features}

    def __enter__(self) -> "GistdaClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
