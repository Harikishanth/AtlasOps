"""AtlasOps Benchmark Runner.

Runs all 28 frozen scenarios (8 single-fault + 5 cascade + 5 multi-fault + 10 named replays)
against a model, scores them with the LLM judge, and outputs a comparison table.

Usage:
  python bench/runner.py --model checkpoints/grpo_v3 --tag grpo_v3
  python bench/runner.py --model checkpoints/AtlasOps_v2_baseline --tag baseline_v2

Output:
  bench/results/<run_id>/results_per_episode.jsonl
  bench/results/<run_id>/results_summary.json
  bench/results/comparison_table.md  (updates in place across runs)
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

from agents.adversarial_designer import design_batch
from agents.coordinator import handle_incident
from agents.judge import judge_trajectory
from config.runtime import (
    FROZEN_SCENARIOS,
    evaluate_reward_contract,
    bounded_speed_score as _bounded_speed_score,
)

# Backwards-compatible alias — tests import this name from bench.runner
_evaluate_episode_reward = evaluate_reward_contract


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("runner")

RESULTS_DIR = Path("bench/results")
MANIFESTS_DIR = Path("bench/chaos_manifests")


def apply_chaos(scenario_id: str) -> bool:
    manifest = MANIFESTS_DIR / f"{scenario_id}.yaml"
    if not manifest.exists():
        log.error("manifest not found: %s", manifest)
        return False
    r = subprocess.run(["kubectl", "apply", "-f", str(manifest)], capture_output=True, text=True)
    return r.returncode == 0


def reset_cluster() -> None:
    subprocess.run(
        ["kubectl", "delete", "podchaos,networkchaos,stresschaos,dnschaos,iochaos,timechaos",
         "--all", "-A"],
        capture_output=True,
    )
    # Also remove any legacy deployment created by named replays
    subprocess.run(["kubectl", "delete", "deployment", "checkoutservice-legacy",
                    "-n", "default", "--ignore-not-found=true"], capture_output=True)
    time.sleep(60)


def wait_for_alert(timeout_s: int = 300) -> dict | None:
    from agents.tools.alertmanager import alertmanager_list_alerts
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        result = alertmanager_list_alerts(active_only=True)
        if result.get("success") and result.get("count", 0) > 0:
            return {"commonLabels": {"alertname": result["alerts"][0]["alertname"]},
                    "alerts": result["alerts"]}
        time.sleep(20)
    log.warning("no alert fired within %ds — synthesising fallback", timeout_s)
    return {"commonLabels": {"alertname": "BenchmarkTimeout"}, "alerts": [],
            "scenario": "unknown", "synthetic": True}


async def run_scenario(scenario_id: str) -> dict:
    t0 = time.time()
    ok = apply_chaos(scenario_id)
    if not ok:
        return {"scenario_id": scenario_id, "status": "skip", "error": "manifest_apply_failed"}

    alert = wait_for_alert()
    alert["scenario_id"] = scenario_id

    try:
        incident = await handle_incident(alert)
        judge_score = await judge_trajectory(incident)
    except Exception as e:
        log.exception("scenario %s failed: %s", scenario_id, e)
        reset_cluster()
        return {"scenario_id": scenario_id, "status": "error", "error": str(e)}

    reset_cluster()

    remediation = incident.get("remediation", {}).get("final", {})
    triage = incident.get("triage", {}).get("final", {})
    total_turns = sum(
        len(incident.get(role, {}).get("trajectory", []))
        for role in ("triage", "diagnosis", "remediation", "comms")
    )

    tier = scenario_id.split("/")[0] if "/" in scenario_id else "unknown"
    episode = {
        "scenario_id": scenario_id,
        "tier": tier,
        "status": "ok",
        "outcome": remediation.get("outcome", "unknown"),
        "resolved": remediation.get("outcome") == "resolved",
        "time_to_resolve_s": remediation.get("time_to_resolve_seconds", round(time.time() - t0)),
        "severity": triage.get("severity", "unknown"),
        "total_turns": total_turns,
        "judge": judge_score,
        "postmortem_path": incident.get("comms", {}).get("final", {}).get("postmortem_path"),
    }
    # Keep reward evaluation centralized so train/eval/bench cannot drift.
    episode["reward_contract"] = evaluate_reward_contract(episode)
    return episode


def compute_summary(results: list[dict], tag: str, model: str) -> dict:
    valid = [r for r in results if r.get("status") == "ok"]
    resolved = [r for r in valid if r.get("resolved")]
    cascades = [r for r in valid if r.get("tier") == "cascade"]
    replays = [r for r in valid if r.get("tier") == "named_replays"]

    def mean(xs, key, default=0.0):
        vals = [x.get(key, default) for x in xs if x.get(key) is not None]
        return round(sum(vals) / len(vals), 3) if vals else 0.0

    judge_scores = [r.get("judge", {}).get("overall", 0) for r in valid if r.get("judge")]
    contract_scores = [r.get("reward_contract", {}).get("total", 0) for r in valid]
    penalties = [r.get("reward_contract", {}).get("penalty_total", 0) for r in valid]

    per_tier = {}
    tiers = sorted({r.get("tier", "unknown") for r in valid})
    for tier in tiers:
        trows = [r for r in valid if r.get("tier") == tier]
        t_resolved = [r for r in trows if r.get("resolved")]
        per_tier[tier] = {
            "count": len(trows),
            "resolution_rate": round(len(t_resolved) / max(len(trows), 1), 3),
            "avg_time_to_resolve_s": mean(trows, "time_to_resolve_s"),
            "avg_reward_contract": round(
                sum(r.get("reward_contract", {}).get("total", 0) for r in trows) / max(len(trows), 1), 3
            ),
        }

    unsafe_action_count = sum(
        1 for r in valid if r.get("reward_contract", {}).get("penalties", {}).get("unsafe_shortcut", 0) > 0
    )
    false_resolution_count = sum(
        1 for r in valid if r.get("reward_contract", {}).get("penalties", {}).get("false_resolution", 0) > 0
    )
    hallucinated_evidence_count = sum(
        1
        for r in valid
        if r.get("reward_contract", {}).get("penalties", {}).get("hallucinated_evidence", 0) > 0
    )

    return {
        "tag": tag,
        "model": model,
        "run_date": datetime.now(timezone.utc).isoformat(),
        "total_scenarios": len(results),
        "resolution_rate": round(len(resolved) / max(len(valid), 1), 3),
        "avg_reward": round(sum(judge_scores) / max(len(judge_scores), 1), 3),
        "avg_reward_contract": round(sum(contract_scores) / max(len(contract_scores), 1), 3),
        "avg_penalty": round(sum(penalties) / max(len(penalties), 1), 3),
        "avg_turns": mean(valid, "total_turns"),
        "avg_time_to_resolve_s": mean(valid, "time_to_resolve_s"),
        "cascade_resolution_rate": round(
            len([r for r in cascades if r.get("resolved")]) / max(len(cascades), 1), 3
        ),
        "named_replay_resolution_rate": round(
            len([r for r in replays if r.get("resolved")]) / max(len(replays), 1), 3
        ),
        "unsafe_action_count": unsafe_action_count,
        "false_resolution_count": false_resolution_count,
        "hallucinated_evidence_count": hallucinated_evidence_count,
        "per_tier": per_tier,
    }


def write_comparison_table(summary: dict) -> None:
    table_path = RESULTS_DIR / "comparison_table.md"
    existing_runs: list[dict] = []
    if table_path.exists():
        # naive parse — rebuild from stored JSON summaries
        for d in RESULTS_DIR.iterdir():
            s_file = d / "results_summary.json"
            if s_file.exists():
                existing_runs.append(json.loads(s_file.read_text()))
    existing_runs = [r for r in existing_runs if r.get("tag") != summary["tag"]]
    existing_runs.append(summary)
    existing_runs.sort(key=lambda x: x.get("run_date", ""))

    header = (
        "| Tag | Model | Resolution | Reward (Judge) | Reward (Contract) | Avg Penalty | Avg Turns "
        "| Cascade Res. | Replay Res. | Date |\n"
    )
    header += "|---|---|---|---|---|---|---|---|---|---|\n"
    rows = ""
    for r in existing_runs:
        rows += (
            f"| {r['tag']} | `{Path(r['model']).name}` "
            f"| {r['resolution_rate']:.0%} "
            f"| {r['avg_reward']:.3f} "
            f"| {r.get('avg_reward_contract', 0):.3f} "
            f"| {r.get('avg_penalty', 0):.3f} "
            f"| {r['avg_turns']:.1f} "
            f"| {r['cascade_resolution_rate']:.0%} "
            f"| {r['named_replay_resolution_rate']:.0%} "
            f"| {r['run_date'][:10]} |\n"
        )
    per_tier_lines = ["\n## Per-tier Breakdown\n"]
    for r in existing_runs:
        per_tier_lines.append(f"\n### {r['tag']}\n")
        per_tier_lines.append("| Tier | Count | Resolution | Avg TTR (s) | Avg Contract Reward |\n")
        per_tier_lines.append("|---|---|---|---|---|\n")
        for tier, item in sorted((r.get("per_tier") or {}).items()):
            per_tier_lines.append(
                f"| {tier} | {item.get('count', 0)} | {item.get('resolution_rate', 0):.0%} "
                f"| {item.get('avg_time_to_resolve_s', 0):.1f} | {item.get('avg_reward_contract', 0):.3f} |\n"
            )
        per_tier_lines.append(
            f"\n- unsafe actions: `{r.get('unsafe_action_count', 0)}`"
            f", false resolutions: `{r.get('false_resolution_count', 0)}`"
            f", hallucinated evidence: `{r.get('hallucinated_evidence_count', 0)}`\n"
        )

    table_path.write_text(
        f"# AtlasOps — Benchmark Results\n\n{header}{rows}{''.join(per_tier_lines)}",
        encoding="utf-8",
    )
    log.info("comparison table updated: %s", table_path)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="Model path or HF ID")
    parser.add_argument("--tag", default="", help="Run label (e.g. grpo_v3, baseline_v2)")
    parser.add_argument("--scenarios", nargs="*", help="Override scenario list")
    parser.add_argument("--output", default="", help="Override output dir")
    parser.add_argument("--adversarial", type=int, default=10,
                        help="Number of dynamic adversarial scenarios to generate (0 to skip)")
    args = parser.parse_args()

    os.environ["AGENT_MODEL"] = args.model
    tag = args.tag or f"run-{int(time.time())}"
    run_id = f"{tag}-{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    out_dir = Path(args.output) if args.output else (RESULTS_DIR / run_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    scenarios = list(args.scenarios or FROZEN_SCENARIOS)

    # Generate fresh adversarial scenarios from 72B judge before running frozen set
    if args.adversarial > 0:
        log.info("generating %d dynamic adversarial scenarios via 72B judge...", args.adversarial)
        # Seed with any existing failure history from prior runs
        prior_failures = []
        for d in RESULTS_DIR.iterdir():
            ep_file = d / "results_per_episode.jsonl"
            if ep_file.exists():
                for line in ep_file.read_text().splitlines():
                    try:
                        ep = json.loads(line)
                        if not ep.get("resolved"):
                            prior_failures.append(ep)
                    except json.JSONDecodeError:
                        pass
        adv_results = await design_batch(prior_failures, count=args.adversarial)
        for adv in adv_results:
            # Add generated manifest path as a runnable scenario
            rel = str(Path(adv["manifest_path"]).relative_to(Path("bench/chaos_manifests")))
            rel = rel.replace("\\", "/").removesuffix(".yaml")
            scenarios.append(rel)
        log.info("added %d adversarial scenarios to run", len(adv_results))
    log.info("running %d scenarios for tag=%s model=%s", len(scenarios), tag, args.model)

    results = []
    episodes_file = out_dir / "results_per_episode.jsonl"
    with episodes_file.open("w", encoding="utf-8") as f:
        for i, s in enumerate(scenarios, 1):
            log.info("[%d/%d] %s", i, len(scenarios), s)
            r = await run_scenario(s)
            results.append(r)
            f.write(json.dumps(r) + "\n")
            f.flush()

    summary = compute_summary(results, tag, args.model)
    (out_dir / "results_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_comparison_table(summary)

    log.info("=== Benchmark complete ===")
    log.info("  Resolution rate : %.1f%%", summary["resolution_rate"] * 100)
    log.info("  Avg reward      : %.3f", summary["avg_reward"])
    log.info("  Results         : %s", out_dir)


if __name__ == "__main__":
    asyncio.run(main())
