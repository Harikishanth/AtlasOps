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


def test_hf_pack_auto_on_space_when_loopback(monkeypatch):
    """Without manual ATLASOPS_USE_HF_INFERENCE, Space + token + localhost routes to HF."""
    monkeypatch.setenv("HF_TOKEN", "hf_test_dummy")
    monkeypatch.delenv("ATLASOPS_USE_HF_INFERENCE", raising=False)
    monkeypatch.setenv("SPACE_AUTHOR_NAME", "lablab-ai-amd-developer-hackathon")
    monkeypatch.setenv("VLLM_BASE", "http://localhost:8000/v1")
    monkeypatch.setenv("JUDGE_URL", "http://127.0.0.1:8001/v1")

    import config.hf_space_env as hf

    importlib.reload(hf)
    hf.apply_hf_space_inference_defaults()

    import os

    assert os.environ.get("ATLASOPS_USE_HF_INFERENCE") == "1"
    assert os.environ["VLLM_BASE"].startswith("https://router.huggingface.co")
    assert os.environ["JUDGE_URL"].startswith("https://router.huggingface.co")


def test_hf_pack_auto_disabled_explicit_off(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_test_dummy")
    monkeypatch.setenv("ATLASOPS_USE_HF_INFERENCE", "0")
    monkeypatch.setenv("SPACE_AUTHOR_NAME", "x")
    monkeypatch.delenv("VLLM_BASE", raising=False)

    import config.hf_space_env as hf

    importlib.reload(hf)
    hf.apply_hf_space_inference_defaults()

    import os

    assert "VLLM_BASE" not in os.environ or not os.environ["VLLM_BASE"].startswith("https://router")


def test_hf_pack_auto_respects_custom_remote_on_space(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_test_dummy")
    monkeypatch.delenv("ATLASOPS_USE_HF_INFERENCE", raising=False)
    monkeypatch.setenv("SPACE_AUTHOR_NAME", "x")
    monkeypatch.setenv("VLLM_BASE", "https://my-mi300x.example.com:8000/v1")
    monkeypatch.setenv("JUDGE_URL", "https://my-mi300x.example.com:8001/v1")

    import config.hf_space_env as hf

    importlib.reload(hf)
    hf.apply_hf_space_inference_defaults()

    import os

    assert os.environ["VLLM_BASE"] == "https://my-mi300x.example.com:8000/v1"
    assert os.environ.get("ATLASOPS_USE_HF_INFERENCE", "") != "1"
