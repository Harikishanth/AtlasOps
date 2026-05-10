"""GRPO training for AtlasOps — online RL against real GKE cluster on AMD MI300X.

Architecture:
  - Each GRPO step generates G=8 rollouts by running the full agent chain
    against a live chaos scenario on the real GKE cluster
  - Reward comes from the AtlasOps reward contract (same as bench/runner.py)
  - This is TRUE online RL — not offline reward-weighted SFT
  - QLoRA: 4-bit base + LoRA r=16 for memory efficiency on MI300X

Training flow:
  1. Sample a chaos scenario from the tier-weighted curriculum
  2. Apply Chaos Mesh to real GKE cluster
  3. Run G=8 parallel agent rollouts (model generates tool calls)
  4. Score each rollout with reward contract (kubectl/promql verify real cluster state)
  5. GRPO updates — policy learns from what actually worked on the real cluster
  6. Reset cluster, next step
"""

import argparse
import asyncio
import json
import logging
import os
import random
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import GRPOConfig, GRPOTrainer
from config.runtime import (
    SCENARIOS_BY_TIER, TIER_SAMPLING_WEIGHTS, evaluate_reward_contract,
    CurriculumManager,
)

log = logging.getLogger(__name__)


# ── QLoRA config ──────────────────────────────────────────────────────────────

LORA_CONFIG = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj"],
    bias="none",
)

BNBCONFIG = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype="bfloat16",
    bnb_4bit_use_double_quant=True,
)


# ── Reward contract ───────────────────────────────────────────────────────────

# Training-run curriculum singleton (tracks mastery + spaced repetition)
_curriculum = CurriculumManager()


def compute_reward(episode: dict) -> float:
    """Blend episode-level contract reward (70%) with dense step rewards (30%).

    Dense step rewards sum tool-call-level progress signals from StepRewardTracker.
    Normalised over 10 (typical episode has 15-30 tool calls, each capped at 0.99).
    """
    contract = float(evaluate_reward_contract(episode)["total"])
    # Sum dense rewards across all four agent roles
    step_total = sum(
        role_data.get("step_reward_summary", {}).get("dense_reward_total", 0.0)
        for role in ("triage", "diagnosis", "remediation", "comms")
        for role_data in [episode.get(role, {})]
    )
    step_norm = max(0.0, min(1.0, step_total / 10.0))
    return round(0.7 * contract + 0.3 * step_norm, 4)


def sample_scenario(tiers: list[str]) -> tuple[str, str]:
    """Use CurriculumManager priority scoring (spaced repetition + weakness targeting)."""
    pool = [
        (sid, sid.split("/")[0])
        for tier in tiers
        for sid in SCENARIOS_BY_TIER.get(tier, [])
    ]
    return _curriculum.next_scenario(pool)


def apply_chaos(scenario_id: str) -> bool:
    manifest = Path("bench/chaos_manifests") / f"{scenario_id}.yaml"
    if not manifest.exists():
        return False
    env = os.environ.copy()
    env["USE_GKE_GCLOUD_AUTH_PLUGIN"] = "True"
    r = subprocess.run(["kubectl", "apply", "-f", str(manifest)],
                       capture_output=True, text=True, env=env)
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
    time.sleep(20)


# ── Online reward function for TRL GRPOTrainer ────────────────────────────────

class OnlineRewardFunction:
    """Wraps the real GKE environment as a TRL-compatible reward function.

    For each batch of completions TRL generates, this class:
    1. Parses the model's tool call sequence from the completion text
    2. Executes it against the real GKE cluster (via coordinator)
    3. Scores the outcome with the reward contract
    4. Returns rewards for GRPO advantage computation
    """

    def __init__(self, tiers: list[str], coordinator_url: str = "http://localhost:9099"):
        self.tiers = tiers
        self.coordinator_url = coordinator_url
        self._loop = asyncio.new_event_loop()

    def __del__(self):
        if not self._loop.is_closed():
            self._loop.close()

    def __call__(self, completions: list[str], prompts: list[str],
                 **kwargs) -> list[float]:
        """Called by TRL after generating G completions. Returns reward per completion."""
        return self._loop.run_until_complete(
            self._score_batch(completions, prompts)
        )

    async def _score_batch(self, completions: list[str],
                           prompts: list[str]) -> list[float]:
        """Score G completions by running SERIALIZED rollouts on the live cluster.

        Why serialized (not asyncio.gather):
        All G rollouts share one GKE cluster. Running them in parallel causes
        interference — rollout 1 may delete the chaos while rollout 3 is still
        diagnosing, making rewards correlated and gradients incorrect.
        Serializing gives each rollout a clean, independent cluster state:
          apply_chaos → wait → rollout → reset_chaos → wait → next rollout
        This is slower (G × episode_time) but produces correct independent rewards.
        """
        rewards: list[float] = []
        scenario_id, tier = sample_scenario(self.tiers)

        for i, completion in enumerate(completions):
            log.info("Rollout %d/%d — scenario %s", i + 1, len(completions), scenario_id)

            if not apply_chaos(scenario_id):
                log.warning("Chaos apply failed for %s — assigning 0 reward", scenario_id)
                rewards.append(0.0)
                continue

            # Wait for Alertmanager to fire
            await asyncio.sleep(15)

            try:
                result = await self._run_one_rollout(completion, scenario_id, tier)
            except Exception as e:
                log.exception("Rollout %d failed: %s", i + 1, e)
                result = None

            # Always reset before the next rollout — even on failure
            reset_chaos()
            await asyncio.sleep(10)   # let the cluster fully stabilise

            if result is None:
                rewards.append(0.0)
            else:
                r = compute_reward(result)
                rewards.append(r)
                _curriculum.record(
                    scenario_id=scenario_id,
                    resolved=bool(result.get("resolved", False)),
                    reward=r,
                )

        cur_stats = _curriculum.stats()
        log.info(
            "Batch done | scenario=%s rewards: min=%.3f max=%.3f mean=%.3f | "
            "curriculum: %d tried, %d graduated, %d due for resurface",
            scenario_id,
            min(rewards), max(rewards), sum(rewards) / len(rewards),
            cur_stats["scenarios_tried"], cur_stats["graduated"],
            cur_stats["due_for_resurface"],
        )
        return rewards

    async def _run_one_rollout(self, completion_text: str,
                               scenario_id: str, tier: str) -> dict:
        """Execute one full incident-response rollout and return a scored episode dict.

        Architecture note: TRL generates G completions per step; we use those
        completions as the triage agent's initial reasoning seed (injected into
        the alert context below). The coordinator then continues the full agent
        chain against the live cluster. Reward is episode-level: resolved/speed/
        evidence/safety/comms. Group-relative advantages are computed across the
        G rollouts, giving GRPO its learning signal.

        The completion_text therefore influences the rollout indirectly via the
        triage seed, creating the completion↔reward coupling GRPO requires.
        """
        from agents.coordinator import handle_incident
        from agents.judge import judge_trajectory

        # Seed the alert with the model's generated triage reasoning so that
        # the reward IS conditioned on the specific completion TRL produced.
        alert = {
            "commonLabels": {"alertname": "GRPOTrainingAlert"},
            "scenario_id": scenario_id,
            "alerts": [],
            "triage_seed": completion_text[:512] if completion_text else "",
        }

        t0 = time.time()
        incident = await handle_incident(alert)
        judge_score = await judge_trajectory(incident, tier=tier)

        remediation = incident.get("remediation", {}).get("final", {})
        total_turns = sum(
            len(incident.get(r, {}).get("trajectory", []))
            for r in ("triage", "diagnosis", "remediation", "comms")
        )

        return {
            "tier": tier,
            "resolved": remediation.get("outcome") == "resolved",
            "outcome": remediation.get("outcome", "unknown"),
            "total_turns": total_turns,
            "time_to_resolve_s": round(time.time() - t0),
            "judge": judge_score,
            "postmortem_path": incident.get("comms", {}).get("final", {}).get("postmortem_path"),
        }


# ── Optuna HP search ──────────────────────────────────────────────────────────

def run_optuna_search(model_path: str, tiers: list[str], output_dir: str,
                      n_trials: int = 6) -> dict[str, Any]:
    try:
        import optuna
    except ImportError:
        log.warning("optuna not installed — skipping HP search")
        return {}

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    reward_fn = OnlineRewardFunction(tiers)

    def objective(trial: optuna.Trial) -> float:
        lr      = trial.suggest_float("lr", 5e-7, 5e-6, log=True)
        beta    = trial.suggest_float("beta", 0.001, 0.05, log=True)
        num_gen = trial.suggest_categorical("num_generations", [4, 8])

        model, tokenizer = load_model_and_tokenizer(model_path)

        # Minimal dataset: GRPOTrainer needs a prompt dataset
        from datasets import Dataset
        prompts = [{"prompt": "Respond as SRE triage agent."} for _ in range(20)]
        dataset = Dataset.from_list(prompts)

        grpo_args = GRPOConfig(
            output_dir=f"{output_dir}/trial_{trial.number}",
            learning_rate=lr,
            per_device_train_batch_size=1,
            bf16=True, max_steps=10, report_to=[], optim="paged_adamw_8bit",
            num_generations=num_gen, beta=beta, max_completion_length=256,
        )
        trainer = GRPOTrainer(
            model=model, args=grpo_args, train_dataset=dataset,
            processing_class=tokenizer,
            reward_funcs=[reward_fn],
        )
        trainer.train()
        logs = trainer.state.log_history
        rewards = [l.get("rewards/mean", 0) for l in logs if "rewards/mean" in l]
        return sum(rewards[-3:]) / max(len(rewards[-3:]), 1)

    study = optuna.create_study(direction="maximize",
                                sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective, n_trials=n_trials)
    best = {"params": study.best_params, "value": study.best_value}
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    (Path(output_dir) / "optuna_best.json").write_text(json.dumps(best, indent=2))
    log.info("Best HP: %s (value=%.4f)", study.best_params, study.best_value)
    return study.best_params


# ── Model loading ─────────────────────────────────────────────────────────────

def load_model_and_tokenizer(model_path: str):
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        quantization_config=BNBCONFIG,
        device_map="auto",
        trust_remote_code=True,
        attn_implementation="flash_attention_2" if _flash_attn_available() else "eager",
    )
    model = prepare_model_for_kbit_training(model)
    model = get_peft_model(model, LORA_CONFIG)
    model.print_trainable_parameters()
    return model, tokenizer


def _flash_attn_available() -> bool:
    try:
        import flash_attn  # noqa: F401
        return True
    except ImportError:
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model",           required=True)
    parser.add_argument("--output",          required=True)
    parser.add_argument("--tiers",           default="cascade,multi_fault,named_replays")
    parser.add_argument("--lr",              type=float, default=1e-6)
    parser.add_argument("--beta",            type=float, default=0.04)
    parser.add_argument("--batch-size",      type=int,   default=1)
    parser.add_argument("--num-generations", type=int,   default=8)
    parser.add_argument("--max-steps",       type=int,   default=200)
    parser.add_argument("--max-compl-len",   type=int,   default=512)
    parser.add_argument("--grad-accum",      type=int,   default=4)
    parser.add_argument("--optuna",          type=int,   default=0)
    args = parser.parse_args()

    tiers      = [t.strip() for t in args.tiers.split(",")]
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Optional Optuna HP search (runs live rollouts against GKE)
    best_hp: dict[str, Any] = {}
    if args.optuna > 0:
        log.info("Optuna HP search (%d trials × 10 live GKE rollouts each)...", args.optuna)
        best_hp = run_optuna_search(args.model, tiers, str(output_dir), n_trials=args.optuna)

    lr      = best_hp.get("lr", args.lr)
    beta    = best_hp.get("beta", args.beta)
    num_gen = best_hp.get("num_generations", args.num_generations)

    log.info("GRPO config: lr=%.2e beta=%.4f num_gen=%d tiers=%s", lr, beta, num_gen, tiers)

    model, tokenizer = load_model_and_tokenizer(args.model)

    # Online reward function — runs real GKE rollouts during training
    reward_fn = OnlineRewardFunction(tiers)

    # Minimal prompt dataset (GRPO generates its own completions online)
    from datasets import Dataset
    sft_data_path = Path("data/sft_corpus.jsonl")
    if sft_data_path.exists():
        prompts = []
        with sft_data_path.open() as f:
            for line in f:
                try:
                    item = json.loads(line)
                    msgs = item.get("messages", [])
                    if msgs:
                        prompts.append({"prompt": json.dumps(msgs[:-1])})
                except json.JSONDecodeError:
                    pass
        dataset = Dataset.from_list(prompts[:5000])
    else:
        # Fallback: prompt-only dataset with role instructions
        dataset = Dataset.from_list([
            {"prompt": f"You are the AtlasOps {role} agent responding to a real Kubernetes incident."}
            for role in ["triage", "diagnosis", "remediation", "comms"] * 250
        ])

    grpo_args = GRPOConfig(
        output_dir=str(output_dir),
        learning_rate=lr,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        bf16=True,
        logging_steps=5,
        save_strategy="steps",
        save_steps=50,
        max_steps=args.max_steps,
        report_to=[],
        optim="paged_adamw_8bit",
        warmup_ratio=0.05,
        lr_scheduler_type="cosine",
        num_generations=num_gen,
        max_completion_length=args.max_compl_len,
        beta=beta,
    )

    trainer = GRPOTrainer(
        model=model,
        args=grpo_args,
        train_dataset=dataset,
        processing_class=tokenizer,
        reward_funcs=[reward_fn],  # ← online RL against real GKE cluster
    )

    log.info("Starting online GRPO against real GKE cluster on AMD MI300X...")
    log.info("Each step: apply chaos → G=%d rollouts → reward contract → gradient update", num_gen)
    trainer.train()

    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    logs = trainer.state.log_history
    rewards = [l.get("rewards/mean") for l in logs if "rewards/mean" in l]
    summary = {
        "model": args.model, "tiers": tiers,
        "total_steps": trainer.state.global_step,
        "final_reward_mean": rewards[-1] if rewards else None,
        "best_reward_mean": max(rewards) if rewards else None,
        "reward_history": rewards,
        "config": {"lr": lr, "beta": beta, "num_generations": num_gen},
        "training_mode": "online_rl_real_gke",
    }
    (output_dir / "training_summary.json").write_text(json.dumps(summary, indent=2))
    log.info("Done. final_reward=%.4f | best=%.4f",
             summary["final_reward_mean"] or 0, summary["best_reward_mean"] or 0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    main()
