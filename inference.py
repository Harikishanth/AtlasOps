"""AtlasOps inference baseline.

Runs a single incident response chain directly (no separate server needed).
Loads .env automatically.

Usage:
    python inference.py
    python inference.py --scenario hist-github-2018
    python inference.py --scenario all        # run every scenario sequentially
    python inference.py --list                # show available scenarios
"""

import asyncio
import json
import os
import sys
import time
import argparse
from pathlib import Path

# Force UTF-8 stdout/stderr on Windows so LLM Unicode responses don't crash print()
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Load .env ────────────────────────────────────────────────────────────────
_env = Path(__file__).parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

# ── Scenario catalogue ───────────────────────────────────────────────────────
ALERTS = {
    # ── Warmup (trivial — verify agent chain works) ───────────────────────────
    "warmup-001": {
        "commonLabels": {"alertname": "HighErrorRate", "severity": "warning", "namespace": "default"},
        "commonAnnotations": {"summary": "frontend HTTP 5xx rate above 1% — low severity warmup"},
        "alerts": [{"status": "firing", "labels": {"alertname": "HighErrorRate", "service": "frontend", "severity": "warning"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
    "warmup-002": {
        "commonLabels": {"alertname": "PodNotReady", "severity": "warning", "namespace": "default"},
        "commonAnnotations": {"summary": "adservice pod not ready — single pod, low impact"},
        "alerts": [{"status": "firing", "labels": {"alertname": "PodNotReady", "pod": "adservice-xxx", "severity": "warning"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
    "warmup-003": {
        "commonLabels": {"alertname": "HighLatencyP99", "severity": "warning", "namespace": "default"},
        "commonAnnotations": {"summary": "recommendationservice p99 latency > 500ms — intermittent"},
        "alerts": [{"status": "firing", "labels": {"alertname": "HighLatencyP99", "service": "recommendationservice", "severity": "warning"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
    # ── Named historical replays ─────────────────────────────────────────────
    "hist-cloudflare-2019": {
        "commonLabels": {"alertname": "HighCPUSaturation", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "CPU saturation on frontend — Cloudflare 2019 replay"},
        "alerts": [{"status": "firing", "labels": {"alertname": "HighCPUSaturation", "pod": "frontend-xxx", "severity": "critical"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
    "hist-github-2018": {
        "commonLabels": {"alertname": "DatabaseFailoverLoop", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "Cloud SQL primary killed — replica promotion loop (GitHub 2018)"},
        "alerts": [{"status": "firing", "labels": {"alertname": "DatabaseFailoverLoop", "severity": "critical"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
    "hist-discord-2022": {
        "commonLabels": {"alertname": "CacheThunderingHerd", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "Redis cache killed — cartservice hammering Cloud SQL (Discord 2022)"},
        "alerts": [{"status": "firing", "labels": {"alertname": "CacheThunderingHerd", "service": "cartservice", "severity": "critical"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
    "hist-datadog-2023": {
        "commonLabels": {"alertname": "DNSResolutionFailure", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "systemd-resolved failure — DNS lookups timing out cluster-wide (Datadog 2023)"},
        "alerts": [{"status": "firing", "labels": {"alertname": "DNSResolutionFailure", "severity": "critical"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
    "hist-slack-2022": {
        "commonLabels": {"alertname": "HTTP2StreamExhaustion", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "HTTP/2 client misconfig causing stream exhaustion — checkout degraded (Slack 2022)"},
        "alerts": [{"status": "firing", "labels": {"alertname": "HTTP2StreamExhaustion", "service": "checkoutservice", "severity": "critical"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
    "hist-aws-s3-2017": {
        "commonLabels": {"alertname": "DeploymentReplicasDown", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "Argo CD bad sync removed deployment replicas — AWS S3 2017 replay (typo'd capacity)"},
        "alerts": [{"status": "firing", "labels": {"alertname": "DeploymentReplicasDown", "severity": "critical"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
    "hist-azure-dns-2019": {
        "commonLabels": {"alertname": "StaleDNSCache", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "CoreDNS misconfig + stale cache — service discovery broken cluster-wide (Azure DNS 2019)"},
        "alerts": [{"status": "firing", "labels": {"alertname": "StaleDNSCache", "severity": "critical"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
    "hist-fastly-2021": {
        "commonLabels": {"alertname": "EnvoyFilterCorruption", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "Bad Envoy filter via Linkerd — all frontend traffic corrupted (Fastly 2021 VCL bug replay)"},
        "alerts": [{"status": "firing", "labels": {"alertname": "EnvoyFilterCorruption", "service": "frontend", "severity": "critical"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
    "hist-facebook-bgp-2021": {
        "commonLabels": {"alertname": "NetworkPartitionControlPlane", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "NetworkChaos partition between service mesh and control plane — BGP withdraw replay (Facebook 2021)"},
        "alerts": [{"status": "firing", "labels": {"alertname": "NetworkPartitionControlPlane", "severity": "critical"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
    "hist-knight-capital-2012": {
        "commonLabels": {"alertname": "PartialDeploymentMismatch", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "Argo CD partial sync — old + new checkout code running simultaneously (Knight Capital 2012 replay)"},
        "alerts": [{"status": "firing", "labels": {"alertname": "PartialDeploymentMismatch", "service": "checkoutservice", "severity": "critical"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
    # ── Single-fault scenarios ────────────────────────────────────────────────
    "sf-001": {
        "commonLabels": {"alertname": "PodCrashLooping", "severity": "warning", "namespace": "default"},
        "commonAnnotations": {"summary": "cartservice pod killed by OOMKill — crash looping"},
        "alerts": [{"status": "firing", "labels": {"alertname": "PodCrashLooping", "pod": "cartservice-xxx", "severity": "warning"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
    "sf-002": {
        "commonLabels": {"alertname": "HighCPUThrottle", "severity": "warning", "namespace": "default"},
        "commonAnnotations": {"summary": "paymentservice CPU throttled at 95% — runaway transaction loop"},
        "alerts": [{"status": "firing", "labels": {"alertname": "HighCPUThrottle", "service": "paymentservice", "severity": "warning"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
    "sf-003": {
        "commonLabels": {"alertname": "MemoryPressure", "severity": "warning", "namespace": "default"},
        "commonAnnotations": {"summary": "checkoutservice memory usage at 90% — potential OOM imminent"},
        "alerts": [{"status": "firing", "labels": {"alertname": "MemoryPressure", "service": "checkoutservice", "severity": "warning"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
    "sf-004": {
        "commonLabels": {"alertname": "NetworkPacketLoss", "severity": "warning", "namespace": "default"},
        "commonAnnotations": {"summary": "50% packet loss on frontend — flaky network interface"},
        "alerts": [{"status": "firing", "labels": {"alertname": "NetworkPacketLoss", "service": "frontend", "severity": "warning"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
    "sf-005": {
        "commonLabels": {"alertname": "RedisCartPartition", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "NetworkChaos partition between Redis and cartservice — cart reads/writes failing"},
        "alerts": [{"status": "firing", "labels": {"alertname": "RedisCartPartition", "service": "redis-cart", "severity": "critical"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
    "sf-006": {
        "commonLabels": {"alertname": "DNSRandomFailure", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "DNSChaos random failures on auth service path — CoreDNS degraded"},
        "alerts": [{"status": "firing", "labels": {"alertname": "DNSRandomFailure", "severity": "critical"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
    "sf-007": {
        "commonLabels": {"alertname": "DiskPressure", "severity": "warning", "namespace": "default"},
        "commonAnnotations": {"summary": "IOChaos filling /var/log on emailservice — disk at 95%, notification backlog building"},
        "alerts": [{"status": "firing", "labels": {"alertname": "DiskPressure", "service": "emailservice", "severity": "warning"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
    "sf-008": {
        "commonLabels": {"alertname": "ClockSkew", "severity": "warning", "namespace": "default"},
        "commonAnnotations": {"summary": "TimeChaos on paymentservice — JWT clock skew causing token validation failures"},
        "alerts": [{"status": "firing", "labels": {"alertname": "ClockSkew", "service": "paymentservice", "severity": "warning"}, "startsAt": "2026-05-09T14:23:31Z"}],
    },
    # ── Cascade scenarios ─────────────────────────────────────────────────────
    "cs-001": {
        "commonLabels": {"alertname": "CascadeLatencySpike", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "currencyservice latency spike → checkout timeout → cart retry storm → frontend 5xx surge"},
        "alerts": [
            {"status": "firing", "labels": {"alertname": "CascadeLatencySpike", "service": "currencyservice", "severity": "critical"}, "startsAt": "2026-05-09T14:23:31Z"},
            {"status": "firing", "labels": {"alertname": "CheckoutTimeout", "service": "checkoutservice", "severity": "critical"}, "startsAt": "2026-05-09T14:24:00Z"},
            {"status": "firing", "labels": {"alertname": "HighErrorRate", "service": "frontend", "severity": "warning"}, "startsAt": "2026-05-09T14:24:30Z"},
        ],
    },
    "cs-002": {
        "commonLabels": {"alertname": "RedisPartition", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "Redis partition → cart errors → checkout failures → revenue alarm firing"},
        "alerts": [
            {"status": "firing", "labels": {"alertname": "RedisPartition", "service": "redis-cart", "severity": "critical"}, "startsAt": "2026-05-09T14:23:31Z"},
            {"status": "firing", "labels": {"alertname": "CartServiceErrors", "service": "cartservice", "severity": "critical"}, "startsAt": "2026-05-09T14:24:00Z"},
        ],
    },
    "cs-003": {
        "commonLabels": {"alertname": "RecommendationCPUHog", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "recommendationservice CPU hog → frontend latency spike → user-facing P1"},
        "alerts": [
            {"status": "firing", "labels": {"alertname": "HighCPUThrottle", "service": "recommendationservice", "severity": "critical"}, "startsAt": "2026-05-09T14:23:31Z"},
            {"status": "firing", "labels": {"alertname": "FrontendLatencySpike", "service": "frontend", "severity": "warning"}, "startsAt": "2026-05-09T14:24:00Z"},
        ],
    },
    "cs-004": {
        "commonLabels": {"alertname": "EmailDiskFullCascade", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "emailservice disk full → notification backlog → checkout confirmation timeout cascade"},
        "alerts": [
            {"status": "firing", "labels": {"alertname": "DiskPressure", "service": "emailservice", "severity": "warning"}, "startsAt": "2026-05-09T14:23:31Z"},
            {"status": "firing", "labels": {"alertname": "CheckoutTimeout", "service": "checkoutservice", "severity": "critical"}, "startsAt": "2026-05-09T14:25:00Z"},
        ],
    },
    "cs-005": {
        "commonLabels": {"alertname": "CloudSQLConnectionExhaustion", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "Cloud SQL connection pool exhausted → cartservice 500s → checkout cascade failure"},
        "alerts": [
            {"status": "firing", "labels": {"alertname": "CloudSQLConnectionExhaustion", "service": "cartservice", "severity": "critical"}, "startsAt": "2026-05-09T14:23:31Z"},
            {"status": "firing", "labels": {"alertname": "CheckoutServiceErrors", "service": "checkoutservice", "severity": "critical"}, "startsAt": "2026-05-09T14:24:30Z"},
        ],
    },
    # ── Multi-fault scenarios ─────────────────────────────────────────────────
    "mf-001": {
        "commonLabels": {"alertname": "MultiServiceDegradation", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "3 simultaneous faults: OOMKill on adservice + DNS chaos + network packet loss on frontend"},
        "alerts": [
            {"status": "firing", "labels": {"alertname": "PodCrashLooping", "service": "adservice", "severity": "warning"}, "startsAt": "2026-05-09T14:23:31Z"},
            {"status": "firing", "labels": {"alertname": "DNSResolutionFailure", "severity": "critical"}, "startsAt": "2026-05-09T14:23:45Z"},
            {"status": "firing", "labels": {"alertname": "NetworkPacketLoss", "service": "frontend", "severity": "warning"}, "startsAt": "2026-05-09T14:24:00Z"},
        ],
    },
    "mf-002": {
        "commonLabels": {"alertname": "RedisAndMemoryFault", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "Redis partition + recommendationservice memory pressure simultaneously — compound degradation"},
        "alerts": [
            {"status": "firing", "labels": {"alertname": "RedisCartPartition", "service": "redis-cart", "severity": "critical"}, "startsAt": "2026-05-09T14:23:31Z"},
            {"status": "firing", "labels": {"alertname": "MemoryPressure", "service": "recommendationservice", "severity": "warning"}, "startsAt": "2026-05-09T14:23:50Z"},
        ],
    },
    "mf-003": {
        "commonLabels": {"alertname": "DNSAndNetworkFault", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "DNS random failures + currencyservice network delay — auth + checkout both broken"},
        "alerts": [
            {"status": "firing", "labels": {"alertname": "DNSRandomFailure", "severity": "critical"}, "startsAt": "2026-05-09T14:23:31Z"},
            {"status": "firing", "labels": {"alertname": "CascadeLatencySpike", "service": "currencyservice", "severity": "warning"}, "startsAt": "2026-05-09T14:24:00Z"},
        ],
    },
    "mf-004": {
        "commonLabels": {"alertname": "ClockSkewAndCorruption", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "TimeChaos clock skew on paymentservice + cartservice network corruption — JWT + cart both failing"},
        "alerts": [
            {"status": "firing", "labels": {"alertname": "ClockSkew", "service": "paymentservice", "severity": "warning"}, "startsAt": "2026-05-09T14:23:31Z"},
            {"status": "firing", "labels": {"alertname": "NetworkPacketCorruption", "service": "cartservice", "severity": "critical"}, "startsAt": "2026-05-09T14:23:45Z"},
        ],
    },
    "mf-005": {
        "commonLabels": {"alertname": "IOAndNetworkFault", "severity": "critical", "namespace": "default"},
        "commonAnnotations": {"summary": "emailservice IO fault + checkoutservice network delay — notification + checkout both degraded"},
        "alerts": [
            {"status": "firing", "labels": {"alertname": "DiskPressure", "service": "emailservice", "severity": "warning"}, "startsAt": "2026-05-09T14:23:31Z"},
            {"status": "firing", "labels": {"alertname": "CheckoutTimeout", "service": "checkoutservice", "severity": "warning"}, "startsAt": "2026-05-09T14:24:00Z"},
        ],
    },
}

SCENARIO_GROUPS = {
    "warmup":  [k for k in ALERTS if k.startswith("warmup-")],
    "hist":    [k for k in ALERTS if k.startswith("hist-")],
    "sf":      [k for k in ALERTS if k.startswith("sf-")],
    "cascade": [k for k in ALERTS if k.startswith("cs-")],
    "multi":   [k for k in ALERTS if k.startswith("mf-")],
    "all":     list(ALERTS.keys()),
}


def print_banner(scenario: str):
    backend = os.getenv("BACKEND", "vllm")
    model   = os.getenv("AGENT_MODEL", "Qwen/Qwen2.5-7B-Instruct")
    print("\n" + "═" * 70)
    print("  AtlasOps — Multi-Agent SRE Incident Response")
    print(f"  Backend:  {backend}")
    print(f"  Model:    {model}")
    print(f"  Scenario: {scenario}")
    print("═" * 70 + "\n")


def print_agent_trace(thoughts: list):
    ICONS  = {"triage": "🔴", "diagnosis": "🔍", "remediation": "🔧", "comms": "📣"}
    PHASE  = {"tool_call": "→", "tool_result": "✓", "conclusion": "★", "thinking": "💭", "waiting_approval": "⏳"}
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


def print_final(role: str, final: dict, turns: int):
    """Pretty-print the full final output for a role."""
    outcome_symbol = {
        "triage": "🔴", "diagnosis": "🔍", "remediation": "🔧", "comms": "📣"
    }.get(role, "•")
    print(f"\n  {outcome_symbol} {role.upper():12s}  ({turns} turns)")
    print("  " + "·" * 60)
    formatted = json.dumps(final, indent=4, ensure_ascii=False)
    for line in formatted.splitlines():
        print(f"    {line}")


async def run(scenario: str) -> dict:
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

    # Full pretty-printed output per agent
    print("═" * 70)
    print("  AGENT OUTPUTS")
    print("═" * 70)
    for role in ("triage", "diagnosis", "remediation", "comms"):
        final = incident.get(role, {}).get("final", {})
        turns = len(incident.get(role, {}).get("trajectory", []))
        print_final(role, final, turns)

    postmortem = incident.get("comms", {}).get("final", {}).get("postmortem_path")
    if postmortem and Path(postmortem).exists():
        print(f"\n[★] Postmortem saved: {postmortem}")

    outcome = incident.get("remediation", {}).get("final", {}).get("outcome", "unknown")
    outcome_icon = {"resolved": "✅", "partial": "⚠️", "escalated": "📞", "unresolved": "❌"}.get(outcome, "❓")
    print(f"\n{outcome_icon} [END] Resolved: {outcome}\n")
    return incident


async def run_all(scenarios: list[str]):
    results = []
    for i, sid in enumerate(scenarios, 1):
        print(f"\n{'━' * 70}")
        print(f"  [{i}/{len(scenarios)}] SCENARIO: {sid}")
        print(f"{'━' * 70}")
        print_banner(sid)
        incident = await run(sid)
        outcome = incident.get("remediation", {}).get("final", {}).get("outcome", "unknown")
        results.append({"scenario": sid, "outcome": outcome})

    # Summary table
    print(f"\n{'═' * 70}")
    print("  RUN SUMMARY")
    print(f"{'═' * 70}")
    for r in results:
        icon = {"resolved": "✅", "partial": "⚠️", "escalated": "📞", "unresolved": "❌"}.get(r["outcome"], "❓")
        print(f"  {icon} {r['scenario']:30s} → {r['outcome']}")
    resolved = sum(1 for r in results if r["outcome"] in {"resolved", "partial"})
    print(f"\n  Resolution: {resolved}/{len(results)} ({100*resolved//len(results)}%)")


def main():
    parser = argparse.ArgumentParser(description="AtlasOps incident response runner")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--scenario", default="hist-cloudflare-2019",
                       help=f"Scenario ID or group name. Groups: {list(SCENARIO_GROUPS.keys())}. "
                            f"Individual: {list(ALERTS.keys())}")
    group.add_argument("--list", action="store_true", help="List all available scenarios and exit")
    args = parser.parse_args()

    if args.list:
        print("\nAvailable scenarios:")
        for group, ids in SCENARIO_GROUPS.items():
            if group == "all":
                continue
            print(f"\n  [{group}]")
            for sid in ids:
                summary = ALERTS[sid]["commonAnnotations"]["summary"][:60]
                print(f"    {sid:35s}  {summary}")
        print(f"\n  Use --scenario all  to run all {len(ALERTS)} scenarios")
        return

    scenario_arg = args.scenario
    if scenario_arg in SCENARIO_GROUPS:
        scenarios = SCENARIO_GROUPS[scenario_arg]
        asyncio.run(run_all(scenarios))
    elif scenario_arg in ALERTS:
        print_banner(scenario_arg)
        asyncio.run(run(scenario_arg))
    else:
        print(f"Unknown scenario: {scenario_arg}")
        print(f"Available: {list(ALERTS.keys()) + list(SCENARIO_GROUPS.keys())}")
        sys.exit(1)


if __name__ == "__main__":
    main()
