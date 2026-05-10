"""Human-in-the-loop approval gate for remediation actions."""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


APPROVAL_POLICY = {
    "P0": "manual",
    "P1": "approve",
    "P2": "auto",
    "P3": "auto",
}


def approval_mode_for_severity(severity: str) -> str:
    return APPROVAL_POLICY.get(str(severity).upper(), "approve")


@dataclass
class ApprovalRequest:
    incident_id: str
    severity: str
    summary: str
    token: str = field(default_factory=lambda: f"apr-{uuid.uuid4().hex[:12]}")
    created_at: float = field(default_factory=time.time)
    decision: str = "pending"
    approved_by: str = ""
    reason: str = ""
    event: asyncio.Event = field(default_factory=asyncio.Event)

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "severity": self.severity,
            "summary": self.summary,
            "token": self.token,
            "created_at": self.created_at,
            "decision": self.decision,
            "approved_by": self.approved_by,
            "reason": self.reason,
        }


class ApprovalGate:
    def __init__(self, timeout_seconds: int | None = None):
        # Default 300s so humans can intervene during demos.
        # Override via APPROVAL_TIMEOUT_SECONDS as needed.
        self.timeout_seconds = timeout_seconds or int(os.getenv("APPROVAL_TIMEOUT_SECONDS", "300"))
        self._pending_by_incident: dict[str, ApprovalRequest] = {}
        self._pending_by_token: dict[str, ApprovalRequest] = {}

    def request(self, incident_id: str, severity: str, summary: str) -> ApprovalRequest:
        req = ApprovalRequest(incident_id=incident_id, severity=severity, summary=summary)
        self._pending_by_incident[incident_id] = req
        self._pending_by_token[req.token] = req
        return req

    async def wait_for_decision(self, incident_id: str) -> dict[str, Any]:
        req = self._pending_by_incident.get(incident_id)
        if not req:
            return {"status": "missing", "incident_id": incident_id}
        try:
            await asyncio.wait_for(req.event.wait(), timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            req.decision = "timeout"
            self._clear(req)
            return {"status": "timeout", "incident_id": incident_id}
        result = {
            "status": req.decision,
            "incident_id": req.incident_id,
            "approved_by": req.approved_by,
            "reason": req.reason,
        }
        self._clear(req)
        return result

    def callback(self, token: str, decision: str, approved_by: str = "", reason: str = "") -> dict[str, Any]:
        req = self._pending_by_token.get(token)
        if not req:
            return {"ok": False, "error": "unknown_token"}
        normalized = decision.lower().strip()
        if normalized not in {"approved", "rejected"}:
            return {"ok": False, "error": "decision must be approved or rejected"}
        req.decision = normalized
        req.approved_by = approved_by
        req.reason = reason
        req.event.set()
        return {"ok": True, "incident_id": req.incident_id, "decision": normalized}

    def pending(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self._pending_by_incident.values()]

    def _clear(self, req: ApprovalRequest) -> None:
        self._pending_by_incident.pop(req.incident_id, None)
        self._pending_by_token.pop(req.token, None)


approval_gate = ApprovalGate()
