"""Tests for coordinator routing and tool narration."""

import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestToolNarration:
    def test_narrate_kubectl_get(self):
        from agents.coordinator import _narrate_tool_call
        result = _narrate_tool_call("triage", "kubectl_get", {"resource": "pods"})
        assert "pods" in result.lower() or "cluster" in result.lower()

    def test_narrate_promql(self):
        from agents.coordinator import _narrate_tool_call
        result = _narrate_tool_call("diagnosis", "promql_query", {"query": "rate(http_requests[1m])"})
        assert "prometheus" in result.lower() or "querying" in result.lower()

    def test_narrate_argocd_rollback(self):
        from agents.coordinator import _narrate_tool_call
        result = _narrate_tool_call("remediation", "argocd_rollback",
                                    {"app": "frontend", "revision": "2"})
        assert "rollback" in result.lower() or "frontend" in result.lower()

    def test_narrate_unknown_tool(self):
        from agents.coordinator import _narrate_tool_call
        result = _narrate_tool_call("triage", "unknown_tool_xyz", {})
        assert "unknown_tool_xyz" in result

    def test_narrate_tool_result_success(self):
        from agents.coordinator import _narrate_tool_result
        result = _narrate_tool_result("kubectl_get", {"success": True, "items": []})
        assert isinstance(result, str) and len(result) > 0

    def test_narrate_tool_result_failure(self):
        from agents.coordinator import _narrate_tool_result
        result = _narrate_tool_result("kubectl_get", {"success": False, "error": "timeout"})
        assert "⚠️" in result or "error" in result.lower()

    def test_conclusion_summaries(self):
        from agents.coordinator import _summarise_conclusion
        for role in ("triage", "diagnosis", "remediation", "comms"):
            result = _summarise_conclusion(role, "some json output")
            assert isinstance(result, str) and len(result) > 10


class TestJsonParsing:
    def test_parse_clean_json(self):
        from agents.coordinator import _try_parse_json
        content = '{"severity": "P1", "next_agent": "diagnosis"}'
        result = _try_parse_json(content)
        assert result["severity"] == "P1"

    def test_parse_json_with_preamble(self):
        from agents.coordinator import _try_parse_json
        content = 'Here is my analysis:\n\n{"severity": "P1"}\n\nDone.'
        result = _try_parse_json(content)
        assert result["severity"] == "P1"

    def test_parse_empty_returns_empty_dict(self):
        from agents.coordinator import _try_parse_json
        result = _try_parse_json("")
        assert result == {}

    def test_parse_invalid_json_returns_raw(self):
        from agents.coordinator import _try_parse_json
        result = _try_parse_json("not json at all")
        assert "raw" in result


class TestBackendConfig:
    def test_vllm_defaults(self, monkeypatch):
        monkeypatch.setenv("BACKEND", "vllm")
        import importlib
        import agents.coordinator as coord
        importlib.reload(coord)
        assert "localhost" in coord.VLLM_BASE or "8000" in coord.VLLM_BASE

    def test_fireworks_defaults(self, monkeypatch):
        monkeypatch.setenv("BACKEND", "fireworks")
        import importlib
        import agents.coordinator as coord
        importlib.reload(coord)
        assert "fireworks" in coord.VLLM_BASE

    def test_api_key_empty_by_default(self, monkeypatch):
        monkeypatch.setenv("BACKEND", "vllm")
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        import importlib
        import agents.coordinator as coord
        importlib.reload(coord)
        assert coord.API_KEY == ""


class TestApprovalFlow:
    @pytest.fixture(autouse=True)
    def _disable_live_judge(self, monkeypatch):
        monkeypatch.setenv("ATLASOPS_LIVE_JUDGE", "0")
        monkeypatch.setenv("ATLASOPS_USE_HF_INFERENCE", "0")

    def test_manual_mode_skips_remediation_agent(self, monkeypatch):
        import agents.coordinator as coord

        triage = {"role": "triage", "trajectory": [], "final": {"severity": "P0"}}
        diagnosis = {"role": "diagnosis", "trajectory": [], "final": {"root_cause": "cpu spike"}}
        comms = {"role": "comms", "trajectory": [], "final": {"status": "posted"}}
        mock_call = AsyncMock(side_effect=[triage, diagnosis, comms])
        monkeypatch.setattr(coord, "call_agent", mock_call)

        result = asyncio.run(coord.handle_incident({"commonLabels": {"alertname": "TestAlert"}}))
        assert result["remediation"]["final"]["mode"] == "manual"
        roles = [c.args[0] for c in mock_call.call_args_list]
        assert roles == ["triage", "diagnosis", "comms"]

    def test_approve_mode_rejected_skips_remediation_execution(self, monkeypatch):
        import agents.coordinator as coord

        triage = {"role": "triage", "trajectory": [], "final": {"severity": "P1"}}
        diagnosis = {"role": "diagnosis", "trajectory": [], "final": {"root_cause": "bad deploy"}}
        comms = {"role": "comms", "trajectory": [], "final": {"status": "posted"}}
        mock_call = AsyncMock(side_effect=[triage, diagnosis, comms])
        monkeypatch.setattr(coord, "call_agent", mock_call)

        async def fake_wait(_incident_id):
            return {"status": "rejected", "approved_by": "oncall", "reason": "needs more evidence"}

        monkeypatch.setattr(coord.approval_gate, "wait_for_decision", fake_wait)

        result = asyncio.run(coord.handle_incident({"commonLabels": {"alertname": "TestAlert"}}))
        assert result["remediation"]["final"]["status"] == "approval_rejected"
        roles = [c.args[0] for c in mock_call.call_args_list]
        assert roles == ["triage", "diagnosis", "comms"]
