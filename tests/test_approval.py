"""Tests for approval gate behavior."""

import asyncio


def test_approval_policy_mapping():
    from agents.approval import approval_mode_for_severity

    assert approval_mode_for_severity("P0") == "manual"
    assert approval_mode_for_severity("P1") == "approve"
    assert approval_mode_for_severity("P2") == "auto"
    assert approval_mode_for_severity("P3") == "auto"
    assert approval_mode_for_severity("UNKNOWN") == "approve"


def test_approval_gate_approve_roundtrip():
    from agents.approval import ApprovalGate

    gate = ApprovalGate(timeout_seconds=2)
    req = gate.request("inc-1", "P1", "rollback checkoutservice")
    cb = gate.callback(req.token, "approved", approved_by="hari")
    assert cb["ok"] is True
    result = asyncio.run(gate.wait_for_decision("inc-1"))
    assert result["status"] == "approved"
    assert result["approved_by"] == "hari"


def test_approval_gate_timeout():
    from agents.approval import ApprovalGate

    gate = ApprovalGate(timeout_seconds=1)
    gate.request("inc-timeout", "P1", "scale service")
    result = asyncio.run(gate.wait_for_decision("inc-timeout"))
    assert result["status"] == "timeout"


def test_approval_callback_rejects_unknown_token():
    from agents.approval import ApprovalGate

    gate = ApprovalGate(timeout_seconds=1)
    result = gate.callback("missing-token", "approved")
    assert result["ok"] is False
