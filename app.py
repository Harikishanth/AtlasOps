"""AtlasOps HF Space entry point.

Serves the custom ops console UI at / and wires the coordinator API.
This is what HF Spaces runs via the Dockerfile.
"""

import hashlib
import hmac
import json
import logging
import os
import subprocess
import time
import uuid
from pathlib import Path

from config.hf_space_env import apply_hf_space_inference_defaults

apply_hf_space_inference_defaults()

from fastapi import FastAPI, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

log = logging.getLogger("atlasops")

# ── Auth ──────────────────────────────────────────────────────────────────────
# Set ATLASOPS_API_KEY env var to enable auth on all mutating endpoints.
# If unset, mutations are allowed without a key (dev / demo mode with a warning).
_API_KEY = os.getenv("ATLASOPS_API_KEY", "")
_api_key_header = APIKeyHeader(name="X-AtlasOps-Key", auto_error=False)

# HMAC secret for validating Alertmanager webhook payloads.
# Set ALERTMANAGER_WEBHOOK_SECRET and configure Alertmanager to send:
#   Authorization: Bearer <secret>
_WEBHOOK_SECRET = os.getenv("ALERTMANAGER_WEBHOOK_SECRET", "")

if not _API_KEY:
    log.warning("ATLASOPS_API_KEY not set — mutating endpoints are unauthenticated (dev mode)")
if not _WEBHOOK_SECRET:
    log.warning("ALERTMANAGER_WEBHOOK_SECRET not set — webhook accepts unsigned payloads (dev mode)")


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _require_api_key(key: str | None = Security(_api_key_header)) -> None:
    """Dependency: validates X-AtlasOps-Key header when ATLASOPS_API_KEY is set."""
    if not _API_KEY:
        return  # dev mode — no key required
    if key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-AtlasOps-Key header")


def _verify_webhook_signature(body: bytes, authorization: str | None) -> None:
    """Validate Alertmanager webhook Bearer token when ALERTMANAGER_WEBHOOK_SECRET is set."""
    if not _WEBHOOK_SECRET:
        return  # dev mode
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header on webhook")
    token = authorization.removeprefix("Bearer ").strip()
    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(token.encode(), _WEBHOOK_SECRET.encode()):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

# Import coordinator internals
from agents.coordinator import handle_incident, app as coordinator_app
from agents.approval import approval_gate
from agents.audit import audit_log
from agents.circuit_breaker import circuit_breaker
from agents.correlator import correlator
from agents.prometheus_metrics import build_dashboard_metrics_payload
from agents.stream import subscribe, get_history

app = FastAPI(title="AtlasOps", docs_url="/api/docs")

# Mount coordinator routes
app.mount("/api", coordinator_app)

# Serve static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


class InjectRequest(BaseModel):
    scenario_id: str = Field(min_length=1)
    name: str | None = None


class InjectResponse(BaseModel):
    ok: bool
    scenario_id: str
    correlation_id: str
    kubectl_skipped: bool = False


class RuntimeConfigResponse(BaseModel):
    coordinator_url: str
    grafana_url: str
    argocd_url: str
    boutique_url: str


class ApprovalCallbackRequest(BaseModel):
    token: str = Field(min_length=1)
    decision: str = Field(min_length=1)
    approved_by: str = ""
    reason: str = ""


@app.get("/", response_class=HTMLResponse)
async def root():
    index = static_dir / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>AtlasOps</h1><p>Static files not found.</p>")


@app.post("/inject", dependencies=[Security(_require_api_key)])
async def inject_chaos(request: Request):
    """Apply a chaos scenario manifest to the real GKE cluster."""
    body = InjectRequest.model_validate(await request.json())
    scenario_id = body.scenario_id
    correlation_id = f"inj-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    manifest = Path("bench/chaos_manifests") / f"{scenario_id}.yaml"

    if not manifest.exists():
        return JSONResponse({"ok": False, "error": f"Manifest not found: {scenario_id}"}, 404)

    kubectl_skipped = _truthy_env("ATLASOPS_SKIP_KUBECTL_INJECT")
    if kubectl_skipped:
        log.warning(
            "ATLASOPS_SKIP_KUBECTL_INJECT: not applying manifests; firing incident pipeline anyway "
            "(HF Space demo without kubeconfig)."
        )
    else:
        env = os.environ.copy()
        env["USE_GKE_GCLOUD_AUTH_PLUGIN"] = "True"
        r = subprocess.run(
            ["kubectl", "apply", "-f", str(manifest)],
            capture_output=True, text=True, env=env, timeout=15,
        )
        if r.returncode != 0:
            err_msg = (r.stderr or "").strip() or r.stdout.strip() or f"exit {r.returncode}"
            return JSONResponse(
                {
                    "ok": False,
                    "error": err_msg,
                    "hint": (
                        "On Hugging Face Spaces, kubectl usually has no kubeconfig — set "
                        "ATLASOPS_SKIP_KUBECTL_INJECT=1 to run triage/diagnosis via LLMs using live "
                        "Prometheus/Alertmanager only (no chaos manifests applied)."
                    ),
                },
                500,
            )

    # Fire the incident through the coordinator after a brief wait
    import asyncio
    asyncio.create_task(_handle_after_delay(body.name or scenario_id, scenario_id, correlation_id))
    return JSONResponse(
        InjectResponse(
            ok=True,
            scenario_id=scenario_id,
            correlation_id=correlation_id,
            kubectl_skipped=kubectl_skipped,
        ).model_dump()
    )


async def _handle_after_delay(name: str, scenario_id: str, correlation_id: str):
    import asyncio
    await asyncio.sleep(20)
    from agents.tools.alertmanager import alertmanager_list_alerts
    result = alertmanager_list_alerts(active_only=True)
    alert = {
        "commonLabels": {"alertname": result["alerts"][0]["alertname"] if result.get("alerts") else name},
        "alerts": result.get("alerts", []),
        "scenario_id": scenario_id,
        "correlation_id": correlation_id,
    }
    # Route through correlator so UI-injected incidents obey the same
    # deduplication and dispatch rules as real Alertmanager webhooks.
    incident_id, _is_new, should_dispatch = correlator.ingest(alert)
    if not should_dispatch:
        return
    correlator.mark_processing(incident_id, True)
    try:
        await handle_incident(alert, incident_id=incident_id)
    finally:
        correlator.mark_processing(incident_id, False)


@app.post("/reset", dependencies=[Security(_require_api_key)])
async def reset_chaos():
    if _truthy_env("ATLASOPS_SKIP_KUBECTL_INJECT"):
        log.warning("ATLASOPS_SKIP_KUBECTL_INJECT: skipping kubectl delete on reset")
        return JSONResponse({"ok": True, "kubectl_skipped": True})
    env = os.environ.copy()
    env["USE_GKE_GCLOUD_AUTH_PLUGIN"] = "True"
    subprocess.run(
        ["kubectl", "delete",
         "podchaos,networkchaos,stresschaos,dnschaos,iochaos,timechaos",
         "--all", "-A", "--ignore-not-found=true"],
        capture_output=True, env=env,
    )
    return JSONResponse({"ok": True})


@app.get("/stream")
async def stream():
    return StreamingResponse(
        subscribe(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/thoughts")
async def thoughts():
    return JSONResponse({"thoughts": get_history()})


@app.get("/metrics")
async def proxy_metrics():
    """Server-side Prometheus proxy — avoids browser CORS on direct GKE IP access."""
    return JSONResponse(await build_dashboard_metrics_payload())


@app.get("/bench/results/comparison_table.md")
async def comparison_table_markdown():
    """UI fetches this path; serve repo file or a tiny placeholder."""
    p = Path(__file__).resolve().parent / "bench" / "results" / "comparison_table.md"
    if not p.is_file():
        return PlainTextResponse(
            "| Scenario | Outcome | Notes |\n|---|---|---|\n"
            "| *pending* | — | Run `python bench/runner.py` or `python -m bench.quick_eval` locally, then commit `bench/results/comparison_table.md`. |\n",
            media_type="text/markdown; charset=utf-8",
        )
    return PlainTextResponse(p.read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")


@app.get("/health")
async def health():
    from agents.coordinator import _live_judge_requested

    agent_base = os.getenv("VLLM_BASE", "").rstrip("/")
    ju = os.getenv("JUDGE_URL", "").rstrip("/")
    return JSONResponse({
        "status": "ok",
        "model": os.getenv("AGENT_MODEL", "Qwen/Qwen2.5-7B-Instruct"),
        "agent_base": agent_base,
        "backend": os.getenv("BACKEND", "vllm"),
        "judge_model": os.getenv("JUDGE_MODEL", ""),
        "judge_base": ju,
        "hf_inference_pack": os.getenv("ATLASOPS_USE_HF_INFERENCE", ""),
        "live_judge": _live_judge_requested(),
        "discord_webhook_configured": bool(os.getenv("DISCORD_WEBHOOK_URL", "").strip()),
        "slack_webhook_configured": bool(os.getenv("SLACK_WEBHOOK_URL", "").strip()),
    })


@app.get("/config")
async def runtime_config():
    """Expose runtime URLs so UI doesn't rely on hardcoded IPs."""
    # Empty → browser keeps `window.location.origin` (required for HF Spaces).
    coordinator_url = (os.getenv("COORDINATOR_URL") or "").strip()
    grafana_url = os.getenv("GRAFANA_URL", "")
    argocd_url = os.getenv("ARGOCD_URL", "")
    boutique_url = os.getenv("BOUTIQUE_URL", "")
    return JSONResponse(
        RuntimeConfigResponse(
            coordinator_url=coordinator_url,
            grafana_url=grafana_url,
            argocd_url=argocd_url,
            boutique_url=boutique_url,
        ).model_dump()
    )


@app.post("/approval/callback", dependencies=[Security(_require_api_key)])
async def approval_callback(request: Request):
    payload = ApprovalCallbackRequest.model_validate(await request.json())
    result = approval_gate.callback(
        token=payload.token,
        decision=payload.decision,
        approved_by=payload.approved_by,
        reason=payload.reason,
    )
    status = 200 if result.get("ok") else 400
    return JSONResponse(result, status_code=status)


@app.get("/approval/pending")
async def approval_pending():
    return JSONResponse({"pending": approval_gate.pending()})


@app.get("/circuit-breaker/status")
async def circuit_breaker_status():
    return JSONResponse(circuit_breaker.status())


@app.post("/circuit-breaker/reset", dependencies=[Security(_require_api_key)])
async def circuit_breaker_reset():
    return JSONResponse(circuit_breaker.reset())


@app.get("/incidents/active")
async def incidents_active():
    return JSONResponse({"incidents": correlator.get_active()})


@app.get("/audit/log")
async def audit_log_entries(limit: int = 100, offset: int = 0):
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    return JSONResponse({"entries": audit_log.tail(limit=limit, offset=offset)})


@app.get("/audit/verify")
async def audit_verify():
    return JSONResponse(audit_log.verify_integrity())


_TOPOLOGY_SERVICES = [
    "frontend", "cartservice", "checkoutservice", "paymentservice",
    "currencyservice", "shippingservice", "emailservice",
    "recommendationservice", "productcatalogservice", "adservice", "redis-cart",
]


@app.get("/cluster/health")
async def cluster_health():
    """Per-service health from kubectl get pods -n default."""
    env = os.environ.copy()
    env["USE_GKE_GCLOUD_AUTH_PLUGIN"] = "True"
    try:
        r = subprocess.run(
            ["kubectl", "get", "pods", "-n", "default", "-o", "json"],
            capture_output=True, text=True, env=env, timeout=8,
        )
        if r.returncode != 0:
            return JSONResponse({"ok": False, "services": {}})

        items = json.loads(r.stdout).get("items", [])
        services: dict = {}

        for pod in items:
            meta = pod.get("metadata", {})
            app_label = meta.get("labels", {}).get("app", "")
            if app_label not in _TOPOLOGY_SERVICES:
                continue

            status = pod.get("status", {})
            phase = status.get("phase", "Unknown")
            cs = status.get("containerStatuses", [])
            restarts = sum(c.get("restartCount", 0) for c in cs)
            ready_count = sum(1 for c in cs if c.get("ready", False))
            total = len(cs)

            if phase == "Running" and ready_count == total and total > 0:
                health = "healthy"
            elif phase in ("Pending", "Terminating"):
                health = "degraded"
            else:
                health = "down"

            if app_label in services:
                prev = services[app_label]
                # worst-case wins
                if "down" in (health, prev["status"]):
                    health = "down"
                elif "degraded" in (health, prev["status"]):
                    health = "degraded"
                services[app_label]["restarts"] = max(prev["restarts"], restarts)
                services[app_label]["status"] = health
            else:
                services[app_label] = {
                    "status": health,
                    "restarts": restarts,
                    "ready": f"{ready_count}/{total}",
                    "phase": phase,
                }

        for svc in _TOPOLOGY_SERVICES:
            if svc not in services:
                services[svc] = {"status": "unknown", "restarts": 0, "ready": "0/0", "phase": "?"}

        total_healthy = sum(1 for s in services.values() if s["status"] == "healthy")
        return JSONResponse({"ok": True, "services": services, "healthy": total_healthy, "total": len(_TOPOLOGY_SERVICES)})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e), "services": {}})


@app.post("/webhook")
async def webhook_proxy(request: Request):
    """Top-level Alertmanager webhook — validates signature then forwards to coordinator.

    Alertmanager config:
      receivers:
        - name: atlasops
          webhook_configs:
            - url: 'http://<host>:7860/webhook'
              http_config:
                authorization:
                  type: Bearer
                  credentials: <ALERTMANAGER_WEBHOOK_SECRET>
    """
    body = await request.body()
    _verify_webhook_signature(body, request.headers.get("Authorization"))
    import json as _json
    from agents.coordinator import app as _coord
    # Re-dispatch through coordinator's webhook handler directly
    from agents.coordinator import handle_incident
    from agents.correlator import correlator
    try:
        payload = _json.loads(body)
    except _json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    incident_id, _is_new, should_dispatch = correlator.ingest(payload)
    if not should_dispatch:
        return JSONResponse({"ok": True, "incident_id": incident_id, "dispatched": False})
    correlator.mark_processing(incident_id, True)
    import asyncio
    asyncio.create_task(_dispatch_incident(payload, incident_id))
    return JSONResponse({"ok": True, "incident_id": incident_id, "dispatched": True})


async def _dispatch_incident(payload: dict, incident_id: str) -> None:
    from agents.coordinator import handle_incident
    from agents.correlator import correlator
    try:
        await handle_incident(payload, incident_id=incident_id)
    finally:
        correlator.mark_processing(incident_id, False)


@app.get("/slack/feed")
async def slack_feed():
    """Return last 30 comms posts from the local log (powers the UI feed)."""
    log_path = Path("data/slack_posts.jsonl")
    if not log_path.exists():
        return JSONResponse({"posts": []})
    posts = []
    for line in log_path.read_text(encoding="utf-8").strip().splitlines():
        try:
            posts.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return JSONResponse({"posts": posts[-30:]})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
