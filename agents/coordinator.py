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
from pydantic import BaseModel, Field

from agents.approval import approval_gate, approval_mode_for_severity
from agents.audit import audit_log
from agents.circuit_breaker import CircuitBreakerTripped, circuit_breaker
from agents.correlator import correlator
from agents.stream import emit as thought_emit
from agents.tools import TOOL_REGISTRY
from config.runtime import StepRewardTracker


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

# Backend-enforced safety policy. Prompt guidance is useful, but runtime must
# still guard high-impact tools in case a model issues unsafe calls.
MUTATING_TOOLS = {
    "argocd_rollback",
    "kubectl_rollout",
    "kubectl_scale",
    "alertmanager_silence",
    "slack_post_update",
}
ROLE_ALLOWED_TOOLS = {
    "triage": {"kubectl_get", "kubectl_top_pods", "alertmanager_list_alerts", "promql_query"},
    "diagnosis": {
        "promql_query",
        "promql_query_range",
        "jaeger_search",
        "jaeger_get_trace",
        "kubectl_logs",
        "kubectl_describe",
        "kubectl_get",
        "kubectl_top_pods",
        "argocd_list_apps",
        "argocd_app_history",
        "gcloud_logs_read",
        "cloud_monitoring_query",
    },
    "remediation": {
        "argocd_rollback",
        "kubectl_rollout",
        "kubectl_scale",
        "alertmanager_silence",
        "promql_query",
        "kubectl_get",
        "kubectl_describe",
        "slack_post_update",
    },
    "comms": {"slack_post_update", "postmortem_draft"},
}


class AlertWebhookPayload(BaseModel):
    alerts: list[dict[str, Any]] = Field(default_factory=list)
    commonLabels: dict[str, Any] = Field(default_factory=dict)
    status: str | None = None


def load_prompt(role: str) -> str:
    return (PROMPTS_DIR / f"{role}.md").read_text(encoding="utf-8")


async def call_agent(role: str, user_input: dict[str, Any], max_turns: int = 10) -> dict[str, Any]:
    """Run a single agent with a tool-calling loop. Returns final JSON output."""
    system_prompt = load_prompt(role)
    incident_id = str(user_input.get("incident_id", "unknown"))
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_input, indent=2)},
    ]
    trajectory: list[dict[str, Any]] = []
    step_tracker = StepRewardTracker()

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
                return {
                    "role": role,
                    "trajectory": trajectory,
                    "final": _try_parse_json(conclusion),
                    "step_reward_summary": step_tracker.summary(),
                }

            for tc in msg["tool_calls"]:
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"])
                policy_error = _check_tool_policy(role, fn_name, fn_args, user_input)
                if policy_error:
                    tool_output = {"success": False, "error": policy_error}
                    audit_log.record(
                        incident_id=incident_id,
                        agent_role=role,
                        action_type="tool_result",
                        tool_name=fn_name,
                        tool_args=fn_args,
                        result_summary=policy_error,
                        policy_check="blocked_by_policy",
                    )
                    thought_emit(role, "tool_result", f"⚠️ blocked by policy: {policy_error}", tool=fn_name)
                    trajectory.append(
                        {
                            "role": role,
                            "turn": turn,
                            "tool": fn_name,
                            "args": fn_args,
                            "output": tool_output,
                            "blocked_by_policy": True,
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps(tool_output),
                        }
                    )
                    continue
                # Narrate the tool call
                thought_emit(role, "tool_call",
                             _narrate_tool_call(role, fn_name, fn_args),
                             tool=fn_name)
                audit_log.record(
                    incident_id=incident_id,
                    agent_role=role,
                    action_type="tool_call",
                    tool_name=fn_name,
                    tool_args=fn_args,
                    policy_check="allowed",
                )
                try:
                    circuit_breaker.check_before_tool_call(
                        incident_id=incident_id,
                        tool_name=fn_name,
                        is_mutating=fn_name in MUTATING_TOOLS,
                    )
                except CircuitBreakerTripped as e:
                    tool_output = {"success": False, "error": str(e), "blocked_by_circuit_breaker": True}
                    audit_log.record(
                        incident_id=incident_id,
                        agent_role=role,
                        action_type="tool_result",
                        tool_name=fn_name,
                        tool_args=fn_args,
                        result_summary=str(e),
                        policy_check="blocked_by_circuit_breaker",
                    )
                    thought_emit(role, "tool_result", f"⛔ blocked by circuit breaker: {e}", tool=fn_name)
                    trajectory.append(
                        {
                            "role": role,
                            "turn": turn,
                            "tool": fn_name,
                            "args": fn_args,
                            "output": tool_output,
                            "blocked_by_circuit_breaker": True,
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps(tool_output),
                        }
                    )
                    continue
                fn = TOOL_REGISTRY.get(fn_name)
                if not fn:
                    tool_output = {"error": f"Unknown tool: {fn_name}"}
                else:
                    try:
                        tool_output = fn(**fn_args)
                    except Exception as e:
                        tool_output = {"error": f"Tool execution failed: {e}"}
                # Dense per-step reward signal
                step_reward = step_tracker.record(fn_name, fn_args, tool_output)
                # Narrate the result
                audit_log.record(
                    incident_id=incident_id,
                    agent_role=role,
                    action_type="tool_result",
                    tool_name=fn_name,
                    tool_args=fn_args,
                    result_summary=str(tool_output)[:300],
                    policy_check="allowed",
                )
                thought_emit(role, "tool_result",
                             _narrate_tool_result(fn_name, tool_output),
                             tool=fn_name,
                             result_summary=str(tool_output)[:200])
                trajectory.append({
                    "role": role, "turn": turn, "tool": fn_name,
                    "args": fn_args, "output": tool_output,
                    "step_reward": step_reward,
                })
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
    return [_tool_schema(name) for name in ROLE_ALLOWED_TOOLS.get(role, set())]


def _tool_schema(name: str) -> dict[str, Any]:
    """Generate OpenAI-format tool schema with strict known arguments."""
    schema_map: dict[str, dict[str, Any]] = {
        "kubectl_get": {"type": "object", "properties": {"resource": {"type": "string"}, "namespace": {"type": "string"}, "output": {"type": "string"}}, "required": ["resource"], "additionalProperties": False},
        "kubectl_describe": {"type": "object", "properties": {"resource": {"type": "string"}, "name": {"type": "string"}, "namespace": {"type": "string"}}, "required": ["resource", "name"], "additionalProperties": False},
        "kubectl_logs": {"type": "object", "properties": {"pod": {"type": "string"}, "namespace": {"type": "string"}, "tail": {"type": "integer"}, "container": {"type": "string"}}, "required": ["pod"], "additionalProperties": False},
        "kubectl_top_pods": {"type": "object", "properties": {"namespace": {"type": "string"}}, "additionalProperties": False},
        "kubectl_rollout": {"type": "object", "properties": {"action": {"type": "string"}, "resource": {"type": "string"}, "namespace": {"type": "string"}}, "required": ["action", "resource"], "additionalProperties": False},
        "kubectl_scale": {"type": "object", "properties": {"deployment": {"type": "string"}, "replicas": {"type": "integer"}, "namespace": {"type": "string"}}, "required": ["deployment", "replicas"], "additionalProperties": False},
        "promql_query": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False},
        "promql_query_range": {"type": "object", "properties": {"query": {"type": "string"}, "start": {"type": "number"}, "end": {"type": "number"}, "step": {"type": "string"}}, "required": ["query"], "additionalProperties": False},
        "jaeger_search": {"type": "object", "properties": {"service": {"type": "string"}, "lookback": {"type": "string"}, "limit": {"type": "integer"}, "min_duration": {"type": "string"}}, "required": ["service"], "additionalProperties": False},
        "jaeger_get_trace": {"type": "object", "properties": {"trace_id": {"type": "string"}}, "required": ["trace_id"], "additionalProperties": False},
        "argocd_list_apps": {"type": "object", "properties": {}, "additionalProperties": False},
        "argocd_app_history": {"type": "object", "properties": {"app": {"type": "string"}}, "required": ["app"], "additionalProperties": False},
        "argocd_rollback": {"type": "object", "properties": {"app": {"type": "string"}, "revision": {"type": "string"}}, "required": ["app", "revision"], "additionalProperties": False},
        "gcloud_logs_read": {"type": "object", "properties": {"filter_query": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["filter_query"], "additionalProperties": False},
        "cloud_monitoring_query": {"type": "object", "properties": {"metric_type": {"type": "string"}, "lookback_seconds": {"type": "integer"}}, "required": ["metric_type"], "additionalProperties": False},
        "alertmanager_list_alerts": {"type": "object", "properties": {"active_only": {"type": "boolean"}}, "additionalProperties": False},
        "alertmanager_silence": {"type": "object", "properties": {"matchers": {"type": "array"}, "duration_minutes": {"type": "integer"}, "comment": {"type": "string"}}, "required": ["matchers"], "additionalProperties": False},
        "slack_post_update": {"type": "object", "properties": {"channel": {"type": "string"}, "severity": {"type": "string"}, "title": {"type": "string"}, "summary": {"type": "string"}, "action_items": {"type": "array"}}, "required": ["channel", "severity", "title", "summary"], "additionalProperties": False},
        "postmortem_draft": {"type": "object", "properties": {"incident": {"type": "object"}, "output_path": {"type": "string"}}, "required": ["incident"], "additionalProperties": False},
    }
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Real SRE tool: {name}",
            "parameters": schema_map.get(name, {"type": "object", "additionalProperties": False}),
        },
    }


def _extract_severity(user_input: dict[str, Any]) -> str:
    triage = user_input.get("triage", {}) if isinstance(user_input, dict) else {}
    sev = str(triage.get("severity", "")).upper()
    return sev if sev in {"P0", "P1", "P2", "P3"} else "UNKNOWN"


def _check_tool_policy(role: str, tool: str, args: dict[str, Any], user_input: dict[str, Any]) -> str | None:
    if tool not in ROLE_ALLOWED_TOOLS.get(role, set()):
        return f"tool `{tool}` not allowed for role `{role}`"

    if role != "remediation" and tool in MUTATING_TOOLS:
        return f"mutating tool `{tool}` blocked outside remediation role"

    # Guard high-impact operations to avoid accidental destructive actions.
    if role == "remediation":
        severity = _extract_severity(user_input)
        if tool == "alertmanager_silence":
            duration = int(args.get("duration_minutes", 30))
            if duration > 30:
                return "silence duration cannot exceed 30 minutes"
        if tool == "kubectl_scale":
            replicas = int(args.get("replicas", 0))
            if replicas < 0 or replicas > 20:
                return "replicas must stay within 0..20"
        if tool == "argocd_rollback" and severity in {"UNKNOWN", "P3"}:
            return "rollback requires confirmed incident severity P0/P1/P2"
    return None


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


def _remediation_plan_summary(triage: dict[str, Any], diagnosis: dict[str, Any]) -> str:
    severity = str(triage.get("severity", "UNKNOWN"))
    root_cause = str(diagnosis.get("root_cause", "unspecified root cause"))
    plan = str(diagnosis.get("recommended_fix", diagnosis.get("next_action", "apply safe rollback/scale")))
    return f"{severity} incident; root cause: {root_cause}; proposal: {plan}"


def _manual_remediation_record(incident_id: str, triage: dict[str, Any], diagnosis: dict[str, Any]) -> dict[str, Any]:
    summary = _remediation_plan_summary(triage, diagnosis)
    runbook = [
        "Validate blast radius with kubectl_get, promql_query, and jaeger_search.",
        "Review latest Argo CD history for affected app and identify safe rollback target.",
        "Apply remediation manually (rollback/scale) using change-management policy.",
        "Verify error rate and saturation return to baseline for at least 5 minutes.",
        "Document resolution and communicate timeline in comms update.",
    ]
    return {
        "role": "remediation",
        "trajectory": [],
        "final": {
            "incident_id": incident_id,
            "mode": "manual",
            "status": "skipped_execution",
            "summary": summary,
            "runbook": runbook,
        },
    }


async def handle_incident(alert: dict[str, Any], incident_id: str | None = None) -> dict[str, Any]:
    """Run the full agent chain for one incident."""
    incident_id = incident_id or f"inc-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    log.info("[%s] handling alert: %s", incident_id, alert.get("commonLabels", {}).get("alertname"))
    audit_log.record(
        incident_id=incident_id,
        agent_role="coordinator",
        action_type="incident_start",
        result_summary=alert.get("commonLabels", {}).get("alertname", "unknown-alert"),
    )
    circuit_breaker.start_incident()

    resolved = False
    try:
        triage = await call_agent("triage", {"incident_id": incident_id, "alert": alert})
        diagnosis = await call_agent("diagnosis", {"incident_id": incident_id, "triage": triage["final"]})
        severity = _extract_severity({"triage": triage.get("final", {})})
        approval_mode = approval_mode_for_severity(severity)
        remediation_input = {
            "incident_id": incident_id,
            "triage": triage["final"],
            "diagnosis": diagnosis["final"],
            "approval_mode": approval_mode,
        }
        if approval_mode == "manual":
            thought_emit(
                "remediation",
                "waiting_approval",
                "Manual mode for P0 incident — generating runbook for human execution.",
            )
            remediation = _manual_remediation_record(incident_id, triage["final"], diagnosis["final"])
        elif approval_mode == "approve":
            summary = _remediation_plan_summary(triage["final"], diagnosis["final"])
            req = approval_gate.request(incident_id=incident_id, severity=severity, summary=summary)
            audit_log.record(
                incident_id=incident_id,
                agent_role="remediation",
                action_type="approval_requested",
                result_summary=summary,
                policy_check="requires_approval",
            )
            thought_emit(
                "remediation",
                "waiting_approval",
                f"Awaiting human approval for remediation plan (token: {req.token}).",
            )
            approval_result = await approval_gate.wait_for_decision(incident_id)
            status = approval_result["status"]
            # "timeout" auto-approves so demos/unattended runs still complete.
            # Only an explicit "rejected" decision skips remediation.
            if status == "rejected":
                audit_log.record(
                    incident_id=incident_id,
                    agent_role="remediation",
                    action_type="approval_decision",
                    result_summary=status,
                    approved_by=approval_result.get("approved_by", ""),
                    policy_check="approval_denied",
                )
                thought_emit("remediation", "conclusion", "Remediation skipped — approval rejected by operator.")
                remediation = {
                    "role": "remediation",
                    "trajectory": [],
                    "final": {
                        "incident_id": incident_id,
                        "mode": "approve",
                        "status": "approval_rejected",
                        "approval": approval_result,
                    },
                }
            else:
                approver = approval_result.get("approved_by") or (
                    "auto-timeout" if status == "timeout" else "human-operator"
                )
                audit_log.record(
                    incident_id=incident_id,
                    agent_role="remediation",
                    action_type="approval_decision",
                    result_summary="approved",
                    approved_by=approver,
                    policy_check="approval_granted",
                )
                thought_emit("remediation", "thinking", f"Approval granted by {approver}; executing plan.")
                remediation_input["approval"] = approval_result
                remediation = await call_agent("remediation", remediation_input)
        else:
            remediation = await call_agent("remediation", remediation_input)
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
        # Derive resolved from actual remediation outcome, not just non-rejection.
        # "skipped_execution" (P0 manual), "approval_rejected", "approval_timeout"
        # are all non-resolved states. Only explicit "resolved" outcome counts.
        remediation_final = remediation.get("final", {})
        resolved = (
            remediation_final.get("outcome") == "resolved"
            or remediation_final.get("status") == "resolved"
        )
        audit_log.record(
            incident_id=incident_id,
            agent_role="coordinator",
            action_type="incident_end",
            result_summary="resolved" if resolved else "not_resolved",
        )
        return full_record
    finally:
        circuit_breaker.finish_incident(incident_id, resolved=resolved)


app = FastAPI(title="AtlasOps Coordinator")


_WEBHOOK_SECRET = os.getenv("ALERTMANAGER_WEBHOOK_SECRET", "")


@app.post("/webhook")
async def webhook(request: Request):
    body = await request.body()

    # Validate Bearer token when secret is configured
    if _WEBHOOK_SECRET:
        import hmac as _hmac
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Missing Authorization header")
        token = auth.removeprefix("Bearer ").strip()
        if not _hmac.compare_digest(token.encode(), _WEBHOOK_SECRET.encode()):
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    payload = AlertWebhookPayload.model_validate(json.loads(body)).model_dump()
    log.info("received alertmanager webhook: %d alerts", len(payload.get("alerts", [])))
    incident_id, _is_new, should_dispatch = correlator.ingest(payload)
    if not should_dispatch:
        return JSONResponse({"ok": True, "incident_id": incident_id, "correlated": True, "dispatched": False})
    correlator.mark_processing(incident_id, True)
    try:
        result = await handle_incident(payload, incident_id=incident_id)
        return JSONResponse({"ok": True, "incident_id": result["incident_id"], "correlated": True, "dispatched": True})
    finally:
        correlator.mark_processing(incident_id, False)


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
