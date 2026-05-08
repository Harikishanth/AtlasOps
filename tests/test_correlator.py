"""Tests for incident correlator and dedup behavior."""

from agents.correlator import IncidentCorrelator


def _alert(alertname: str, namespace: str = "default", service: str = "frontend") -> dict:
    return {
        "commonLabels": {"alertname": alertname, "namespace": namespace, "service": service},
        "alerts": [{"labels": {"alertname": alertname, "service": service}}],
    }


def test_ingest_creates_new_incident():
    c = IncidentCorrelator()
    incident_id, is_new, should_dispatch = c.ingest(_alert("HighCPU"))
    assert incident_id.startswith("inc-")
    assert is_new is True
    assert should_dispatch is True


def test_ingest_correlates_similar_alerts():
    c = IncidentCorrelator()
    inc1, _, _ = c.ingest(_alert("HighCPU", service="frontend"))
    inc2, is_new, _ = c.ingest(_alert("HighLatency", service="frontend"))
    assert inc1 == inc2
    assert is_new is False


def test_dedup_skips_dispatch_while_processing():
    c = IncidentCorrelator()
    inc, _, _ = c.ingest(_alert("HighCPU", service="frontend"))
    c.mark_processing(inc, True)
    _inc2, _is_new, should_dispatch = c.ingest(_alert("High5xx", service="frontend"))
    assert should_dispatch is False


def test_different_namespace_does_not_correlate():
    c = IncidentCorrelator()
    inc1, _, _ = c.ingest(_alert("HighCPU", namespace="prod-a"))
    inc2, is_new, _ = c.ingest(_alert("HighCPU", namespace="prod-b"))
    assert inc1 != inc2
    assert is_new is True
