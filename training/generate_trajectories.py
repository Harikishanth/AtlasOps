"""Generate SFT trajectories by running scripted incident scenarios on a real GKE cluster.

For each scenario:
  1. Apply Chaos Mesh manifest
  2. Wait for Alertmanager to fire
  3. Run the 4-agent chain (with a teacher model — Claude/GPT-4 — for high-quality demos)
  4. Score with the judge
  5. Record (state, action, output, reward) tuples
  6. Reset cluster

Output: data/sft_corpus.jsonl  (one trajectory per line, ChatML format for SFT)
"""

import argparse
import asyncio
import json
import logging
import subprocess
import time
from pathlib import Path

from agents.coordinator import handle_incident
from agents.judge import judge_trajectory
from config.runtime import evaluate_reward_contract


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("trajectories")


def list_scenarios(manifests_root: Path) -> list[Path]:
    return sorted(p for p in manifests_root.rglob("*.yaml") if p.is_file())


def apply_chaos(manifest: Path) -> bool:
    log.info("applying %s", manifest)
    r = subprocess.run(["kubectl", "apply", "-f", str(manifest)], capture_output=True, text=True)
    if r.returncode != 0:
        log.error("kubectl apply failed: %s", r.stderr)
        return False
    return True


def wait_for_alert(timeout_s: int = 300) -> dict | None:
    """Poll Alertmanager until at least one alert is firing."""
    from agents.tools.alertmanager import alertmanager_list_alerts
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        result = alertmanager_list_alerts(active_only=True)
        if result.get("success") and result.get("count", 0) > 0:
            return {
                "commonLabels": {"alertname": result["alerts"][0]["alertname"]},
                "alerts": result["alerts"],
            }
        time.sleep(15)
    log.warning("no alert fired within %ds", timeout_s)
    return None


def reset_cluster() -> None:
    log.info("resetting cluster (deleting all chaos)")
    subprocess.run(
        ["kubectl", "delete", "podchaos,networkchaos,stresschaos,dnschaos,iochaos,timechaos",
         "--all", "-A"],
        capture_output=True,
    )
    time.sleep(60)  # wait for pods to recover


def trajectory_to_sft_examples(
    scenario_id: str, tier: str, incident: dict, judge_score: dict, reward_contract: dict
) -> list[dict]:
    """Convert one full incident chain into ChatML training examples (one per agent turn)."""
    examples = []
    for role in ("triage", "diagnosis", "remediation", "comms"):
        agent_data = incident.get(role, {})
        for entry in agent_data.get("trajectory", []):
            if "tool" in entry:
                examples.append({
                    "scenario_id": scenario_id,
                    "role": role,
                    "messages": [
                        {"role": "system", "content": f"You are the {role} agent."},
                        {"role": "user", "content": json.dumps({"step": entry["turn"]})},
                        {"role": "assistant", "content": json.dumps({"tool": entry["tool"], "args": entry["args"]})},
                    ],
                    "tier": tier,
                    "reward": reward_contract.get("total", judge_score.get("overall", 0.0)),
                    "reward_contract": reward_contract,
                    "judge": judge_score,
                })
            else:
                examples.append({
                    "scenario_id": scenario_id,
                    "role": role,
                    "messages": [
                        {"role": "system", "content": f"You are the {role} agent."},
                        {"role": "assistant", "content": entry.get("content", "")},
                    ],
                    "tier": tier,
                    "reward": reward_contract.get("total", judge_score.get("overall", 0.0)),
                    "reward_contract": reward_contract,
                    "judge": judge_score,
                })
    return examples


async def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifests", default="bench/chaos_manifests")
    parser.add_argument("--output", default="data/sft_corpus.jsonl")
    parser.add_argument("--max-scenarios", type=int, default=0, help="0 = all")
    parser.add_argument("--repeats", type=int, default=10, help="repeats per scenario for variance")
    args = parser.parse_args()

    scenarios = list_scenarios(Path(args.manifests))
    if args.max_scenarios:
        scenarios = scenarios[: args.max_scenarios]
    log.info("found %d scenarios; %d repeats each = %d trajectories",
             len(scenarios), args.repeats, len(scenarios) * args.repeats)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with output.open("a", encoding="utf-8") as f:
        for manifest in scenarios:
            tier = manifest.parent.name
            scenario_id = f"{tier}/{manifest.stem}"
            for repeat in range(args.repeats):
                if not apply_chaos(manifest):
                    continue
                alert = wait_for_alert()
                if not alert:
                    reset_cluster()
                    continue
                t0 = time.time()
                incident = await handle_incident(alert)
                judge_score = await judge_trajectory(incident)
                remediation = incident.get("remediation", {}).get("final", {})
                episode = {
                    "scenario_id": scenario_id,
                    "tier": tier,
                    "resolved": remediation.get("outcome") == "resolved",
                    "outcome": remediation.get("outcome", "unknown"),
                    "time_to_resolve_s": float(
                        remediation.get("time_to_resolve_seconds", round(time.time() - t0))
                    ),
                    "total_turns": sum(
                        len(incident.get(r, {}).get("trajectory", []))
                        for r in ("triage", "diagnosis", "remediation", "comms")
                    ),
                    "postmortem_path": incident.get("comms", {}).get("final", {}).get("postmortem_path"),
                    "judge": judge_score,
                }
                # Use the same shared reward contract used by benchmark + GRPO.
                reward_contract = evaluate_reward_contract(episode)
                examples = trajectory_to_sft_examples(
                    scenario_id, tier, incident, judge_score, reward_contract
                )
                for ex in examples:
                    f.write(json.dumps(ex) + "\n")
                    written += 1
                f.flush()
                log.info(
                    "[%s repeat=%d] judge=%.2f contract=%.2f written=%d",
                    scenario_id,
                    repeat,
                    judge_score.get("overall", 0),
                    reward_contract.get("total", 0),
                    written,
                )
                reset_cluster()

    log.info("done. %d examples in %s", written, output)


if __name__ == "__main__":
    asyncio.run(run())
