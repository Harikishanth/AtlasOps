"""Argo CD tool wrappers — CLI subprocess calls."""

import json
import subprocess
from typing import Any


def _run(cmd: list[str], timeout: int = 30) -> dict[str, Any]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout}s", "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}


def argocd_list_apps() -> dict[str, Any]:
    """List all Argo CD applications."""
    result = _run(["argocd", "app", "list", "-o", "json"])
    if result.get("success"):
        try:
            result["parsed"] = json.loads(result["stdout"])
        except json.JSONDecodeError:
            pass
    return result


def argocd_app_history(app: str) -> dict[str, Any]:
    """Get deployment history for an Argo CD application."""
    return _run(["argocd", "app", "history", app, "-o", "wide"])


def argocd_rollback(app: str, revision: str) -> dict[str, Any]:
    """Roll back an Argo CD application to a previous revision (real action)."""
    return _run(["argocd", "app", "rollback", app, revision], timeout=120)


def argocd_app_get(app: str) -> dict[str, Any]:
    """Get details for a specific Argo CD application."""
    result = _run(["argocd", "app", "get", app, "-o", "json"])
    if result.get("success"):
        try:
            result["parsed"] = json.loads(result["stdout"])
        except json.JSONDecodeError:
            pass
    return result
