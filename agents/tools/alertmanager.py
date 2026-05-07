"""Alertmanager tool wrappers — silence flapping alerts via HTTP API."""

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests


ALERTMANAGER_URL = os.getenv(
    "ALERTMANAGER_URL",
    "http://prometheus-kube-prometheus-alertmanager.monitoring.svc.cluster.local:9093",
)


def alertmanager_silence(matchers: list[dict[str, str]], duration_minutes: int = 30,
                         comment: str = "Silenced by CloudSRE agent",
                         created_by: str = "cloudsre-coordinator") -> dict[str, Any]:
    """Create a silence for alerts matching the given labels.

    matchers example: [{"name": "alertname", "value": "HighErrorRate", "isRegex": False}]
    """
    starts_at = datetime.now(timezone.utc).isoformat()
    ends_at = (datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)).isoformat()
    payload = {
        "matchers": matchers,
        "startsAt": starts_at,
        "endsAt": ends_at,
        "createdBy": created_by,
        "comment": comment,
    }
    try:
        r = requests.post(f"{ALERTMANAGER_URL}/api/v2/silences", json=payload, timeout=10)
        r.raise_for_status()
        return {"success": True, "silence_id": r.json().get("silenceID"), "ends_at": ends_at}
    except requests.RequestException as e:
        return {"success": False, "error": str(e)}


def alertmanager_list_alerts(active_only: bool = True) -> dict[str, Any]:
    """List currently firing alerts."""
    try:
        params = {"active": "true" if active_only else "false"}
        r = requests.get(f"{ALERTMANAGER_URL}/api/v2/alerts", params=params, timeout=10)
        r.raise_for_status()
        alerts = r.json()
        return {
            "success": True,
            "count": len(alerts),
            "alerts": [
                {
                    "alertname": a.get("labels", {}).get("alertname"),
                    "severity": a.get("labels", {}).get("severity"),
                    "namespace": a.get("labels", {}).get("namespace"),
                    "status": a.get("status", {}).get("state"),
                    "starts_at": a.get("startsAt"),
                }
                for a in alerts
            ],
        }
    except requests.RequestException as e:
        return {"success": False, "error": str(e)}
