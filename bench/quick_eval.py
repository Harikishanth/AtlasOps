"""Quick evaluation — runs the 3 demo scenarios and scores them.

Produces bench/results/quick_eval.json and prints a summary table.
Does NOT apply real Chaos Mesh — uses the pre-defined alert payloads
from inference.py (same as the HF demo).

Usage:
    python bench/quick_eval.py
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

_env = Path(__file__).parent.parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCENARIOS = {
    "hist-cloudflare-2019": {
        "commonLabels": {"alertname": "HighCPUSaturation", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "CPU saturation on frontend — Cloudflare 2019 replay"},
        "alerts": [{"status": "firing", "labels": {"alertname": "HighCPUSaturation", "pod": "frontend-xxx", "severity": "critical"}, "startsAt": "2026-05-09T10:00:00Z"}],
    },
    "hist-github-2018": {
        "commonLabels": {"alertname": "DatabaseFailoverLoop", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "Cloud SQL primary killed — replica promotion loop"},
        "alerts": [{"status": "firing", "labels": {"alertname": "DatabaseFailoverLoop", "severity": "critical"}, "startsAt": "2026-05-09T10:00:00Z"}],
    },
    "sf-001": {
        "commonLabels": {"alertname": "PodCrashLooping", "severity": "warning", "namespace": "default"},
        "commonAnnotations": {"summary": "cartservice pod killed by OOMKill"},
        "alerts": [{"status": "firing", "labels": {"alertname": "PodCrashLooping", "pod": "cartservice-xxx", "severity": "warning"}, "startsAt": "2026-05-09T10:00:00Z"}],
    },
}


def score_incident(incident: dict, elapsed_s: float, scenario_id: str) -> dict:
    """Compute reward metrics for a completed incident chain."""
    triage = incident.get("triage", {}).get("final", {})
    diagnosis = incident.get("diagnosis", {}).get("final", {})
    remediation = incident.get("remediation", {}).get("final", {})
    comms = incident.get("comms", {}).get("final", {})

    severity = triage.get("severity", "UNKNOWN")
    root_cause = diagnosis.get("root_cause") or diagnosis.get("specific")
    outcome = remediation.get("outcome", "unresolved")
    postmortem_path = comms.get("postmortem_path")

    # Score components (0–1 each)
    triage_score = 1.0 if severity in {"P0", "P1", "P2", "P3"} else 0.0
    diagnosis_score = 0.8 if root_cause and not isinstance(root_cause, dict) else (0.6 if root_cause else 0.0)
    remediation_score = {"resolved": 1.0, "partial": 0.7, "escalated": 0.5, "unresolved": 0.2}.get(outcome, 0.0)
    comms_score = 1.0 if (postmortem_path and Path(postmortem_path).exists()) else 0.5
    speed_score = max(0.0, 1.0 - (elapsed_s - 30) / 300) if elapsed_s < 300 else 0.0

    total = (
        triage_score * 0.15 +
        diagnosis_score * 0.30 +
        remediation_score * 0.35 +
        comms_score * 0.10 +
        speed_score * 0.10
    )

    triage_turns = len(incident.get("triage", {}).get("trajectory", []))
    diagnosis_turns = len(incident.get("diagnosis", {}).get("trajectory", []))
    remediation_turns = len(incident.get("remediation", {}).get("trajectory", []))

    return {
        "scenario_id": scenario_id,
        "elapsed_s": round(elapsed_s, 1),
        "severity": severity,
        "outcome": outcome,
        "root_cause_found": bool(root_cause),
        "postmortem_saved": bool(postmortem_path and Path(postmortem_path).exists()),
        "turns": triage_turns + diagnosis_turns + remediation_turns,
        "scores": {
            "triage": round(triage_score, 2),
            "diagnosis": round(diagnosis_score, 2),
            "remediation": round(remediation_score, 2),
            "comms": round(comms_score, 2),
            "speed": round(speed_score, 2),
        },
        "total": round(total, 3),
    }


async def run_scenario(scenario_id: str) -> dict:
    from agents.coordinator import handle_incident
    from agents.stream import get_history

    alert = SCENARIOS[scenario_id]
    alert["scenario_id"] = scenario_id

    print(f"\n[-->] {scenario_id}")
    t0 = time.time()
    incident = await handle_incident(alert)
    elapsed = time.time() - t0
    return score_incident(incident, elapsed, scenario_id)


async def main():
    results = []
    for sid in SCENARIOS:
        r = await run_scenario(sid)
        results.append(r)
        print(f"      {r['outcome']:12s} {r['elapsed_s']:6.1f}s  score={r['total']:.3f}")

    avg_score = sum(r["total"] for r in results) / len(results)
    avg_turns = sum(r["turns"] for r in results) / len(results)
    resolved = sum(1 for r in results if r["outcome"] in {"resolved", "partial"})
    postmortems = sum(1 for r in results if r["postmortem_saved"])

    summary = {
        "model": os.getenv("AGENT_MODEL", "Qwen/Qwen2.5-7B-Instruct"),
        "backend": os.getenv("BACKEND", "vllm"),
        "scenarios": len(results),
        "resolution_rate": resolved / len(results),
        "avg_reward": avg_score,
        "avg_turns": avg_turns,
        "postmortem_rate": postmortems / len(results),
        "results": results,
    }

    out = Path("bench/results/quick_eval.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"  QUICK EVAL SUMMARY ({len(results)} scenarios)")
    print(f"{'='*60}")
    print(f"  Resolution rate:    {resolved}/{len(results)} ({100*resolved//len(results)}%)")
    print(f"  Avg reward:         {avg_score:.3f}")
    print(f"  Avg turns:          {avg_turns:.1f}")
    print(f"  Postmortem rate:    {postmortems}/{len(results)}")
    print(f"  Results saved:      {out}")


if __name__ == "__main__":
    asyncio.run(main())
