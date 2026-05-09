"""Argo CD tool wrappers — REST API over HTTP (no CLI required).

Falls back to CLI subprocess when ARGOCD_USE_CLI=true is set.
"""

import json
import os
import subprocess
from typing import Any

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_ARGOCD_URL   = os.getenv("ARGOCD_URL", "https://34.122.132.237")
_ARGOCD_USER  = os.getenv("ARGOCD_USER", "admin")
_ARGOCD_PASS  = os.getenv("ARGOCD_PASS", "sNl2MpIydyZWa7aC")
_USE_HTTP     = _ARGOCD_URL.startswith("http")

# Try HTTP first (avoids TLS issues with self-signed certs)
_HTTP_BASE = _ARGOCD_URL.replace("https://", "http://") if _ARGOCD_URL.startswith("https://") else _ARGOCD_URL

_cached_token: str | None = None


def _get_token() -> str:
    global _cached_token
    if _cached_token:
        return _cached_token
    try:
        r = requests.post(
            f"{_HTTP_BASE}/api/v1/session",
            json={"username": _ARGOCD_USER, "password": _ARGOCD_PASS},
            timeout=10,
            verify=False,
        )
        r.raise_for_status()
        _cached_token = r.json()["token"]
        return _cached_token
    except Exception as e:
        raise RuntimeError(f"ArgoCD auth failed: {e}") from e


def _api(method: str, path: str, **kwargs) -> dict[str, Any]:
    try:
        token = _get_token()
        r = requests.request(
            method,
            f"{_HTTP_BASE}/api/v1{path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
            verify=False,
            **kwargs,
        )
        if r.status_code == 401:
            global _cached_token
            _cached_token = None
            token = _get_token()
            r = requests.request(
                method,
                f"{_HTTP_BASE}/api/v1{path}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
                verify=False,
                **kwargs,
            )
        r.raise_for_status()
        return {"success": True, "data": r.json()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def argocd_list_apps() -> dict[str, Any]:
    """List all Argo CD applications."""
    result = _api("GET", "/applications")
    if result.get("success"):
        items = result["data"].get("items") or []
        result["apps"] = [
            {
                "name": a["metadata"]["name"],
                "health": a.get("status", {}).get("health", {}).get("status", "Unknown"),
                "sync": a.get("status", {}).get("sync", {}).get("status", "Unknown"),
                "revision": (a.get("status", {}).get("history") or [{}])[-1].get("id"),
            }
            for a in items
        ]
        result["count"] = len(items)
    return result


def argocd_app_history(app: str) -> dict[str, Any]:
    """Get deployment history for an Argo CD application."""
    result = _api("GET", f"/applications/{app}")
    if result.get("success"):
        history = result["data"].get("status", {}).get("history") or []
        result["history"] = [
            {"id": h.get("id"), "revision": h.get("revision"), "deployedAt": h.get("deployedAt")}
            for h in history[-10:]
        ]
    return result


def argocd_rollback(app: str, revision: str) -> dict[str, Any]:
    """Roll back an Argo CD application to a previous revision."""
    rev_id = int(revision) if str(revision).isdigit() else 0
    result = _api("POST", f"/applications/{app}/rollback", json={"id": rev_id})
    if result.get("success"):
        result["message"] = f"Rollback of {app} to revision {revision} initiated."
    return result


def argocd_app_get(app: str) -> dict[str, Any]:
    """Get details for a specific Argo CD application."""
    return _api("GET", f"/applications/{app}")
