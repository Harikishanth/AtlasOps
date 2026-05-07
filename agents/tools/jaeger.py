"""Jaeger tool wrappers — HTTP query API to Jaeger."""

import os
import time
from typing import Any

import requests

JAEGER_URL = os.getenv(
    "JAEGER_URL",
    "http://jaeger-query.tracing.svc.cluster.local:16686",
)


def jaeger_search(service: str, lookback: str = "15m", limit: int = 20,
                  min_duration: str = "", tag_filters: dict | None = None) -> dict[str, Any]:
    """Search for traces by service. min_duration example: '1s', '500ms'."""
    end_us = int(time.time() * 1_000_000)
    lookback_us = _parse_lookback_to_us(lookback)
    start_us = end_us - lookback_us
    params: dict[str, Any] = {
        "service": service,
        "start": str(start_us),
        "end": str(end_us),
        "limit": str(limit),
    }
    if min_duration:
        params["minDuration"] = min_duration
    if tag_filters:
        tag_str = " ".join(f'{k}="{v}"' for k, v in tag_filters.items())
        params["tags"] = tag_str
    try:
        r = requests.get(f"{JAEGER_URL}/api/traces", params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        traces = [
            {
                "traceID": t.get("traceID"),
                "spans": len(t.get("spans", [])),
                "duration_us": max((s.get("duration", 0) for s in t.get("spans", [])), default=0),
                "operation": t.get("spans", [{}])[0].get("operationName") if t.get("spans") else None,
            }
            for t in data.get("data", [])
        ]
        return {"success": True, "count": len(traces), "traces": traces}
    except requests.RequestException as e:
        return {"success": False, "error": str(e)}


def jaeger_get_trace(trace_id: str) -> dict[str, Any]:
    """Fetch a single trace by ID."""
    try:
        r = requests.get(f"{JAEGER_URL}/api/traces/{trace_id}", timeout=10)
        r.raise_for_status()
        return {"success": True, "data": r.json()}
    except requests.RequestException as e:
        return {"success": False, "error": str(e)}


def _parse_lookback_to_us(lookback: str) -> int:
    """Convert '15m', '1h', '30s' to microseconds."""
    unit = lookback[-1]
    value = int(lookback[:-1])
    multipliers = {"s": 1_000_000, "m": 60_000_000, "h": 3_600_000_000}
    return value * multipliers.get(unit, 60_000_000)
