from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit

import httpx

from app.core import Settings, get_settings

logger = logging.getLogger(__name__)
ENDPOINTS = {"1DAY": "1day", "3DAYS": "3days", "7DAYS": "7days", "30DAYS": "30days"}
MAX_GEOJSON_PAGES = 20_000
MAX_COLLECTION_PAGES = 2_000
COLLECTION_PAGE_SIZE = 1_000


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
        expected = relation.casefold()

        def has_relation(link: dict[str, Any]) -> bool:
            value = link.get("rel")
            values = value if isinstance(value, list) else [value]
            return any(
                isinstance(item, str)
                and item.strip().casefold().rstrip("/").rsplit("/", 1)[-1] == expected
                for item in values
            )

        matches = [link for link in links if isinstance(link, dict) and has_relation(link)]
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
            logger.info(
                "Discovered GISTDA Features asset type=%s roles=%s",
                preferred.get("type", "unknown"), preferred.get("roles", []),
            )
            return preferred["href"]
        matches = [asset["href"] for asset in assets.values() if valid(asset)]
        if len(matches) != 1:
            raise GistdaAPIError("GISTDA STAC item must contain one GeoJSON Features asset")
        selected = next(asset for asset in assets.values() if valid(asset))
        logger.info(
            "Discovered GISTDA Features asset type=%s roles=%s",
            selected.get("type", "unknown"), selected.get("roles", []),
        )
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

    @staticmethod
    def _collection_identity(collection: Any) -> str | None:
        if isinstance(collection, str) and collection.strip():
            return collection.strip()
        if not isinstance(collection, dict):
            return None
        for key in ("id", "collection", "name"):
            value = collection.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        links = collection.get("links", [])
        if isinstance(links, list):
            for link in links:
                if not isinstance(link, dict) or link.get("rel") != "self":
                    continue
                href = link.get("href")
                if isinstance(href, str) and "/collections/" in href:
                    return href.rstrip("/").rsplit("/", 1)[-1]
        return None

    @staticmethod
    def _matches_period(value: str, period: str) -> bool:
        days = ENDPOINTS[period].removesuffix("days").removesuffix("day")
        normalized = re.sub(r"[^a-z0-9]", "", value.casefold())
        return re.search(rf"flood0*{re.escape(days)}days?", normalized) is not None

    @classmethod
    def _select_collection(cls, collections: list[Any], period: str) -> tuple[str, dict[str, Any]]:
        identity_matches: list[tuple[str, dict[str, Any]]] = []
        metadata_matches: list[tuple[str, dict[str, Any]]] = []
        seen_identities: set[str] = set()
        for raw in collections:
            identity = cls._collection_identity(raw)
            if identity is None:
                continue
            canonical_identity = identity.casefold()
            if canonical_identity in seen_identities:
                continue
            seen_identities.add(canonical_identity)
            collection = raw if isinstance(raw, dict) else {"id": identity}
            if cls._matches_period(identity, period):
                identity_matches.append((identity, collection))
                continue
            metadata = " ".join(
                str(collection.get(key, "")) for key in ("title", "description", "keywords")
            )
            if cls._matches_period(metadata, period):
                metadata_matches.append((identity, collection))
        candidates = identity_matches or metadata_matches
        if not candidates:
            raise GistdaAPIError(f"GISTDA STAC discovery found 0 collections for {period}")
        if len(candidates) == 1:
            return candidates[0]

        # Multiple revisions of the same period are resolved to the greatest
        # explicit revision. Without an unambiguous revision, fail closed.
        versioned: list[tuple[int, str, dict[str, Any]]] = []
        for identity, collection in candidates:
            match = re.search(r"(?:^|[_-])(?:r|v|version)[_-]?(\d+)$", identity.casefold())
            if match:
                versioned.append((int(match.group(1)), identity, collection))
        if versioned:
            highest = max(item[0] for item in versioned)
            newest = [item for item in versioned if item[0] == highest]
            if len(newest) == 1:
                _, identity, collection = newest[0]
                return identity, collection
        raise GistdaAPIError(
            f"GISTDA STAC discovery found {len(candidates)} ambiguous collections for {period}"
        )

    @staticmethod
    def _normalize_collection_next(href: str) -> str:
        """Repair GISTDA's verified `/collections&limit=...` link defect only."""
        parts = urlsplit(href)
        if parts.query or parts.fragment:
            return href
        match = re.fullmatch(r"(?P<path>.*(?:^|/)collections)&(?P<query>[^?#]+)", parts.path)
        if match is None:
            return href
        parameters = parse_qsl(match.group("query"), keep_blank_values=True)
        keys = {key for key, _ in parameters}
        if not parameters or not {"limit", "offset"}.issubset(keys) or not keys <= {"limit", "offset"}:
            return href
        return urlunsplit((parts.scheme, parts.netloc, match.group("path"), match.group("query"), ""))

    def _stac_collection(self, period: str) -> tuple[dict[str, Any], httpx.URL]:
        listing, listing_url = self._get_json(
            f"collections?limit={COLLECTION_PAGE_SIZE}&offset=0", period,
        )
        all_collections: list[Any] = []
        visited: set[str] = set()
        for page_number in range(1, MAX_COLLECTION_PAGES + 1):
            canonical_url = str(listing_url)
            if canonical_url in visited:
                raise GistdaAPIError("GISTDA STAC collection pagination cycle detected")
            visited.add(canonical_url)
            collections = listing.get("collections")
            if not isinstance(collections, list):
                raise GistdaAPIError("GISTDA STAC collections response is malformed")
            all_collections.extend(collections)
            next_href = self._link(listing, "next")
            logger.info(
                "GISTDA STAC collection page=%d returned=%d next=%s",
                page_number, len(collections), next_href is not None,
            )
            if next_href is None:
                break
            normalized_next = self._normalize_collection_next(next_href)
            if normalized_next != next_href:
                logger.warning("Repaired malformed GISTDA STAC collection next link")
            listing, listing_url = self._get_json(listing_url.join(normalized_next), period)
        else:
            raise GistdaAPIError(
                f"GISTDA STAC collection pagination exceeded {MAX_COLLECTION_PAGES} pages"
            )

        collection_id, collection = self._select_collection(all_collections, period)
        logger.info("Discovered GISTDA STAC collection id=%s for %s", collection_id, period)
        self_href = self._link(collection, "self")
        collection_url = (
            listing_url.join(self_href) if self_href
            else listing_url.join(f"collections/{quote(collection_id, safe='')}")
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
        total_returned = 0
        for page_number in range(1, MAX_GEOJSON_PAGES + 1):
            canonical_url = str(url)
            if canonical_url in visited:
                raise GistdaAPIError("GISTDA pagination cycle detected")
            visited.add(canonical_url)
            if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
                raise GistdaAPIError("GISTDA page is not a GeoJSON FeatureCollection")
            next_href = self._link(payload, "next")
            returned = payload.get("numberReturned")
            returned_count = returned if isinstance(returned, int) and not isinstance(returned, bool) else len(payload["features"])
            total_returned += len(payload["features"])
            logger.info(
                "GISTDA GeoJSON page=%d numberReturned=%d next=%s",
                page_number, returned_count, next_href is not None,
            )
            yield payload
            if next_href is None:
                matched = payload.get("numberMatched")
                if isinstance(matched, int) and not isinstance(matched, bool) and matched > total_returned:
                    raise GistdaAPIError(
                        "GISTDA pagination ended before numberMatched was reached "
                        f"({total_returned} of {matched})"
                    )
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
