"""AtlasOps inference baseline.

Runs a single incident response chain against the coordinator
and prints the full agent trace.

Usage:
    # Against running coordinator
    python inference.py

    # Against HF Space
    COORDINATOR_URL=https://your-space.hf.space python inference.py

    # With Fireworks AI backend
    BACKEND=fireworks LLM_API_KEY=fw_xxxx python inference.py
"""

import json
import os
import sys
import time

import httpx


COORDINATOR_URL = os.getenv("COORDINATOR_URL", "http://localhost:9099")
SCENARIO = os.getenv("SCENARIO", "hist-cloudflare-2019")

# Simulated Alertmanager webhook payload for Cloudflare 2019 replay
SAMPLE_ALERT = {
    "version": "4",
    "groupKey": "{}:{alertname='HighCPUSaturation'}",
    "status": "firing",
    "receiver": "atlasops-coordinator",
    "commonLabels": {
        "alertname": "HighCPUSaturation",
        "severity": "critical",
        "namespace": "default",
        "scenario": SCENARIO,
    },
    "commonAnnotations": {
        "summary": "CPU saturation on frontend — 100% load across all replicas",
        "description": "StressChaos injected simulating Cloudflare 2019 regex backtracking incident",
    },
    "alerts": [
        {
            "status": "firing",
            "labels": {
                "alertname": "HighCPUSaturation",
                "container": "server",
                "namespace": "default",
                "pod": "frontend-7d8b9c4f6-x2kp9",
                "severity": "critical",
            },
            "annotations": {
                "summary": "frontend CPU at 100%",
                "runbook": "https://github.com/Harikishanth/AtlasOps/blob/main/docs/postmortems/2026-05-09-cloudflare-2019-replay.md",
            },
            "startsAt": "2026-05-09T14:23:31Z",
        }
    ],
}


def print_banner():
    print("\n" + "=" * 70)
    print("  AtlasOps — Multi-Agent SRE Incident Response")
    print(f"  Coordinator: {COORDINATOR_URL}")
    print(f"  Scenario:    {SCENARIO}")
    print("=" * 70 + "\n")


def check_health() -> bool:
    try:
        r = httpx.get(f"{COORDINATOR_URL}/health", timeout=5)
        data = r.json()
        print(f"[START] Coordinator healthy — model: {data.get('model', 'unknown')}")
        return True
    except Exception as e:
        print(f"[ERROR] Coordinator not reachable: {e}")
        print(f"        Start it with: python agents/coordinator.py")
        return False


def run_inference() -> dict:
    print(f"[STEP] Firing alert: {SAMPLE_ALERT['commonLabels']['alertname']}")
    t0 = time.time()

    with httpx.Client(timeout=300) as client:
        r = client.post(f"{COORDINATOR_URL}/webhook", json=SAMPLE_ALERT)
        r.raise_for_status()
        result = r.json()

    elapsed = round(time.time() - t0, 1)
    print(f"[STEP] Webhook accepted — incident_id: {result.get('incident_id')}")
    print(f"[STEP] Elapsed: {elapsed}s\n")
    return result


def fetch_thoughts() -> list:
    try:
        r = httpx.get(f"{COORDINATOR_URL}/thoughts", timeout=5)
        return r.json().get("thoughts", [])
    except Exception:
        return []


def print_agent_trace(thoughts: list):
    ICONS = {"triage": "🔴", "diagnosis": "🔍", "remediation": "🔧", "comms": "📣"}
    PHASE = {"tool_call": "→", "tool_result": "✓", "conclusion": "★"}
    print("─" * 70)
    print("  AGENT TRACE")
    print("─" * 70)
    for t in thoughts:
        icon = ICONS.get(t["role"], "•")
        phase = PHASE.get(t["phase"], "•")
        print(f"  {icon} {t['role'].upper():12s} {phase}  {t['thought']}")
    print("─" * 70 + "\n")


def main():
    print_banner()

    if not check_health():
        sys.exit(1)

    try:
        result = run_inference()
    except httpx.HTTPError as e:
        print(f"[ERROR] HTTP error: {e}")
        sys.exit(1)

    thoughts = fetch_thoughts()
    if thoughts:
        print_agent_trace(thoughts)

    # Print summary
    print("[END] Incident response summary:")
    print(json.dumps(result, indent=2))

    return result


if __name__ == "__main__":
    main()
