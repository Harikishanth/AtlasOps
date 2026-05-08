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


def test_consecutive_failures_open_breaker():
    from agents.circuit_breaker import CircuitBreaker, CircuitBreakerTripped

    cb = CircuitBreaker(consecutive_failure_threshold=2)
    cb.start_incident()
    cb.finish_incident("inc-a", resolved=False)
    cb.start_incident()
    cb.finish_incident("inc-b", resolved=False)
    with pytest.raises(CircuitBreakerTripped):
        cb.start_incident()


def test_reset_clears_tripped_state():
    from agents.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker(consecutive_failure_threshold=1)
    cb.start_incident()
    cb.finish_incident("inc-c", resolved=False)
    assert cb.status()["tripped"] is True
    status = cb.reset()
    assert status["tripped"] is False
