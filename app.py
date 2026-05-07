"""AtlasOps HF Space entry point.

Serves the custom ops console UI at / and wires the coordinator API.
This is what HF Spaces runs via the Dockerfile.
"""

import json
import os
import subprocess
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# Import coordinator internals
from agents.coordinator import handle_incident, app as coordinator_app
from agents.stream import subscribe, get_history

app = FastAPI(title="AtlasOps", docs_url="/api/docs")

# Mount coordinator routes
app.mount("/api", coordinator_app)

# Serve static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    index = static_dir / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>AtlasOps</h1><p>Static files not found.</p>")


@app.post("/inject")
async def inject_chaos(request: Request):
    """Apply a chaos scenario manifest to the real GKE cluster."""
    body = await request.json()
    scenario_id = body.get("scenario_id", "")
    manifest = Path("bench/chaos_manifests") / f"{scenario_id}.yaml"

    if not manifest.exists():
        return JSONResponse({"ok": False, "error": f"Manifest not found: {scenario_id}"}, 404)

    env = os.environ.copy()
    env["USE_GKE_GCLOUD_AUTH_PLUGIN"] = "True"
    r = subprocess.run(
        ["kubectl", "apply", "-f", str(manifest)],
        capture_output=True, text=True, env=env, timeout=15,
    )
    if r.returncode != 0:
        return JSONResponse({"ok": False, "error": r.stderr}, 500)

    # Fire the incident through the coordinator after a brief wait
    import asyncio
    asyncio.create_task(_handle_after_delay(body.get("name", scenario_id)))
    return JSONResponse({"ok": True, "scenario_id": scenario_id})


async def _handle_after_delay(name: str):
    import asyncio
    await asyncio.sleep(20)
    from agents.tools.alertmanager import alertmanager_list_alerts
    result = alertmanager_list_alerts(active_only=True)
    alert = {
        "commonLabels": {"alertname": result["alerts"][0]["alertname"] if result.get("alerts") else name},
        "alerts": result.get("alerts", []),
    }
    await handle_incident(alert)


@app.post("/reset")
async def reset_chaos():
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


@app.get("/health")
async def health():
    return JSONResponse({
        "status": "ok",
        "model": os.getenv("AGENT_MODEL", "Qwen/Qwen2.5-7B-Instruct"),
        "backend": os.getenv("BACKEND", "vllm"),
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
