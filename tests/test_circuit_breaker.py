"""Tests for circuit breaker behavior."""

import pytest


def test_tool_call_limit_trips_for_incident():
    from agents.circuit_breaker import CircuitBreaker, CircuitBreakerTripped

    cb = CircuitBreaker(max_tool_calls_per_incident=2)
    cb.start_incident()
    cb.check_before_tool_call("inc-1", "kubectl_get", is_mutating=False)
    cb.check_before_tool_call("inc-1", "kubectl_get", is_mutating=False)
    with pytest.raises(CircuitBreakerTripped):
        cb.check_before_tool_call("inc-1", "kubectl_get", is_mutating=False)
    cb.finish_incident("inc-1", resolved=True)


def test_mutating_action_hourly_limit():
    from agents.circuit_breaker import CircuitBreaker, CircuitBreakerTripped

    cb = CircuitBreaker(max_mutating_actions_per_hour=1)
    cb.start_incident()
    cb.check_before_tool_call("inc-2", "kubectl_scale", is_mutating=True)
    with pytest.raises(CircuitBreakerTripped):
        cb.check_before_tool_call("inc-2", "kubectl_scale", is_mutating=True)
    cb.finish_incident("inc-2", resolved=True)


def test_consecutive_system_errors_trip_breaker():
    from agents.circuit_breaker import CircuitBreaker, CircuitBreakerTripped

    cb = CircuitBreaker(consecutive_failure_threshold=2)
    cb.start_incident()
    cb.finish_incident("inc-a", resolved=False, reason="system_error")
    cb.start_incident()
    cb.finish_incident("inc-b", resolved=False, reason="system_error")
    with pytest.raises(CircuitBreakerTripped):
        cb.start_incident()


def test_approval_rejected_does_not_trip_breaker():
    """Judges rejecting remediation is a designed outcome, not a system failure."""
    from agents.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker(consecutive_failure_threshold=2)
    for i in range(5):
        cb.start_incident()
        cb.finish_incident(f"inc-rej-{i}", resolved=False, reason="approval_rejected")
    assert cb.status()["tripped"] is False
    assert cb.status()["consecutive_failures"] == 0


def test_manual_runbook_does_not_trip_breaker():
    from agents.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker(consecutive_failure_threshold=2)
    for i in range(5):
        cb.start_incident()
        cb.finish_incident(f"inc-man-{i}", resolved=False, reason="manual_runbook")
    assert cb.status()["tripped"] is False


def test_approval_timeout_does_not_trip_breaker():
    from agents.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker(consecutive_failure_threshold=2)
    for i in range(5):
        cb.start_incident()
        cb.finish_incident(f"inc-to-{i}", resolved=False, reason="approval_timeout")
    assert cb.status()["tripped"] is False


def test_unresolved_without_reason_still_trips():
    """Plain unresolved (no reason) should trip the breaker for backward compat."""
    from agents.circuit_breaker import CircuitBreaker, CircuitBreakerTripped

    cb = CircuitBreaker(consecutive_failure_threshold=2)
    cb.start_incident()
    cb.finish_incident("inc-x", resolved=False)
    cb.start_incident()
    cb.finish_incident("inc-y", resolved=False)
    with pytest.raises(CircuitBreakerTripped):
        cb.start_incident()


def test_reset_clears_tripped_state():
    from agents.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker(consecutive_failure_threshold=1)
    cb.start_incident()
    cb.finish_incident("inc-c", resolved=False, reason="system_error")
    assert cb.status()["tripped"] is True
    status = cb.reset()
    assert status["tripped"] is False
    assert status["active_incidents"] == 0


def test_resolved_resets_consecutive_failures():
    from agents.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker(consecutive_failure_threshold=3)
    cb.start_incident()
    cb.finish_incident("inc-1", resolved=False, reason="system_error")
    cb.start_incident()
    cb.finish_incident("inc-2", resolved=False, reason="system_error")
    assert cb.status()["consecutive_failures"] == 2
    cb.start_incident()
    cb.finish_incident("inc-3", resolved=True)
    assert cb.status()["consecutive_failures"] == 0
