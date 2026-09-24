from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core import Settings, get_settings

logger = logging.getLogger(__name__)
ENDPOINTS = {"1DAY": "1day", "3DAYS": "3days", "7DAYS": "7days", "30DAYS": "30days"}


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
        if not self.settings.gistda_api_key.strip():
            raise GistdaConfigurationError("GISTDA_API_KEY is required")
        if not self.settings.gistda_api_base_url.strip():
            raise GistdaConfigurationError("GISTDA_API_BASE_URL is required")
        self._client = httpx.Client(
            base_url=self.settings.gistda_api_base_url.rstrip("/") + "/",
            headers={"API-Key": self.settings.gistda_api_key},
            timeout=httpx.Timeout(self.settings.gistda_read_timeout_seconds, connect=self.settings.gistda_connect_timeout_seconds),
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def fetch_flood_features(self, period: str) -> dict[str, Any]:
        normalized = period.upper()
        if normalized not in ENDPOINTS:
            raise ValueError(f"Unsupported GISTDA period: {period}")
        path = f"features/flood/{ENDPOINTS[normalized]}"
        logger.info("Fetching GISTDA flood features for %s", normalized)
        try:
            response = self._client.get(path)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Never interpolate the request, headers, body, or upstream text.
            raise GistdaAPIError(f"GISTDA request failed for {normalized}: {type(exc).__name__}") from None
        if not isinstance(payload, dict):
            raise GistdaAPIError("GISTDA response must be a JSON object")
        return payload

    def __enter__(self) -> "GistdaClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
