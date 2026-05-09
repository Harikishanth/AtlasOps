"""Fast SFT trajectory generator — no Chaos Mesh required.

Runs all 31 scenarios from inference.py directly against the real GKE cluster
using the pre-defined alert payloads (no waiting for real alerts to fire).

Each completed incident chain → multiple ChatML training examples (one per turn).
Writes to data/sft_corpus.jsonl in the format expected by training/sft.py.

Usage:
    python training/generate_trajectories_fast.py
    python training/generate_trajectories_fast.py --scenarios warmup sf
    python training/generate_trajectories_fast.py --repeats 3 --max-scenarios 10
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

# ── env + UTF-8 ──────────────────────────────────────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_env = Path(__file__).parent.parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("gen_traj")

# ── Import scenario catalogue from inference.py ───────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
from inference import ALERTS, SCENARIO_GROUPS  # noqa: E402

OUTPUT = Path("data/sft_corpus.jsonl")


def load_prompt(role: str) -> str:
    p = Path("agents/prompts") / f"{role}.md"
    return p.read_text(encoding="utf-8") if p.exists() else f"You are the {role} agent."


def trajectory_to_sft(scenario_id: str, incident: dict, elapsed_s: float) -> list[dict]:
    """Convert one incident chain into ChatML training examples.

    Each turn where the agent called a tool or produced a conclusion becomes
    one training example with:
      system  → role-specific system prompt
      user    → full input context for that agent
      assistant → the action taken (tool call JSON or conclusion JSON)
    """
    examples = []

    # Build per-role user context
    triage_final  = incident.get("triage",      {}).get("final", {})
    diag_final    = incident.get("diagnosis",   {}).get("final", {})
    remed_final   = incident.get("remediation", {}).get("final", {})

    alert = incident.get("alert", {})

    role_inputs = {
        "triage":      {"scenario_id": scenario_id, "alert": alert},
        "diagnosis":   {"scenario_id": scenario_id, "triage": triage_final},
        "remediation": {"scenario_id": scenario_id, "triage": triage_final, "diagnosis": diag_final},
        "comms":       {"scenario_id": scenario_id, "triage": triage_final,
                        "diagnosis": diag_final, "remediation": remed_final},
    }

    for role in ("triage", "diagnosis", "remediation", "comms"):
        system_prompt = load_prompt(role)
        user_input    = role_inputs[role]
        agent_data    = incident.get(role, {})
        trajectory    = agent_data.get("trajectory", [])
        final         = agent_data.get("final", {})

        # Build a running message history for this role
        messages: list[dict] = [
            {"role": "system",    "content": system_prompt},
            {"role": "user",      "content": json.dumps(user_input, ensure_ascii=False)},
        ]

        for entry in trajectory:
            if entry.get("dedup_blocked") or entry.get("cap_blocked") or entry.get("blocked_by_policy"):
                continue  # skip blocked calls — bad training signal

            if "tool" in entry:
                # Tool call turn
                tool_call_content = json.dumps({
                    "name": entry["tool"],
                    "arguments": entry.get("args", {}),
                }, ensure_ascii=False)

                examples.append({
                    "scenario_id":  scenario_id,
                    "role":         role,
                    "turn_type":    "tool_call",
                    "messages":     messages.copy() + [
                        {"role": "assistant", "content": tool_call_content}
                    ],
                    "reward":       _score(triage_final, diag_final, remed_final, elapsed_s),
                })

                # Append tool result to running history for next turn
                messages.append({"role": "assistant", "content": tool_call_content})
                messages.append({
                    "role": "tool",
                    "content": json.dumps(entry.get("output", {}), ensure_ascii=False)[:2000],
                })

            elif "content" in entry:
                # Conclusion turn
                examples.append({
                    "scenario_id":  scenario_id,
                    "role":         role,
                    "turn_type":    "conclusion",
                    "messages":     messages.copy() + [
                        {"role": "assistant", "content": entry["content"]}
                    ],
                    "reward":       _score(triage_final, diag_final, remed_final, elapsed_s),
                })

        # If trajectory is empty but final exists — add a direct example
        if not trajectory and final and "raw" not in final and "error" not in final:
            examples.append({
                "scenario_id":  scenario_id,
                "role":         role,
                "turn_type":    "conclusion",
                "messages":     messages + [
                    {"role": "assistant", "content": json.dumps(final, ensure_ascii=False)}
                ],
                "reward":       _score(triage_final, diag_final, remed_final, elapsed_s),
            })

    return examples


def _score(triage: dict, diagnosis: dict, remediation: dict, elapsed_s: float) -> float:
    """Simple reward score for weighting training examples."""
    sev    = triage.get("severity", "") in {"P0", "P1", "P2", "P3"}
    rc     = bool(diagnosis.get("root_cause"))
    out    = remediation.get("outcome", "")
    res    = {"resolved": 1.0, "partial": 0.7, "escalated": 0.4, "unresolved": 0.1}.get(out, 0.1)
    speed  = max(0.0, 1.0 - (elapsed_s - 30) / 300) if elapsed_s < 300 else 0.0
    return round(0.2 * sev + 0.3 * rc + 0.4 * res + 0.1 * speed, 3)


async def run_scenario(scenario_id: str) -> tuple[dict, float]:
    from agents.coordinator import handle_incident
    from agents.stream import get_history

    alert = dict(ALERTS[scenario_id])
    alert["scenario_id"] = scenario_id

    t0 = time.time()
    incident = await handle_incident(alert)
    elapsed = time.time() - t0

    # Attach alert to incident for trajectory_to_sft
    incident["alert"] = alert
    return incident, elapsed


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", nargs="*",
                        help="Scenario groups or IDs. Groups: warmup hist sf cascade multi all. "
                             "Default: all")
    parser.add_argument("--repeats",       type=int, default=1,
                        help="How many times to run each scenario (more = more diverse data)")
    parser.add_argument("--max-scenarios", type=int, default=0,
                        help="Cap number of unique scenarios (0 = no cap)")
    parser.add_argument("--output", default="data/sft_corpus.jsonl")
    parser.add_argument("--min-reward", type=float, default=0.0,
                        help="Skip examples below this reward threshold")
    args = parser.parse_args()

    # Resolve scenario list
    if not args.scenarios:
        scenario_ids = list(ALERTS.keys())
    else:
        scenario_ids = []
        for s in args.scenarios:
            if s in SCENARIO_GROUPS:
                scenario_ids.extend(SCENARIO_GROUPS[s])
            elif s in ALERTS:
                scenario_ids.append(s)
            else:
                log.warning("unknown scenario/group: %s — skipping", s)
        scenario_ids = list(dict.fromkeys(scenario_ids))  # deduplicate, preserve order

    if args.max_scenarios:
        scenario_ids = scenario_ids[:args.max_scenarios]

    total_runs = len(scenario_ids) * args.repeats
    log.info("generating SFT data: %d scenarios × %d repeats = %d runs",
             len(scenario_ids), args.repeats, total_runs)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped = 0
    run_num = 0

    with output.open("w", encoding="utf-8") as f:
        for repeat in range(args.repeats):
            for sid in scenario_ids:
                run_num += 1
                log.info("[%d/%d] %s (repeat %d)", run_num, total_runs, sid, repeat + 1)
                try:
                    incident, elapsed = await run_scenario(sid)
                    examples = trajectory_to_sft(sid, incident, elapsed)
                    for ex in examples:
                        if ex["reward"] < args.min_reward:
                            skipped += 1
                            continue
                        f.write(json.dumps(ex, ensure_ascii=False) + "\n")
                        written += 1
                    f.flush()
                    log.info("  -> %d examples (reward avg=%.3f, elapsed=%.1fs)",
                             len(examples),
                             sum(e["reward"] for e in examples) / max(len(examples), 1),
                             elapsed)
                except Exception as e:
                    log.error("  scenario %s failed: %s", sid, e)
                    continue

    log.info("done. wrote %d examples (%d skipped) to %s", written, skipped, output)
    print(f"\n[OK] {written} training examples saved to {output}")
    print(f"     Run: python training/sft.py --data {output}")


if __name__ == "__main__":
    asyncio.run(main())
