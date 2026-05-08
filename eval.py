"""AtlasOps Evaluation — Base model vs Fine-tuned comparison.

Runs N episodes on the live GKE cluster and reports:
- Resolution rate per tier
- Average reward (judge score + contract score)
- MTTR distribution
- Per-incident postmortem quality

Usage:
    # Compare base vs fine-tuned
    python eval.py --base Qwen/Qwen2.5-7B-Instruct --ft checkpoints/grpo_v3 --episodes 20

    # Eval a single model
    python eval.py --model checkpoints/grpo_v3 --episodes 30 --tiers cascade,named_replays

    # Quick smoke test (5 episodes)
    python eval.py --model Qwen/Qwen2.5-7B-Instruct --episodes 5 --quick
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from config.runtime import EVAL_SCENARIOS_BY_TIER

log = logging.getLogger(__name__)

RESULTS_DIR = Path("bench/results/eval")
MANIFESTS_DIR = Path("bench/chaos_manifests")

def apply_chaos(scenario_id: str) -> bool:
    manifest = MANIFESTS_DIR / f"{scenario_id}.yaml"
    if not manifest.exists():
        return False
    env = os.environ.copy()
    env["USE_GKE_GCLOUD_AUTH_PLUGIN"] = "True"
    r = subprocess.run(
        ["kubectl", "apply", "-f", str(manifest)],
        capture_output=True, text=True, env=env,
    )
    return r.returncode == 0


def reset_chaos():
    env = os.environ.copy()
    env["USE_GKE_GCLOUD_AUTH_PLUGIN"] = "True"
    subprocess.run(
        ["kubectl", "delete",
         "podchaos,networkchaos,stresschaos,dnschaos,iochaos,timechaos",
         "--all", "-A", "--ignore-not-found=true"],
        capture_output=True, env=env,
    )
    time.sleep(30)


def wait_for_alert(timeout_s: int = 180) -> dict | None:
    from agents.tools.alertmanager import alertmanager_list_alerts
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        result = alertmanager_list_alerts(active_only=True)
        if result.get("success") and result.get("count", 0) > 0:
            return {"commonLabels": {"alertname": result["alerts"][0]["alertname"]},
                    "alerts": result["alerts"]}
        time.sleep(10)
    return {"commonLabels": {"alertname": "EvalTimeout"}, "alerts": [], "synthetic": True}


async def run_episode(scenario_id: str) -> dict:
    from agents.coordinator import handle_incident
    from agents.judge import judge_trajectory

    t0 = time.time()
    tier = scenario_id.split("/")[0]

    if not apply_chaos(scenario_id):
        return {"scenario_id": scenario_id, "status": "skip", "tier": tier}

    alert = wait_for_alert()
    alert["scenario_id"] = scenario_id

    try:
        incident = await handle_incident(alert)
        judge_score = await judge_trajectory(incident)
    except Exception as e:
        reset_chaos()
        return {"scenario_id": scenario_id, "status": "error", "error": str(e), "tier": tier}

    reset_chaos()

    remediation = incident.get("remediation", {}).get("final", {})
    total_turns = sum(
        len(incident.get(r, {}).get("trajectory", []))
        for r in ("triage", "diagnosis", "remediation", "comms")
    )

    return {
        "scenario_id": scenario_id,
        "tier": tier,
        "status": "ok",
        "resolved": remediation.get("outcome") == "resolved",
        "outcome": remediation.get("outcome", "unknown"),
        "time_to_resolve_s": remediation.get("time_to_resolve_seconds", round(time.time() - t0)),
        "total_turns": total_turns,
        "judge": judge_score,
        "postmortem_path": incident.get("comms", {}).get("final", {}).get("postmortem_path"),
    }


def reset_cluster():
    reset_chaos()


def compute_stats(results: list[dict], tag: str) -> dict:
    valid = [r for r in results if r.get("status") == "ok"]
    resolved = [r for r in valid if r.get("resolved")]

    judge_scores = [r["judge"].get("overall", 0) for r in valid if r.get("judge")]
    ttr_values = [r["time_to_resolve_s"] for r in valid if r.get("time_to_resolve_s")]

    per_tier: dict = {}
    for tier in ("single_fault", "cascade", "named_replays"):
        tier_eps = [r for r in valid if r.get("tier") == tier]
        tier_res = [r for r in tier_eps if r.get("resolved")]
        per_tier[tier] = {
            "total": len(tier_eps),
            "resolved": len(tier_res),
            "resolution_rate": round(len(tier_res) / max(len(tier_eps), 1), 3),
        }

    return {
        "tag": tag,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_episodes": len(results),
        "valid_episodes": len(valid),
        "resolution_rate": round(len(resolved) / max(len(valid), 1), 3),
        "avg_judge_score": round(sum(judge_scores) / max(len(judge_scores), 1), 3),
        "avg_ttr_seconds": round(sum(ttr_values) / max(len(ttr_values), 1), 1),
        "min_ttr_seconds": min(ttr_values) if ttr_values else None,
        "max_ttr_seconds": max(ttr_values) if ttr_values else None,
        "per_tier": per_tier,
    }


def print_comparison(base_stats: dict, ft_stats: dict):
    print("\n" + "=" * 70)
    print("  ATLASOPS EVALUATION — BASE vs FINE-TUNED")
    print("=" * 70)
    print(f"\n{'Metric':<30} {'Base':>12} {'Fine-tuned':>12} {'Delta':>10}")
    print("-" * 66)

    metrics = [
        ("Resolution Rate", "resolution_rate", "{:.1%}"),
        ("Avg Judge Score", "avg_judge_score", "{:.3f}"),
        ("Avg TTR (seconds)", "avg_ttr_seconds", "{:.0f}s"),
    ]
    for label, key, fmt in metrics:
        b = base_stats.get(key, 0)
        f = ft_stats.get(key, 0)
        delta = f - b if isinstance(b, (int, float)) else 0
        sign = "+" if delta > 0 else ""
        print(f"  {label:<28} {fmt.format(b):>12} {fmt.format(f):>12} {sign}{fmt.format(delta):>9}")

    print("\n  Per-Tier Resolution Rate:")
    for tier in ("single_fault", "cascade", "named_replays"):
        b = base_stats.get("per_tier", {}).get(tier, {}).get("resolution_rate", 0)
        f = ft_stats.get("per_tier", {}).get(tier, {}).get("resolution_rate", 0)
        delta = f - b
        sign = "+" if delta > 0 else ""
        print(f"    {tier:<26} {b:>10.1%} {f:>10.1%} {sign}{delta:>8.1%}")
    print("=" * 70 + "\n")


async def eval_model(model_id: str, tag: str, scenarios: list[str],
                     episodes: int) -> dict:
    os.environ["AGENT_MODEL"] = model_id
    log.info("Evaluating %s (%d episodes)...", tag, episodes)

    results = []
    for i, scenario in enumerate(scenarios[:episodes], 1):
        log.info("[%d/%d] %s", i, episodes, scenario)
        result = await run_episode(scenario)
        results.append(result)

    return compute_stats(results, tag)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base",     default="", help="Base model path/ID")
    parser.add_argument("--ft",       default="", help="Fine-tuned checkpoint path")
    parser.add_argument("--model",    default="", help="Single model eval (sets both)")
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--tiers",    default="single_fault,cascade,named_replays")
    parser.add_argument("--quick",    action="store_true", help="5-episode smoke test")
    args = parser.parse_args()

    if args.quick:
        args.episodes = 5

    tiers = [t.strip() for t in args.tiers.split(",")]
    scenarios = []
    for tier in tiers:
        scenarios.extend(EVAL_SCENARIOS_BY_TIER.get(tier, []))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.model:
        stats = await eval_model(args.model, "model", scenarios, args.episodes)
        print(json.dumps(stats, indent=2))
        (RESULTS_DIR / f"eval_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
         ).write_text(json.dumps(stats, indent=2))
        return

    if not args.base or not args.ft:
        parser.error("Provide --base and --ft for comparison, or --model for single eval")

    base_stats = await eval_model(args.base, "base", scenarios, args.episodes)
    ft_stats   = await eval_model(args.ft,   "fine_tuned", scenarios, args.episodes)

    print_comparison(base_stats, ft_stats)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    (RESULTS_DIR / f"comparison_{ts}.json").write_text(
        json.dumps({"base": base_stats, "fine_tuned": ft_stats}, indent=2)
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    asyncio.run(main())
