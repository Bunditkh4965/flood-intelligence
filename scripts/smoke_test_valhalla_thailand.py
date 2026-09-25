#!/usr/bin/env python3
"""Exercise a real Thailand road route; uses no Flood Intelligence master data."""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# Test-only coordinates: Bangkok Victory Monument -> Wat Arun.
TEST_ORIGIN = {"lat": 13.7649, "lon": 100.5383}
TEST_DESTINATION = {"lat": 13.7437, "lon": 100.4889}


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test local Thailand Valhalla tiles")
    parser.add_argument("--url", default="http://localhost:8002")
    args = parser.parse_args()
    payload = json.dumps(
        {
            "locations": [TEST_ORIGIN, TEST_DESTINATION],
            "costing": "auto",
            "units": "kilometers",
            "directions_options": {"units": "kilometers"},
        }
    ).encode()
    request = Request(
        f"{args.url.rstrip('/')}/route",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:  # noqa: S310 - caller selects local URL
            result = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"FAIL: route request did not return valid JSON: {exc}", file=sys.stderr)
        return 1

    trip = result.get("trip") or {}
    summary = trip.get("summary") or {}
    legs = trip.get("legs") or []
    distance = summary.get("length")
    duration = summary.get("time")
    shapes = [leg.get("shape") for leg in legs if isinstance(leg, dict)]
    errors = []
    if trip.get("status") not in (0, None) or not legs:
        errors.append("response does not contain a successful trip with legs")
    if not isinstance(distance, (int, float)) or distance <= 0:
        errors.append("trip.summary.length is not greater than zero")
    if not isinstance(duration, (int, float)) or duration <= 0:
        errors.append("trip.summary.time is not greater than zero")
    if not any(isinstance(shape, str) and len(shape) > 1 for shape in shapes):
        errors.append("no encoded road shape was returned in trip.legs[].shape")
    if errors:
        print("FAIL: " + "; ".join(errors), file=sys.stderr)
        return 1

    print(f"PASS: Thailand road route: {distance:.3f} km, {duration:.1f} seconds, {len(legs)} leg(s)")
    print("PASS: response includes an encoded polyline6 route shape")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
