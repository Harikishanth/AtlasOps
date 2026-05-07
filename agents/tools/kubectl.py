"""kubectl tool wrappers — real subprocess calls to kubectl."""

import json
import subprocess
from typing import Any


def _run(cmd: list[str], timeout: int = 30) -> dict[str, Any]:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
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


def kubectl_get(resource: str, namespace: str = "-A", output: str = "json") -> dict[str, Any]:
    """Get Kubernetes resources. resource examples: 'pods', 'deployments', 'services'."""
    cmd = ["kubectl", "get", resource, "-o", output]
    if namespace == "-A":
        cmd.append("-A")
    else:
        cmd.extend(["-n", namespace])
    result = _run(cmd)
    if result.get("success") and output == "json":
        try:
            result["parsed"] = json.loads(result["stdout"])
        except json.JSONDecodeError:
            pass
    return result


def kubectl_describe(resource: str, name: str, namespace: str = "default") -> dict[str, Any]:
    """Describe a specific Kubernetes resource."""
    return _run(["kubectl", "describe", resource, name, "-n", namespace])


def kubectl_logs(pod: str, namespace: str = "default", tail: int = 200,
                 container: str = "") -> dict[str, Any]:
    """Get pod logs."""
    cmd = ["kubectl", "logs", pod, "-n", namespace, f"--tail={tail}"]
    if container:
        cmd.extend(["-c", container])
    return _run(cmd, timeout=20)


def kubectl_top_pods(namespace: str = "-A") -> dict[str, Any]:
    """Get CPU/memory usage for pods."""
    cmd = ["kubectl", "top", "pods"]
    if namespace == "-A":
        cmd.append("-A")
    else:
        cmd.extend(["-n", namespace])
    return _run(cmd)


def kubectl_top_nodes() -> dict[str, Any]:
    """Get CPU/memory usage for nodes."""
    return _run(["kubectl", "top", "nodes"])


def kubectl_rollout(action: str, resource: str, namespace: str = "default") -> dict[str, Any]:
    """Rollout operations: undo, status, history. action in {undo, status, history}."""
    if action not in ("undo", "status", "history"):
        return {"error": f"Invalid rollout action: {action}", "success": False}
    return _run(["kubectl", "rollout", action, resource, "-n", namespace], timeout=60)


def kubectl_scale(deployment: str, replicas: int, namespace: str = "default") -> dict[str, Any]:
    """Scale a deployment to the given replica count."""
    if not (0 <= replicas <= 20):
        return {"error": "replicas must be 0–20", "success": False}
    return _run(
        ["kubectl", "scale", "deployment", deployment,
         f"--replicas={replicas}", "-n", namespace],
        timeout=30,
    )


def kubectl_exec(pod: str, command: list[str], namespace: str = "default") -> dict[str, Any]:
    """Execute a read-only command inside a pod. Allowlisted commands only."""
    allowlist = {"ls", "cat", "env", "ps", "df", "free", "netstat", "ss", "curl", "wget",
                 "nslookup", "dig", "ping", "hostname", "id", "whoami", "date", "uptime"}
    if not command or command[0] not in allowlist:
        return {
            "error": f"Command '{command[0] if command else ''}' not in allowlist",
            "success": False,
        }
    return _run(
        ["kubectl", "exec", pod, "-n", namespace, "--"] + command,
        timeout=15,
    )
