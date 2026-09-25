#!/usr/bin/env python3
"""Test the shared Thailand routing HTTP API without application dependencies."""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TEST_ORIGIN = {"lat": 13.7649, "lon": 100.5383}  # Bangkok Victory Monument
TEST_DESTINATION = {"lat": 13.7437, "lon": 100.4889}  # Bangkok Wat Arun


def get_json(url: str) -> dict:
    with urlopen(url, timeout=30) as response:  # noqa: S310 - local URL by default
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test shared Thailand Valhalla")
    parser.add_argument("--url", default="http://localhost:8002")
    args = parser.parse_args()
    base_url = args.url.rstrip("/")
    try:
        status = get_json(f"{base_url}/status")
        if not isinstance(status, dict):
            raise ValueError("/status did not return a JSON object")
        payload = json.dumps({
            "locations": [TEST_ORIGIN, TEST_DESTINATION],
            "costing": "auto",
            "units": "kilometers",
            "directions_options": {"units": "kilometers"},
        }).encode()
        request = Request(f"{base_url}/route", data=payload,
                          headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=60) as response:  # noqa: S310
            result = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL: Valhalla HTTP validation failed: {exc}", file=sys.stderr)
        return 1

    trip = result.get("trip") or {}
    summary = trip.get("summary") or {}
    legs = trip.get("legs") or []
    shapes = [leg.get("shape") for leg in legs if isinstance(leg, dict)]
    errors = []
    if trip.get("status") not in (0, None) or not legs:
        errors.append("response does not contain a successful trip with legs")
    if not isinstance(summary.get("length"), (int, float)) or summary["length"] <= 0:
        errors.append("trip.summary.length is not greater than zero")
    if not isinstance(summary.get("time"), (int, float)) or summary["time"] <= 0:
        errors.append("trip.summary.time is not greater than zero")
    if not any(isinstance(shape, str) and len(shape) > 1 for shape in shapes):
        errors.append("no encoded road-network shape exists in trip.legs[].shape")
    if errors:
        print("FAIL: " + "; ".join(errors), file=sys.stderr)
        return 1

    print("PASS: /status returned JSON")
    print(f"PASS: route is {summary['length']:.3f} km and {summary['time']:.1f} seconds")
    print("PASS: response contains an encoded polyline6 road-network shape")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
