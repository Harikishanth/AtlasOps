"""GRPO training entrypoint for AtlasOps.

Training reward is aligned with benchmark reward contract:
- Prefer `reward_contract.total` when present in dataset rows
- Otherwise compute the same contract from episode-style fields
- Fallback to legacy `reward` only when contract inputs are unavailable
"""

import argparse
import json
import math
from pathlib import Path

from datasets import Dataset
from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainingArguments
from trl import GRPOConfig, GRPOTrainer

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


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _bounded_speed_score(seconds: float, tier: str) -> float:
    midpoint = {
        "warmup": 90.0,
        "single_fault": 150.0,
        "cascade": 240.0,
        "multi_fault": 300.0,
        "named_replays": 300.0,
        "adversarial": 360.0,
    }.get(tier, 240.0)
    slope = 40.0
    return max(0.0, min(1.0, 1.0 / (1.0 + math.exp((seconds - midpoint) / slope))))


def _compute_contract_reward(item: dict) -> float:
    """Compute benchmark-aligned contract reward from an episode row."""
    tier = str(item.get("tier", "unknown"))
    resolved = bool(item.get("resolved", False))
    outcome = str(item.get("outcome", "unknown"))
    turns = int(item.get("total_turns", 0))
    ttr = float(item.get("time_to_resolve_s", 9999))
    judge = item.get("judge", {}) or {}
    reasoning = float(judge.get("reasoning", 0.0))
    correctness = float(judge.get("correctness", 0.0))
    efficiency = float(judge.get("efficiency", 0.0))

    r_resolve = 1.0 if resolved else (0.5 if outcome == "partial" else 0.0)
    r_speed = _bounded_speed_score(ttr, tier)
    r_evidence = _clamp01((reasoning + correctness) / 2.0)
    r_safety = _clamp01(efficiency)
    r_comms = 1.0 if item.get("postmortem_path") else 0.3

    penalties = {
        "command_spam": 0.10 if turns > 40 else 0.0,
        "false_resolution": 0.25 if (not resolved and outcome == "resolved") else 0.0,
        "unsafe_shortcut": 0.20 if efficiency < 0.3 else 0.0,
        "hallucinated_evidence": 0.20 if (reasoning < 0.25 and correctness < 0.5) else 0.0,
        "over_silence": 0.10 if ("silence" in json.dumps(item).lower() and not resolved) else 0.0,
    }

    weights = {
        "r_resolve": 0.35,
        "r_speed": 0.15,
        "r_evidence": 0.20,
        "r_safety": 0.20,
        "r_comms": 0.10,
    }
    if tier == "single_fault":
        weights.update({"r_evidence": 0.25, "r_speed": 0.10})
    elif tier == "cascade":
        weights.update({"r_resolve": 0.30, "r_evidence": 0.25, "r_speed": 0.10})
    elif tier == "multi_fault":
        weights.update({"r_safety": 0.25, "r_evidence": 0.25, "r_speed": 0.10})
    elif tier in ("adversarial", "named_replays"):
        penalties = {k: v * 1.25 for k, v in penalties.items()}
        weights.update({"r_safety": 0.25, "r_evidence": 0.25, "r_speed": 0.05})

    weighted = (
        weights["r_resolve"] * r_resolve
        + weights["r_speed"] * r_speed
        + weights["r_evidence"] * r_evidence
        + weights["r_safety"] * r_safety
        + weights["r_comms"] * r_comms
    )
    return _clamp01(weighted - sum(penalties.values()))


def _select_training_reward(item: dict) -> float:
    """Use contract reward when available, fallback safely."""
    # Preferred explicit value from benchmark pipeline.
    contract = item.get("reward_contract") or {}
    if isinstance(contract, dict) and "total" in contract:
        return float(contract["total"])

    # Or compute from episode-style keys if present.
    episode_keys = {"tier", "resolved", "outcome", "time_to_resolve_s", "judge"}
    if any(k in item for k in episode_keys):
        return _compute_contract_reward(item)

    # Last fallback for older corpora.
    return float(item.get("reward", 0.0))


def load_reward_dataset(path: str) -> Dataset:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            item = json.loads(line)
            reward = _select_training_reward(item)
            rows.append(
                {
                    "prompt": json.dumps(item.get("messages", []), ensure_ascii=False),
                    "reward": reward,
                }
            )
    return Dataset.from_list(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="SFT checkpoint path")
    parser.add_argument("--output", required=True, help="Output checkpoint directory")
    parser.add_argument("--data", default="data/sft_corpus.jsonl", help="Reward-labeled jsonl data")
    parser.add_argument("--tiers", default="cascade,multi_fault,named_replays")
    parser.add_argument("--lr", type=float, default=1e-6)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--num-generations", type=int, default=4)
    parser.add_argument("--max-prompt-len", type=int, default=1024)
    parser.add_argument("--max-completion-len", type=int, default=512)
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset = load_reward_dataset(args.data)
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # QLoRA: load SFT adapter checkpoint in 4-bit, attach fresh LoRA head for GRPO
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        quantization_config=BNBCONFIG,
        device_map="auto",
        trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model)
    model = get_peft_model(model, LORA_CONFIG)
    model.print_trainable_parameters()

    train_args = TrainingArguments(
        output_dir=str(output_dir),
        learning_rate=args.lr,
        per_device_train_batch_size=args.batch_size,
        logging_steps=10,
        save_strategy="epoch",
        bf16=True,
        report_to=[],
        optim="paged_adamw_8bit",
    )
    grpo_cfg = GRPOConfig(
        num_generations=args.num_generations,
        max_prompt_length=args.max_prompt_len,
        max_completion_length=args.max_completion_len,
    )

    trainer = GRPOTrainer(
        model=model,
        args=train_args,
        train_dataset=dataset,
        processing_class=tokenizer,
        grpo_config=grpo_cfg,
    )
    trainer.train()
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))


if __name__ == "__main__":
    main()
