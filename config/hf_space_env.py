"""Hugging Face Space defaults for AtlasOps inference.

Spaces usually provide `HF_TOKEN` (read / inference). This module maps that onto
OpenAI-compatible calls for both agents (7B) and judge (72B).

Explicit enable (Secrets):
    ATLASOPS_USE_HF_INFERENCE=1

Automatic rescue (typical submission hazard): when running **inside a HF Space**
(`SPACE_AUTHOR_NAME` etc.), **`HF_TOKEN` is set**, and `VLLM_BASE` / `JUDGE_URL`
still point at **localhost**, we route to the HF Inference Router — otherwise the
coordinator blocks forever calling `http://localhost:8000` inside the container.

Opt out of auto-routing:
    ATLASOPS_AUTO_HF_INFERENCE=0

Hard-disable HF routing entirely (use only your reachable self-hosted URL):
    ATLASOPS_USE_HF_INFERENCE=0

Optional overrides:
    HF_INFERENCE_BASE=https://router.huggingface.co/v1
"""

from __future__ import annotations

import logging
import os

_log = logging.getLogger("atlasops.hf_space_env")


def _running_on_hf_space() -> bool:
    """True inside Hugging Face Spaces Docker (built-in env markers)."""
    return bool(
        os.getenv("SPACE_AUTHOR_NAME", "").strip()
        or os.getenv("SPACE_REPO_NAME", "").strip()
        or os.getenv("SPACE_ID", "").strip()
        or os.getenv("SYSTEM", "").strip().lower() == "space"
    )


def _localhost_or_empty(url: str) -> bool:
    u = (url or "").strip().lower()
    return (not u) or ("localhost" in u) or ("127.0.0.1" in u)


def apply_hf_space_inference_defaults() -> None:
    tok = (
        os.getenv("HF_TOKEN", "").strip()
        or os.getenv("HUGGING_FACE_HUB_TOKEN", "").strip()
    )
    if tok:
        os.environ.setdefault("LLM_API_KEY", tok)
        os.environ.setdefault("JUDGE_API_KEY", tok)

    hf_flag_raw = os.getenv("ATLASOPS_USE_HF_INFERENCE", "").strip().lower()
    if hf_flag_raw in ("0", "false", "no", "off"):
        return

    explicit_hf = hf_flag_raw in ("1", "true", "yes", "on")

    prev_agent = os.getenv("VLLM_BASE", "").strip()
    prev_judge = os.getenv("JUDGE_URL", "").strip()
    agent_loopback = _localhost_or_empty(prev_agent)
    judge_loopback = _localhost_or_empty(prev_judge)

    auto_opt_out = os.getenv("ATLASOPS_AUTO_HF_INFERENCE", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    )
    auto_hf = (
        not explicit_hf
        and not auto_opt_out
        and bool(tok)
        and _running_on_hf_space()
        and (agent_loopback or judge_loopback)
    )

    if not explicit_hf and not auto_hf:
        return

    base = os.getenv("HF_INFERENCE_BASE", "https://router.huggingface.co/v1").rstrip("/")

    os.environ.setdefault("BACKEND", "openai")

    # Replace loopback URLs — `setdefault` would wrongly keep localhost if already set.
    if agent_loopback:
        os.environ["VLLM_BASE"] = base
    if judge_loopback:
        os.environ["JUDGE_URL"] = base

    os.environ.setdefault("ATLASOPS_USE_HF_INFERENCE", "1")

    if auto_hf:
        _log.warning(
            "ATLASOPS: auto-routing LLM + judge to HF Inference Router (Space runtime + "
            "HF_TOKEN + loopback VLLM/JUDGE). "
            "Override with a reachable VLLM_BASE or ATLASOPS_AUTO_HF_INFERENCE=0."
        )
