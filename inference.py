"""AtlasOps inference baseline.

Runs a single incident response chain directly (no separate server needed).
Loads .env automatically.

Usage:
    python inference.py
    python inference.py --scenario hist-github-2018
"""

import asyncio
import json
import os
import sys
import time
import argparse
from pathlib import Path

# ── Load .env ────────────────────────────────────────────────────────────────
_env = Path(__file__).parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

# ── Sample alerts per scenario ───────────────────────────────────────────────
ALERTS = {
    "hist-cloudflare-2019": {
        "commonLabels": {
            "alertname": "HighCPUSaturation",
            "severity": "critical",
            "namespace": "default",
        },
        "commonAnnotations": {
            "summary": "CPU saturation on frontend — Cloudflare 2019 replay",
        },
        "alerts": [{
            "status": "firing",
            "labels": {"alertname": "HighCPUSaturation", "pod": "frontend-xxx", "severity": "critical"},
            "annotations": {"summary": "frontend CPU at 100%"},
            "startsAt": "2026-05-09T14:23:31Z",
        }],
    },
    "hist-github-2018": {
        "commonLabels": {"alertname": "DatabaseFailoverLoop", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "Cloud SQL primary killed — replica promotion loop"},
        "alerts": [{"status": "firing", "labels": {"alertname": "DatabaseFailoverLoop", "severity": "critical"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
    "sf-001": {
        "commonLabels": {"alertname": "PodCrashLooping", "severity": "warning", "namespace": "default"},
        "commonAnnotations": {"summary": "cartservice pod killed by OOMKill"},
        "alerts": [{"status": "firing", "labels": {"alertname": "PodCrashLooping", "pod": "cartservice-xxx", "severity": "warning"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
}


def print_banner(scenario: str):
    backend = os.getenv("BACKEND", "vllm")
    model   = os.getenv("AGENT_MODEL", "Qwen/Qwen2.5-7B-Instruct")
    print("\n" + "=" * 70)
    print("  AtlasOps — Multi-Agent SRE Incident Response")
    print(f"  Backend:  {backend}")
    print(f"  Model:    {model}")
    print(f"  Scenario: {scenario}")
    print("=" * 70 + "\n")


def print_agent_trace(thoughts: list):
    ICONS = {"triage": "🔴", "diagnosis": "🔍", "remediation": "🔧", "comms": "📣"}
    PHASE = {"tool_call": "→", "tool_result": "✓", "conclusion": "★", "thinking": "💭", "waiting_approval": "⏳"}
    print("─" * 70)
    print("  AGENT TRACE")
    print("─" * 70)
    for t in thoughts:
        icon  = ICONS.get(t.get("role", ""), "•")
        phase = PHASE.get(t.get("phase", ""), "•")
        role  = t.get("role", "?").upper()
        text  = t.get("thought", "")
        tool  = f"  [{t['tool']}]" if t.get("tool") else ""
        print(f"  {icon} {role:12s} {phase}  {text[:80]}{tool}")
    print("─" * 70 + "\n")


async def run(scenario: str):
    from agents.coordinator import handle_incident
    from agents.stream import get_history

    alert = ALERTS.get(scenario, ALERTS["hist-cloudflare-2019"])
    alert["scenario_id"] = scenario

    print(f"[→] Firing alert: {alert['commonLabels']['alertname']}")
    t0 = time.time()

    incident = await handle_incident(alert)

    elapsed = round(time.time() - t0, 1)
    print(f"[✓] Chain complete in {elapsed}s\n")

    thoughts = get_history()
    if thoughts:
        print_agent_trace(thoughts)

    # Summary per role
    for role in ("triage", "diagnosis", "remediation", "comms"):
        final = incident.get(role, {}).get("final", {})
        turns = len(incident.get(role, {}).get("trajectory", []))
        print(f"  {role.upper():12s}  {turns} turns  →  {json.dumps(final)[:120]}")

    postmortem = incident.get("comms", {}).get("final", {}).get("postmortem_path")
    if postmortem and Path(postmortem).exists():
        print(f"\n[★] Postmortem saved: {postmortem}")

    print(f"\n[END] Resolved: {incident.get('remediation', {}).get('final', {}).get('outcome', 'unknown')}")
    return incident


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="hist-cloudflare-2019",
                        choices=list(ALERTS.keys()),
                        help="Which scenario alert to fire")
    args = parser.parse_args()

    print_banner(args.scenario)
    asyncio.run(run(args.scenario))


if __name__ == "__main__":
    main()
