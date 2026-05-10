#!/usr/bin/env python3
"""Merge a PEFT LoRA adapter into base weights and optionally push to the Hub.

Run on a GPU machine after training:
  pip install -e ".[train]"
  huggingface-cli login

  python training/merge_lora_for_hub.py \\
    --base Qwen/Qwen2.5-7B-Instruct \\
    --adapter checkpoints/grpo_v3 \\
    --repo-id your-org/atlasops-7b-grpo \\
    --private

Then set Space secret AGENT_MODEL=your-org/atlasops-7b-grpo .

If you omit --repo-id and --push, writes ./merged_hub_export only."""

from __future__ import annotations

import argparse
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True)
    p.add_argument("--adapter", required=True, type=Path)
    p.add_argument("--out", type=Path, default=Path("merged_hub_export"))
    p.add_argument("--repo-id", dest="repo_id", default="", help="HF model repo; if set, uploads merged weights")
    p.add_argument("--private", action="store_true")
    args = p.parse_args()

    if not args.adapter.is_dir():
        raise SystemExit(f"Adapter dir not found: {args.adapter}")

    tok = AutoTokenizer.from_pretrained(args.base, trust_remote_code=True)
    base = AutoModelForCausalLM.from_pretrained(
        args.base,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )
    lora = PeftModel.from_pretrained(base, str(args.adapter), device_map="auto")
    merged = lora.merge_and_unload()
    args.out.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(args.out, safe_serialization=True)
    tok.save_pretrained(args.out)

    print(f"Saved merged weights to {args.out.resolve()}")

    if args.repo_id:
        merged.push_to_hub(args.repo_id, private=args.private)
        tok.push_to_hub(args.repo_id, private=args.private)
        print(f"Pushed to https://huggingface.co/{args.repo_id}")


if __name__ == "__main__":
    main()
