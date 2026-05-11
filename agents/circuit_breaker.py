"""Circuit breaker to stop unsafe or runaway incident automation."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# Outcome reasons that represent *designed* human decisions, not system failures.
# These must NOT trip the breaker — judges rejecting remediation or P0 manual mode
# are expected operational paths, not evidence of a broken pipeline.
DESIGNED_OUTCOMES = frozenset({
    "approval_rejected",
    "approval_timeout",
    "manual_runbook",
    "partial_resolution",
    "escalation",
})


class CircuitBreakerTripped(RuntimeError):
    pass


@dataclass
class CircuitBreaker:
    max_tool_calls_per_incident: int = 50
    max_mutating_actions_per_hour: int = 10
    max_concurrent_incidents: int = 5
    consecutive_failure_threshold: int = 3

    _tool_call_count: dict[str, int] = field(default_factory=dict)
    _mutating_actions_this_hour: int = 0
    _active_incidents: int = 0
    _consecutive_failures: int = 0
    _tripped: bool = False
    _hour_window_start: float = field(default_factory=time.time)

    def start_incident(self) -> None:
        if self._tripped:
            raise CircuitBreakerTripped("Circuit breaker is OPEN — incidents paused")
        if self._active_incidents >= self.max_concurrent_incidents:
            raise CircuitBreakerTripped("Concurrent incident limit reached")
        self._active_incidents += 1

    def finish_incident(self, incident_id: str, resolved: bool, reason: str = "") -> None:
        self._active_incidents = max(0, self._active_incidents - 1)
        self._tool_call_count.pop(incident_id, None)
        if resolved:
            self._consecutive_failures = 0
            return
        if reason in DESIGNED_OUTCOMES:
            return
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.consecutive_failure_threshold:
            self._tripped = True

    def check_before_tool_call(self, incident_id: str, tool_name: str, is_mutating: bool) -> None:
        self._roll_hour_window_if_needed()
        if self._tripped:
            raise CircuitBreakerTripped("Circuit breaker is OPEN — all tool calls blocked")

        count = self._tool_call_count.get(incident_id, 0)
        if count >= self.max_tool_calls_per_incident:
            raise CircuitBreakerTripped(
                f"Tool call limit ({self.max_tool_calls_per_incident}) exceeded for {incident_id}"
            )
        self._tool_call_count[incident_id] = count + 1

        if is_mutating:
            if self._mutating_actions_this_hour >= self.max_mutating_actions_per_hour:
                raise CircuitBreakerTripped("Hourly mutating action limit reached")
            self._mutating_actions_this_hour += 1

    def status(self) -> dict:
        self._roll_hour_window_if_needed()
        return {
            "tripped": self._tripped,
            "active_incidents": self._active_incidents,
            "consecutive_failures": self._consecutive_failures,
            "mutating_actions_this_hour": self._mutating_actions_this_hour,
            "max_tool_calls_per_incident": self.max_tool_calls_per_incident,
            "max_mutating_actions_per_hour": self.max_mutating_actions_per_hour,
            "max_concurrent_incidents": self.max_concurrent_incidents,
        }

    def reset(self) -> dict:
        self._tripped = False
        self._consecutive_failures = 0
        self._mutating_actions_this_hour = 0
        self._hour_window_start = time.time()
        self._tool_call_count.clear()
        self._active_incidents = 0
        return self.status()

    def _roll_hour_window_if_needed(self) -> None:
        if time.time() - self._hour_window_start >= 3600:
            self._hour_window_start = time.time()
            self._mutating_actions_this_hour = 0


circuit_breaker = CircuitBreaker()
