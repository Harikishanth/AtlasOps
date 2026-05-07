"""Adversarial Scenario Designer.

Qwen2.5-72B judge analyses the agent's failure history and generates
brand-new Chaos Mesh YAML manifests targeting specific weaknesses.

Every run produces unique, never-seen-before scenarios — the benchmark
gets harder as the model improves, making the test set impossible to memorise.
"""

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


JUDGE_URL   = os.getenv("JUDGE_URL",   "http://localhost:8001/v1")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "Qwen/Qwen2.5-72B-Instruct")
API_KEY     = os.getenv("LLM_API_KEY", "")

ADVERSARIAL_DIR = Path("bench/chaos_manifests/adversarial")
ADVERSARIAL_DIR.mkdir(parents=True, exist_ok=True)

# All Chaos Mesh fault primitives the designer can combine
AVAILABLE_PRIMITIVES = [
    "PodChaos(pod-kill)",
    "PodChaos(pod-failure)",
    "PodChaos(container-kill)",
    "NetworkChaos(delay)",
    "NetworkChaos(loss)",
    "NetworkChaos(corrupt)",
    "NetworkChaos(duplicate)",
    "NetworkChaos(partition)",
    "StressChaos(cpu)",
    "StressChaos(memory)",
    "DNSChaos(error)",
    "DNSChaos(random)",
    "IOChaos(fault)",
    "IOChaos(latency)",
    "TimeChaos(offset)",
]

SERVICES = [
    "frontend", "cartservice", "checkoutservice", "paymentservice",
    "currencyservice", "shippingservice", "emailservice",
    "recommendationservice", "productcatalogservice", "adservice",
    "redis-cart",
]

DESIGNER_SYSTEM_PROMPT = """You are an elite chaos engineering adversary.
Your job is to design Kubernetes chaos experiments that will expose weaknesses
in an AI SRE agent's incident response capabilities.

You will be given:
1. The agent's recent failure history (which scenarios it struggled with)
2. The available Chaos Mesh fault primitives
3. The available target services

You must output a JSON object describing a NEW chaos scenario that:
- Targets the agent's SPECIFIC weaknesses (not generic failures)
- Combines 2-4 fault primitives simultaneously for realism
- Includes at least one red herring (a fault that LOOKS related but isn't the root cause)
- Has a clear root cause chain that requires multi-step reasoning to find

Output ONLY this JSON (no markdown, no explanation):
{
  "scenario_id": "adv-<unique-slug>",
  "title": "<one-line description>",
  "difficulty": "hard|expert|extreme",
  "root_cause_chain": ["service_A → symptom", "service_B → cascade"],
  "red_herrings": ["service_C looks broken but isn't the cause"],
  "weakness_targeted": "<which agent weakness this exploits>",
  "faults": [
    {
      "kind": "PodChaos|NetworkChaos|StressChaos|DNSChaos|IOChaos|TimeChaos",
      "action": "<specific action>",
      "target_service": "<service name>",
      "params": {"key": "value"}
    }
  ]
}"""


async def _call_judge(prompt: str) -> str:
    headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
    async with httpx.AsyncClient(timeout=60, headers=headers) as client:
        r = await client.post(
            f"{JUDGE_URL}/chat/completions",
            json={
                "model": JUDGE_MODEL,
                "messages": [
                    {"role": "system", "content": DESIGNER_SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                "temperature": 0.9,  # high temp = maximum creativity
            },
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def _extract_weaknesses(failure_history: list[dict]) -> list[str]:
    """Summarise what the agent repeatedly fails at."""
    weakness_counts: dict[str, int] = {}
    for episode in failure_history:
        if episode.get("resolved"):
            continue
        tier    = episode.get("tier", "unknown")
        sc_id   = episode.get("scenario_id", "")
        judge   = episode.get("judge", {}) or {}
        if judge.get("reasoning", 1.0) < 0.4:
            weakness_counts["poor evidence-gathering"] = weakness_counts.get("poor evidence-gathering", 0) + 1
        if judge.get("efficiency", 1.0) < 0.4:
            weakness_counts["unsafe remediation shortcuts"] = weakness_counts.get("unsafe remediation shortcuts", 0) + 1
        if "dns" in sc_id.lower():
            weakness_counts["DNS failure diagnosis"] = weakness_counts.get("DNS failure diagnosis", 0) + 1
        if "cascade" in tier:
            weakness_counts["cascade root cause tracing"] = weakness_counts.get("cascade root cause tracing", 0) + 1
        if "network" in sc_id.lower():
            weakness_counts["network partition handling"] = weakness_counts.get("network partition handling", 0) + 1
        if "time" in sc_id.lower():
            weakness_counts["clock skew detection"] = weakness_counts.get("clock skew detection", 0) + 1
    # Return top 3 weaknesses
    return sorted(weakness_counts, key=weakness_counts.get, reverse=True)[:3]


def _fault_to_yaml(fault: dict, scenario_id: str, index: int) -> str:
    kind    = fault.get("kind", "PodChaos")
    action  = fault.get("action", "pod-kill")
    service = fault.get("target_service", "frontend")
    params  = fault.get("params", {})
    name    = f"{scenario_id}-fault-{index}"

    base = f"""apiVersion: chaos-mesh.org/v1alpha1
kind: {kind}
metadata:
  name: {name}
  namespace: chaos-mesh
  labels:
    scenario: {scenario_id}
    tier: adversarial
    generated: "true"
spec:
  action: {action}
  mode: all
  selector:
    namespaces: [default]
    labelSelectors:
      app: {service}
"""
    # Append kind-specific params
    if kind == "NetworkChaos" and action == "delay":
        latency = params.get("latency", "1000ms")
        base += f"  delay:\n    latency: \"{latency}\"\n    correlation: \"80\"\n"
    elif kind == "NetworkChaos" and action == "loss":
        loss = params.get("loss", "30")
        base += f"  loss:\n    loss: \"{loss}\"\n    correlation: \"25\"\n"
    elif kind == "NetworkChaos" and action == "partition":
        base += f"  direction: both\n  target:\n    mode: all\n    selector:\n      namespaces: [default]\n"
    elif kind == "StressChaos":
        if "cpu" in action:
            workers = params.get("workers", 4)
            load    = params.get("load", 80)
            base += f"  stressors:\n    cpu:\n      workers: {workers}\n      load: {load}\n"
        else:
            size = params.get("size", "256MB")
            base += f"  stressors:\n    memory:\n      workers: 2\n      size: \"{size}\"\n"
    elif kind == "DNSChaos":
        base += f"  patterns:\n    - \"*.default.svc.cluster.local.\"\n"
    elif kind == "TimeChaos":
        offset = params.get("offset", "+300s")
        base += f"  timeOffset: \"{offset}\"\n"

    duration = params.get("duration", "15m")
    base += f"  duration: \"{duration}\"\n"
    return base


async def design_scenario(failure_history: list[dict]) -> dict[str, Any]:
    """Generate one unique adversarial scenario targeting the agent's weaknesses."""
    weaknesses = _extract_weaknesses(failure_history)

    prompt = f"""Agent failure history summary:
- Failed scenarios: {[e.get('scenario_id') for e in failure_history if not e.get('resolved')]}
- Top weaknesses identified: {weaknesses}
- Total episodes analysed: {len(failure_history)}

Available fault primitives: {AVAILABLE_PRIMITIVES}
Available target services: {SERVICES}

Design a NEW adversarial chaos scenario that specifically targets: {weaknesses[0] if weaknesses else 'general multi-fault handling'}

Make it {('extreme' if len(failure_history) > 20 else 'expert' if len(failure_history) > 10 else 'hard')} difficulty."""

    raw = await _call_judge(prompt)

    # Parse JSON from response
    try:
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        spec  = json.loads(raw[start:end])
    except (json.JSONDecodeError, ValueError):
        # Fallback: create a generic hard scenario
        spec = {
            "scenario_id": f"adv-fallback-{uuid.uuid4().hex[:6]}",
            "title": "Multi-fault cascade with red herring",
            "difficulty": "hard",
            "faults": [
                {"kind": "NetworkChaos", "action": "delay", "target_service": "currencyservice",
                 "params": {"latency": "2000ms", "duration": "15m"}},
                {"kind": "PodChaos", "action": "pod-kill", "target_service": "redis-cart",
                 "params": {}},
            ],
        }

    # Ensure unique scenario_id
    scenario_id = spec.get("scenario_id", f"adv-{uuid.uuid4().hex[:8]}")
    spec["scenario_id"] = scenario_id
    spec["generated_at"] = datetime.now(timezone.utc).isoformat()
    spec["weaknesses_targeted"] = weaknesses

    # Write Chaos Mesh YAML manifest
    faults   = spec.get("faults", [])
    yamls    = [_fault_to_yaml(f, scenario_id, i) for i, f in enumerate(faults)]
    manifest = "---\n".join(yamls)

    manifest_path = ADVERSARIAL_DIR / f"{scenario_id}.yaml"
    manifest_path.write_text(manifest, encoding="utf-8")

    # Write metadata sidecar
    meta_path = ADVERSARIAL_DIR / f"{scenario_id}.json"
    meta_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")

    return {
        "scenario_id": scenario_id,
        "manifest_path": str(manifest_path),
        "spec": spec,
    }


async def design_batch(failure_history: list[dict], count: int = 10) -> list[dict]:
    """Generate `count` unique adversarial scenarios in one session."""
    results = []
    for i in range(count):
        # Pass growing history so each scenario is harder than the last
        result = await design_scenario(failure_history)
        results.append(result)
        print(f"[{i+1}/{count}] Generated: {result['scenario_id']} "
              f"({result['spec'].get('difficulty', '?')}) → {result['manifest_path']}")
    return results
