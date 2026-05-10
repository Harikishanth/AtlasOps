"""Lightweight integration smoke tests for app.py endpoints.

These tests mock external side effects so they can run in CI without a cluster.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _client():
    from app import app
    return TestClient(app)


def test_health_endpoint_ok():
    client = _client()
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "model" in body
    assert "discord_webhook_configured" in body
    assert "slack_webhook_configured" in body


def test_inject_missing_manifest_returns_404():
    client = _client()
    r = client.post("/inject", json={"scenario_id": "does/not/exist"})
    assert r.status_code == 404
    assert r.json()["ok"] is False


@patch("app.subprocess.run")
@patch("app.Path.exists", return_value=True)
@patch("asyncio.create_task")
def test_inject_success_returns_correlation_id(mock_task, mock_exists, mock_run):
    # The endpoint constructs a coroutine before scheduling it; close it in the
    # mock so pytest doesn't report an un-awaited coroutine warning.
    mock_task.side_effect = lambda coro: coro.close()
    mock_run.return_value = MagicMock(returncode=0, stderr="")
    client = _client()
    r = client.post("/inject", json={"scenario_id": "single_fault/sf-001", "name": "Smoke"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["scenario_id"] == "single_fault/sf-001"
    assert body["correlation_id"].startswith("inj-")
    assert mock_task.called


@patch("app.subprocess.run")
def test_reset_returns_ok(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    client = _client()
    r = client.post("/reset")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_slack_feed_returns_recent_posts(tmp_path, monkeypatch):
    log_file = tmp_path / "data" / "slack_posts.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    posts = [{"a": 1}, {"b": 2}]
    log_file.write_text("\n".join(json.dumps(p) for p in posts), encoding="utf-8")

    # Ensure endpoint reads from temporary file path.
    monkeypatch.chdir(tmp_path)
    client = _client()
    r = client.get("/slack/feed")
    assert r.status_code == 200
    assert len(r.json()["posts"]) == 2


@patch("app.subprocess.run")
def test_cluster_health_handles_kubectl_failure(mock_run):
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")
    client = _client()
    r = client.get("/cluster/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert isinstance(body["services"], dict)


def test_approval_callback_and_pending_flow():
    from agents.approval import approval_gate

    req = approval_gate.request("inc-test-approval", "P1", "rollback checkoutservice")
    client = _client()
    pending = client.get("/approval/pending")
    assert pending.status_code == 200
    assert any(p["incident_id"] == "inc-test-approval" for p in pending.json()["pending"])

    cb = client.post(
        "/approval/callback",
        json={"token": req.token, "decision": "approved", "approved_by": "test-user"},
    )
    assert cb.status_code == 200
    assert cb.json()["ok"] is True


def test_approval_callback_unknown_token_400():
    client = _client()
    r = client.post("/approval/callback", json={"token": "missing", "decision": "approved"})
    assert r.status_code == 400


def test_circuit_breaker_status_and_reset():
    client = _client()
    s = client.get("/circuit-breaker/status")
    assert s.status_code == 200
    assert "tripped" in s.json()

    r = client.post("/circuit-breaker/reset")
    assert r.status_code == 200
    assert r.json()["tripped"] is False


def test_incidents_active_endpoint_returns_list():
    client = _client()
    r = client.get("/incidents/active")
    assert r.status_code == 200
    body = r.json()
    assert "incidents" in body
    assert isinstance(body["incidents"], list)


def test_audit_log_and_verify_endpoints():
    client = _client()
    l = client.get("/audit/log?limit=5")
    assert l.status_code == 200
    assert "entries" in l.json()
    v = client.get("/audit/verify")
    assert v.status_code == 200
    assert "ok" in v.json()

