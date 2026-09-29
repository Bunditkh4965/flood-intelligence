from datetime import date
from typing import Any

import httpx

from app.core import Settings, get_settings


class HdmsAPIError(RuntimeError):
    pass


class HdmsClient:
    """Sequential, unauthenticated client for HDMS public endpoints."""

    def __init__(self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.Client(
            base_url=self.settings.hdms_base_url.rstrip("/") + "/",
            timeout=self.settings.hdms_timeout_seconds,
            transport=transport,
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str, params: dict[str, str]) -> Any:
        try:
            response = self._client.get(path, params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HdmsAPIError(f"HDMS request failed: {type(exc).__name__}") from None

    def fetch_dashboard(self, start: date, end: date, status: str = "open", passage: str = "all") -> Any:
        return self._get("public/dashboard", {
            "start": start.isoformat(), "end": end.isoformat(), "status": status, "passage": passage,
        })

    def fetch_section_geometry(self, road_code: str, section_code: str,
                               km_start: str, km_end: str) -> Any:
        return self._get("section_part/section-km", {
            "road_code": road_code, "section_code": section_code,
            "km_start": km_start, "km_end": km_end,
        })
