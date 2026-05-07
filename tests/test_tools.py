"""Unit tests for AtlasOps tool wrappers."""

import json
from unittest.mock import MagicMock, patch

import pytest


# ── kubectl tools ──────────────────────────────────────────────────────────────

class TestKubectlGet:
    def test_returns_dict_on_success(self):
        from agents.tools.kubectl import kubectl_get
        mock_result = MagicMock(returncode=0, stdout='{"items":[]}', stderr="")
        with patch("subprocess.run", return_value=mock_result):
            result = kubectl_get("pods")
        assert result["success"] is True
        assert "parsed" in result

    def test_returns_failure_on_nonzero(self):
        from agents.tools.kubectl import kubectl_get
        mock_result = MagicMock(returncode=1, stdout="", stderr="connection refused")
        with patch("subprocess.run", return_value=mock_result):
            result = kubectl_get("pods")
        assert result["success"] is False

    def test_namespace_flag_all(self):
        from agents.tools.kubectl import kubectl_get
        mock_result = MagicMock(returncode=0, stdout='{"items":[]}', stderr="")
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            kubectl_get("pods", namespace="-A")
        cmd = mock_run.call_args[0][0]
        assert "-A" in cmd

    def test_namespace_flag_specific(self):
        from agents.tools.kubectl import kubectl_get
        mock_result = MagicMock(returncode=0, stdout='{"items":[]}', stderr="")
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            kubectl_get("pods", namespace="default")
        cmd = mock_run.call_args[0][0]
        assert "-n" in cmd and "default" in cmd


class TestKubectlScale:
    def test_valid_replicas(self):
        from agents.tools.kubectl import kubectl_scale
        mock_result = MagicMock(returncode=0, stdout="scaled", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            result = kubectl_scale("frontend", 3)
        assert result["success"] is True

    def test_rejects_negative_replicas(self):
        from agents.tools.kubectl import kubectl_scale
        result = kubectl_scale("frontend", -1)
        assert result["success"] is False

    def test_rejects_too_many_replicas(self):
        from agents.tools.kubectl import kubectl_scale
        result = kubectl_scale("frontend", 99)
        assert result["success"] is False


class TestKubectlExec:
    def test_allowlisted_command_passes(self):
        from agents.tools.kubectl import kubectl_exec
        mock_result = MagicMock(returncode=0, stdout="output", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            result = kubectl_exec("mypod", ["ls", "/tmp"])
        assert result["success"] is True

    def test_non_allowlisted_command_blocked(self):
        from agents.tools.kubectl import kubectl_exec
        result = kubectl_exec("mypod", ["rm", "-rf", "/"])
        assert result["success"] is False
        assert "allowlist" in result["error"]

    def test_empty_command_blocked(self):
        from agents.tools.kubectl import kubectl_exec
        result = kubectl_exec("mypod", [])
        assert result["success"] is False


# ── Prometheus tools ───────────────────────────────────────────────────────────

class TestPromQL:
    def test_successful_query(self):
        from agents.tools.prometheus import promql_query
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {"resultType": "vector", "result": [{"metric": {}, "value": [1, "0.5"]}]},
        }
        with patch("requests.get", return_value=mock_response):
            result = promql_query("up")
        assert result["success"] is True
        assert len(result["result"]) == 1

    def test_prometheus_error_response(self):
        from agents.tools.prometheus import promql_query
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"status": "error", "error": "bad_data"}
        with patch("requests.get", return_value=mock_response):
            result = promql_query("invalid{}")
        assert result["success"] is False

    def test_connection_error(self):
        from agents.tools.prometheus import promql_query
        import requests as req
        with patch("requests.get", side_effect=req.exceptions.ConnectionError("refused")):
            result = promql_query("up")
        assert result["success"] is False
        assert "error" in result


# ── Alertmanager tools ─────────────────────────────────────────────────────────

class TestAlertmanager:
    def test_silence_valid_matchers(self):
        from agents.tools.alertmanager import alertmanager_silence
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"silenceID": "abc-123"}
        with patch("requests.post", return_value=mock_response):
            result = alertmanager_silence(
                matchers=[{"name": "alertname", "value": "HighCPU", "isRegex": False}],
                duration_minutes=30,
            )
        assert result["success"] is True
        assert result["silence_id"] == "abc-123"

    def test_silence_returns_ends_at(self):
        from agents.tools.alertmanager import alertmanager_silence
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"silenceID": "xyz"}
        with patch("requests.post", return_value=mock_response):
            result = alertmanager_silence(
                matchers=[{"name": "alertname", "value": "Test", "isRegex": False}]
            )
        assert "ends_at" in result

    def test_list_alerts_success(self):
        from agents.tools.alertmanager import alertmanager_list_alerts
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [
            {"labels": {"alertname": "HighCPU", "severity": "critical", "namespace": "default"},
             "status": {"state": "firing"}, "startsAt": "2026-05-07T00:00:00Z"}
        ]
        with patch("requests.get", return_value=mock_response):
            result = alertmanager_list_alerts()
        assert result["success"] is True
        assert result["count"] == 1
        assert result["alerts"][0]["alertname"] == "HighCPU"


# ── Comms tools ────────────────────────────────────────────────────────────────

class TestSlackPost:
    def test_logs_locally_when_no_webhook(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "")
        monkeypatch.setenv("POSTMORTEM_DIR", str(tmp_path))
        import agents.tools.comms as comms_mod
        monkeypatch.setattr(comms_mod, "SLACK_WEBHOOK", "")
        from agents.tools.comms import slack_post_update
        import importlib
        result = slack_post_update(
            channel="#incidents", severity="P1",
            title="Test incident", summary="Something broke"
        )
        assert result["success"] is True
        assert result["mode"] == "logged_locally"

    def test_postmortem_draft_creates_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("POSTMORTEM_DIR", str(tmp_path))
        import agents.tools.comms as comms_mod
        from pathlib import Path
        monkeypatch.setattr(comms_mod, "POSTMORTEM_DIR", tmp_path)
        from agents.tools.comms import postmortem_draft
        incident = {
            "title": "Test Incident",
            "severity": "P1",
            "duration": "5m",
            "authors": "AtlasOps",
            "summary": "Test summary",
            "impact": "Minor",
            "timeline": [{"time": "00:01", "event": "alert fired"}],
            "root_cause": "CPU saturation",
            "detection": "Prometheus alert",
            "resolution": "Scaled up",
            "went_well": ["Fast detection"],
            "went_wrong": ["Slow response"],
            "action_items": [{"action": "Add alert", "owner": "@team", "priority": "P2", "due": "2026-06-01"}],
        }
        result = postmortem_draft(incident, output_path=str(tmp_path / "test.md"))
        assert result["success"] is True
        assert (tmp_path / "test.md").exists()
        content = (tmp_path / "test.md").read_text()
        assert "Test Incident" in content


# ── Jaeger tools ───────────────────────────────────────────────────────────────

class TestJaeger:
    def test_search_returns_traces(self):
        from agents.tools.jaeger import jaeger_search
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"traceID": "abc123", "spans": [{"duration": 1500000, "operationName": "/cart"}]},
            ]
        }
        with patch("requests.get", return_value=mock_response):
            result = jaeger_search("cartservice")
        assert result["success"] is True
        assert result["count"] == 1
        assert result["traces"][0]["traceID"] == "abc123"

    def test_get_trace_by_id(self):
        from agents.tools.jaeger import jaeger_get_trace
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"data": [{"traceID": "abc123", "spans": []}]}
        with patch("requests.get", return_value=mock_response):
            result = jaeger_get_trace("abc123")
        assert result["success"] is True

    def test_lookback_parser(self):
        from agents.tools.jaeger import _parse_lookback_to_us
        assert _parse_lookback_to_us("15m") == 15 * 60 * 1_000_000
        assert _parse_lookback_to_us("1h") == 3_600_000_000
        assert _parse_lookback_to_us("30s") == 30_000_000


# ── Stream (thought emission) ──────────────────────────────────────────────────

class TestThoughtStream:
    def test_emit_stores_in_buffer(self):
        from agents.stream import emit, get_history, _thought_buffer
        _thought_buffer.clear()
        emit("triage", "tool_call", "Checking pods...", tool="kubectl_get")
        history = get_history()
        assert len(history) == 1
        assert history[0]["role"] == "triage"
        assert history[0]["thought"] == "Checking pods..."

    def test_emit_multiple_roles(self):
        from agents.stream import emit, get_history, _thought_buffer
        _thought_buffer.clear()
        emit("triage", "conclusion", "P1 assigned")
        emit("diagnosis", "tool_call", "Querying Prometheus")
        emit("remediation", "tool_result", "Rollback executed")
        history = get_history()
        assert len(history) == 3
        roles = [h["role"] for h in history]
        assert roles == ["triage", "diagnosis", "remediation"]

    def test_buffer_max_size(self):
        from agents.stream import emit, get_history, _thought_buffer
        _thought_buffer.clear()
        for i in range(250):
            emit("triage", "thinking", f"thought {i}")
        history = get_history()
        assert len(history) == 200  # maxlen=200
