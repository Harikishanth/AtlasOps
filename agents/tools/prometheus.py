"""Prometheus tool wrappers — HTTP API queries to Prometheus."""

import os
import time
from typing import Any

import requests

PROMETHEUS_URL = os.getenv(
    "PROMETHEUS_URL",
    "http://prometheus-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090",
)


def promql_query(query: str, time_unix: float | None = None) -> dict[str, Any]:
    """Execute an instant PromQL query."""
    params = {"query": query}
    if time_unix is not None:
        params["time"] = str(time_unix)
    try:
        r = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "success":
            return {"success": False, "error": data.get("error", "unknown"), "raw": data}
        return {"success": True, "result": data["data"]["result"], "resultType": data["data"]["resultType"]}
    except requests.RequestException as e:
        return {"success": False, "error": str(e)}


def promql_query_range(query: str, start: float | None = None, end: float | None = None,
                        step: str = "30s") -> dict[str, Any]:
    """Execute a PromQL range query (last 15 min by default)."""
    end = end or time.time()
    start = start or (end - 900)
    params = {"query": query, "start": str(start), "end": str(end), "step": step}
    try:
        r = requests.get(f"{PROMETHEUS_URL}/api/v1/query_range", params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "success":
            return {"success": False, "error": data.get("error", "unknown")}
        return {"success": True, "result": data["data"]["result"]}
    except requests.RequestException as e:
        return {"success": False, "error": str(e)}
