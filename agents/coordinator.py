"""AtlasOps Coordinator.

Routes alerts through: Triage → Diagnosis → Remediation → Comms.
Receives Alertmanager webhooks at POST /webhook on port 9099.
Each agent is a vLLM endpoint co-hosted on the AMD MI300X.
"""

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from agents.stream import emit as thought_emit
from agents.tools import TOOL_REGISTRY


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("coordinator")


# Backend selection:
#   BACKEND=vllm   → self-hosted vLLM on AMD MI300X (default)
#   BACKEND=fireworks → Fireworks AI API (AMD GPUs, managed)
#   BACKEND=openai  → any OpenAI-compatible endpoint
BACKEND = os.getenv("BACKEND", "vllm")

_BACKEND_DEFAULTS = {
    "vllm":      ("http://localhost:8000/v1",          "Qwen/Qwen2.5-7B-Instruct"),
    "fireworks": ("https://api.fireworks.ai/inference/v1", "accounts/fireworks/models/qwen2p5-7b-instruct"),
    "openai":    ("https://api.openai.com/v1",         "gpt-4o-mini"),
}
_default_base, _default_model = _BACKEND_DEFAULTS.get(BACKEND, _BACKEND_DEFAULTS["vllm"])

VLLM_BASE  = os.getenv("VLLM_BASE",    _default_base)
MODEL_NAME = os.getenv("AGENT_MODEL",  _default_model)
API_KEY    = os.getenv("LLM_API_KEY",  "")  # required for fireworks/openai, empty for local vllm
PROMPTS_DIR = Path(__file__).parent / "prompts"
TRAJECTORIES_DIR = Path(os.getenv("TRAJECTORIES_DIR", "data/trajectories"))
TRAJECTORIES_DIR.mkdir(parents=True, exist_ok=True)


def load_prompt(role: str) -> str:
    return (PROMPTS_DIR / f"{role}.md").read_text(encoding="utf-8")


async def call_agent(role: str, user_input: dict[str, Any], max_turns: int = 10) -> dict[str, Any]:
    """Run a single agent with a tool-calling loop. Returns final JSON output."""
    system_prompt = load_prompt(role)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_input, indent=2)},
    ]
    trajectory: list[dict[str, Any]] = []

    headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
    async with httpx.AsyncClient(timeout=120, headers=headers) as client:
        for turn in range(max_turns):
            r = await client.post(
                f"{VLLM_BASE}/chat/completions",
                json={
                    "model": MODEL_NAME,
                    "messages": messages,
                    "temperature": 0.2,
                    "tools": _tool_schemas_for_role(role),
                    "tool_choice": "auto",
                },
            )
            r.raise_for_status()
            choice = r.json()["choices"][0]
            msg = choice["message"]
            messages.append(msg)

            if not msg.get("tool_calls"):
                conclusion = msg["content"] or ""
                thought_emit(role, "conclusion", _summarise_conclusion(role, conclusion))
                trajectory.append({"role": role, "turn": turn, "content": conclusion})
                return {"role": role, "trajectory": trajectory, "final": _try_parse_json(conclusion)}

            for tc in msg["tool_calls"]:
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"])
                # Narrate the tool call
                thought_emit(role, "tool_call",
                             _narrate_tool_call(role, fn_name, fn_args),
                             tool=fn_name)
                fn = TOOL_REGISTRY.get(fn_name)
                if not fn:
                    tool_output = {"error": f"Unknown tool: {fn_name}"}
                else:
                    try:
                        tool_output = fn(**fn_args)
                    except Exception as e:
                        tool_output = {"error": f"Tool execution failed: {e}"}
                # Narrate the result
                thought_emit(role, "tool_result",
                             _narrate_tool_result(fn_name, tool_output),
                             tool=fn_name,
                             result_summary=str(tool_output)[:200])
                trajectory.append({"role": role, "turn": turn, "tool": fn_name, "args": fn_args, "output": tool_output})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(tool_output)[:8000],
                })

    log.warning("%s exceeded %d turns", role, max_turns)
    return {"role": role, "trajectory": trajectory, "final": {"error": "max_turns_exceeded"}}


def _narrate_tool_call(role: str, tool: str, args: dict) -> str:
    narrations = {
        "kubectl_get":           lambda a: f"Checking {a.get('resource','pods')} across the cluster...",
        "kubectl_logs":          lambda a: f"Reading logs from {a.get('pod','pod')} — looking for errors...",
        "kubectl_describe":      lambda a: f"Describing {a.get('resource','')} {a.get('name','')} — checking events...",
        "kubectl_top_pods":      lambda a: "Checking CPU/memory pressure across all pods...",
        "kubectl_rollout":       lambda a: f"Running rollout {a.get('action','')} on {a.get('resource','')}...",
        "kubectl_scale":         lambda a: f"Scaling {a.get('deployment','')} to {a.get('replicas','')} replicas...",
        "promql_query":          lambda a: f"Querying Prometheus: `{str(a.get('query',''))[:80]}`",
        "promql_query_range":    lambda a: f"Checking metric trend: `{str(a.get('query',''))[:80]}`",
        "jaeger_search":         lambda a: f"Searching traces for {a.get('service','')} (last {a.get('lookback','15m')})...",
        "jaeger_get_trace":      lambda a: f"Fetching trace {a.get('trace_id','')[:16]}... — following the span chain...",
        "argocd_list_apps":      lambda a: "Checking Argo CD for recent deployments...",
        "argocd_app_history":    lambda a: f"Checking deploy history for {a.get('app','')}...",
        "argocd_rollback":       lambda a: f"Rolling back {a.get('app','')} to revision {a.get('revision','')}...",
        "gcloud_logs_read":      lambda a: f"Reading Cloud Logging: `{str(a.get('filter_query',''))[:80]}`",
        "cloud_monitoring_query":lambda a: f"Querying GCP metric: {a.get('metric_type','')}",
        "alertmanager_silence":  lambda a: f"Silencing alert for {a.get('duration_minutes',30)} min — suppressing noise...",
        "slack_post_update":     lambda a: f"Posting [{a.get('severity','')}] incident update to Slack...",
        "postmortem_draft":      lambda a: "Drafting postmortem — building timeline from incident data...",
    }
    fn = narrations.get(tool)
    return fn(args) if fn else f"Calling {tool}..."


def _narrate_tool_result(tool: str, output: dict) -> str:
    if not output.get("success", True):
        return f"⚠️ {tool} returned an error: {str(output.get('error',''))[:100]}"
    result_narrations = {
        "kubectl_get":       "Got cluster state.",
        "kubectl_logs":      "Got pod logs — scanning for stack traces and errors.",
        "promql_query":      f"Got metric data — analysing values.",
        "jaeger_search":     f"Found traces — checking for slow spans.",
        "argocd_rollback":   "✅ Rollback executed.",
        "kubectl_scale":     "✅ Scale applied.",
        "slack_post_update": "✅ Slack notified.",
        "postmortem_draft":  "✅ Postmortem saved.",
    }
    return result_narrations.get(tool, f"{tool} completed.")


def _summarise_conclusion(role: str, content: str) -> str:
    summaries = {
        "triage":      "Triage complete — severity assigned, blast radius mapped, handing to Diagnosis.",
        "diagnosis":   "Root cause identified — handing remediation plan to Remediation agent.",
        "remediation": "Remediation complete — verifying resolution with Prometheus.",
        "comms":       "Incident closed — Slack updated, postmortem saved.",
    }
    return summaries.get(role, f"{role} agent finished.")


def _tool_schemas_for_role(role: str) -> list[dict[str, Any]]:
    role_tools = {
        "triage": ["kubectl_get", "kubectl_top_pods", "alertmanager_list_alerts", "promql_query"],
        "diagnosis": ["promql_query", "promql_query_range", "jaeger_search", "jaeger_get_trace",
                      "kubectl_logs", "kubectl_describe", "kubectl_get", "kubectl_top_pods",
                      "argocd_list_apps", "argocd_app_history", "gcloud_logs_read",
                      "cloud_monitoring_query"],
        "remediation": ["argocd_rollback", "kubectl_rollout", "kubectl_scale",
                        "alertmanager_silence", "promql_query", "kubectl_get", "kubectl_describe",
                        "slack_post_update"],
        "comms": ["slack_post_update", "postmortem_draft"],
    }
    return [_tool_schema(name) for name in role_tools.get(role, [])]


def _tool_schema(name: str) -> dict[str, Any]:
    """Generate OpenAI-format tool schema. Hand-rolled minimal version — vLLM tolerates it."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Real SRE tool: {name}",
            "parameters": {"type": "object", "additionalProperties": True},
        },
    }


def _try_parse_json(content: str) -> dict[str, Any]:
    if not content:
        return {}
    try:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            return json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        pass
    return {"raw": content}


async def handle_incident(alert: dict[str, Any]) -> dict[str, Any]:
    """Run the full agent chain for one incident."""
    incident_id = f"inc-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    log.info("[%s] handling alert: %s", incident_id, alert.get("commonLabels", {}).get("alertname"))

    triage = await call_agent("triage", {"incident_id": incident_id, "alert": alert})
    diagnosis = await call_agent("diagnosis", {"incident_id": incident_id, "triage": triage["final"]})
    remediation = await call_agent("remediation", {
        "incident_id": incident_id, "triage": triage["final"], "diagnosis": diagnosis["final"],
    })
    comms = await call_agent("comms", {
        "incident_id": incident_id,
        "triage": triage["final"],
        "diagnosis": diagnosis["final"],
        "remediation": remediation["final"],
    })

    full_record = {
        "incident_id": incident_id,
        "alert": alert,
        "triage": triage,
        "diagnosis": diagnosis,
        "remediation": remediation,
        "comms": comms,
    }
    (TRAJECTORIES_DIR / f"{incident_id}.json").write_text(
        json.dumps(full_record, indent=2), encoding="utf-8",
    )
    return full_record


app = FastAPI(title="AtlasOps Coordinator")


@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()
    log.info("received alertmanager webhook: %d alerts", len(payload.get("alerts", [])))
    result = await handle_incident(payload)
    return JSONResponse({"ok": True, "incident_id": result["incident_id"]})


@app.get("/stream")
async def stream_thoughts():
    """SSE endpoint — dashboard subscribes here for live agent thoughts."""
    from agents.stream import subscribe
    return StreamingResponse(
        subscribe(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/thoughts")
async def get_thoughts():
    """Return full thought history for the timeline tab."""
    from agents.stream import get_history
    return {"thoughts": get_history()}


@app.get("/health")
async def health():
    return {"status": "ok", "vllm": VLLM_BASE, "model": MODEL_NAME}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9099)
