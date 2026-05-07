"""Cloud Logging tool wrapper — gcloud subprocess + Python SDK."""

import json
import os
import subprocess
from typing import Any

PROJECT = os.getenv("GCP_PROJECT", "")


def gcloud_logs_read(filter_query: str, limit: int = 50, project: str = "") -> dict[str, Any]:
    """Read Cloud Logging entries.

    filter_query examples:
      - 'resource.type="k8s_container" AND severity>=ERROR'
      - 'resource.labels.container_name="checkoutservice" AND textPayload:"timeout"'
    """
    proj = project or PROJECT
    if not proj:
        return {"success": False, "error": "GCP_PROJECT env var not set"}
    cmd = [
        "gcloud", "logging", "read", filter_query,
        "--project", proj,
        "--limit", str(limit),
        "--format", "json",
        "--freshness", "1h",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return {"success": False, "error": result.stderr, "returncode": result.returncode}
        entries = json.loads(result.stdout) if result.stdout.strip() else []
        return {
            "success": True,
            "count": len(entries),
            "entries": [
                {
                    "timestamp": e.get("timestamp"),
                    "severity": e.get("severity"),
                    "resource": e.get("resource", {}).get("labels", {}),
                    "message": e.get("textPayload") or e.get("jsonPayload", {}).get("message"),
                }
                for e in entries
            ],
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "gcloud logging read timed out"}
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON: {e}"}
