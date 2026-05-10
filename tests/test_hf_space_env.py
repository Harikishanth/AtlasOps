import importlib

import pytest


def test_hf_pack_sets_router_and_token_chain(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_test_dummy")
    monkeypatch.setenv("ATLASOPS_USE_HF_INFERENCE", "1")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("JUDGE_API_KEY", raising=False)
    monkeypatch.delenv("VLLM_BASE", raising=False)
    monkeypatch.delenv("JUDGE_URL", raising=False)

    import config.hf_space_env as hf

    importlib.reload(hf)
    hf.apply_hf_space_inference_defaults()

    import os

    assert os.environ.get("LLM_API_KEY") == "hf_test_dummy"
    assert os.environ.get("JUDGE_API_KEY") == "hf_test_dummy"
    assert os.environ["VLLM_BASE"].startswith("https://")
    assert os.environ["JUDGE_URL"].startswith("https://")


def test_hf_pack_respects_custom_remote_url(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "tok")
    monkeypatch.setenv("ATLASOPS_USE_HF_INFERENCE", "1")
    monkeypatch.setenv("VLLM_BASE", "https://example.com/v1")
    monkeypatch.setenv("JUDGE_URL", "https://example-judge.com/v1")

    import config.hf_space_env as hf

    importlib.reload(hf)
    hf.apply_hf_space_inference_defaults()

    import os

    assert os.environ["VLLM_BASE"] == "https://example.com/v1"
    assert os.environ["JUDGE_URL"] == "https://example-judge.com/v1"
