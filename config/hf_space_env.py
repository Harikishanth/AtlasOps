"""Hugging Face Space defaults for AtlasOps inference.

Spaces usually provide `HF_TOKEN` (read / inference). This module maps that onto
OpenAI-compatible calls for both agents (7B) and judge (72B).

Enable on the Space root:
    ATLASOPS_USE_HF_INFERENCE=1

Optional overrides:
    HF_INFERENCE_BASE=https://router.huggingface.co/v1
    BACKEND=vllm|openai   (URLs still come from VLLM_BASE / router)
"""

from __future__ import annotations

import os


def apply_hf_space_inference_defaults() -> None:
    tok = (
        os.getenv("HF_TOKEN", "").strip()
        or os.getenv("HUGGING_FACE_HUB_TOKEN", "").strip()
    )
    if tok:
        os.environ.setdefault("LLM_API_KEY", tok)
        os.environ.setdefault("JUDGE_API_KEY", tok)

    flag = os.getenv("ATLASOPS_USE_HF_INFERENCE", "").lower()
    if flag not in ("1", "true", "yes"):
        return

    base = os.getenv("HF_INFERENCE_BASE", "https://router.huggingface.co/v1").rstrip("/")

    os.environ.setdefault("BACKEND", "openai")

    prev_agent = os.getenv("VLLM_BASE", "").strip()
    prev_judge = os.getenv("JUDGE_URL", "").strip()
    localhostish = ("localhost", "127.0.0.1")

    # Point agent + judge routers at HF unless already set to a non-loopback URL.
    agent_default = (not prev_agent) or any(h in prev_agent for h in localhostish)
    if agent_default:
        os.environ.setdefault("VLLM_BASE", base)

    judge_default = (not prev_judge) or any(h in prev_judge for h in localhostish)
    if judge_default:
        os.environ.setdefault("JUDGE_URL", base)
