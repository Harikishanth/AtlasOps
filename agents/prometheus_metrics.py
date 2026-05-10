"""Shared Prometheus dashboard metrics JSON for FastAPI handlers.

Used by the root Space app (`GET /metrics`) and the coordinator sub-app mounted
at `/api` (`GET /api/metrics` → coordinator route `/metrics`).
"""

from __future__ import annotations

import os
from typing import Any


async def build_dashboard_metrics_payload() -> dict[str, Any]:
    import httpx as _httpx

    prom = (os.getenv("PROMETHEUS_URL") or "").strip()
    alert_url = (os.getenv("ALERTMANAGER_URL") or "").strip()
    results: dict[str, Any] = {"error_rate": None, "cpu": None, "rps": None, "alerts": None}
    if not prom:
        return results
    queries = {
        "error_rate": 'sum(rate(apiserver_request_total{code=~"5.."}[2m])) or vector(0)',
        "cpu": 'sum(rate(container_cpu_usage_seconds_total{namespace="default"}[2m])) or vector(0)',
        "rps": "sum(rate(apiserver_request_total[2m])) or vector(0)",
    }
    try:
        async with _httpx.AsyncClient(timeout=10) as client:
            for key, query in queries.items():
                try:
                    r = await client.get(f"{prom}/api/v1/query", params={"query": query})
                    if r.status_code == 200:
                        data = r.json().get("data", {}).get("result", [])
                        total = sum(float(x["value"][1]) for x in data if x.get("value"))
                        results[key] = round(total, 4)
                except Exception:
                    continue
            if alert_url:
                try:
                    ar = await client.get(f"{alert_url}/api/v2/alerts?active=true")
                    if ar.status_code == 200:
                        results["alerts"] = len(ar.json())
                except Exception:
                    pass
    except Exception:
        pass
    return results
