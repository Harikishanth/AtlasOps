"""Tests for audit log append and verification."""

from pathlib import Path


def test_audit_log_record_and_verify(tmp_path):
    from agents.audit import AuditLog

    path = tmp_path / "audit.jsonl"
    log = AuditLog(secret_key="test-secret", log_path=path)
    log.record("inc-1", "triage", "tool_call", tool_name="kubectl_get", tool_args={"resource": "pods"})
    log.record("inc-1", "triage", "tool_result", result_summary="ok")
    verify = log.verify_integrity()
    assert verify["ok"] is True
    assert verify["entries"] == 2


def test_audit_verify_fails_on_tamper(tmp_path):
    from agents.audit import AuditLog

    path = tmp_path / "audit.jsonl"
    log = AuditLog(secret_key="test-secret", log_path=path)
    log.record("inc-2", "coordinator", "incident_start", result_summary="test")
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("incident_start", "incident_starx"), encoding="utf-8")
    verify = log.verify_integrity()
    assert verify["ok"] is False


def test_audit_tail_limit_and_offset(tmp_path):
    from agents.audit import AuditLog

    path = tmp_path / "audit.jsonl"
    log = AuditLog(secret_key="test-secret", log_path=path)
    for idx in range(5):
        log.record(f"inc-{idx}", "coordinator", "incident_start", result_summary=f"r{idx}")
    entries = log.tail(limit=2)
    assert len(entries) == 2
    shifted = log.tail(limit=10, offset=3)
    assert len(shifted) == 2
