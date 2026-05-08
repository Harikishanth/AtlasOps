"""Incident correlation and deduplication for alert storms."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CorrelatedIncident:
    incident_id: str
    created_at: float
    namespace: str
    services: set[str] = field(default_factory=set)
    alert_names: set[str] = field(default_factory=set)
    alerts: list[dict[str, Any]] = field(default_factory=list)
    active_processing: bool = False
    last_alert_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "created_at": self.created_at,
            "namespace": self.namespace,
            "services": sorted(self.services),
            "alert_names": sorted(self.alert_names),
            "alert_count": len(self.alerts),
            "active_processing": self.active_processing,
            "last_alert_at": self.last_alert_at,
        }


class IncidentCorrelator:
    CORRELATION_WINDOW_S = 300

    def __init__(self):
        self._incidents: dict[str, CorrelatedIncident] = {}

    def ingest(self, alert: dict[str, Any]) -> tuple[str, bool, bool]:
        """Return (incident_id, is_new_incident, should_dispatch_chain)."""
        now = time.time()
        self._expire_old(now)

        namespace = self._extract_namespace(alert)
        services = self._extract_services(alert)
        alert_names = self._extract_alert_names(alert)

        for inc in self._incidents.values():
            if self._should_correlate(now, namespace, services, alert_names, inc):
                inc.alerts.append(alert)
                inc.alert_names.update(alert_names)
                inc.services.update(services)
                inc.last_alert_at = now
                should_dispatch = not inc.active_processing
                return inc.incident_id, False, should_dispatch

        incident_id = f"inc-{int(now)}-{uuid.uuid4().hex[:6]}"
        inc = CorrelatedIncident(
            incident_id=incident_id,
            created_at=now,
            namespace=namespace,
            services=set(services),
            alert_names=set(alert_names),
            alerts=[alert],
            active_processing=False,
            last_alert_at=now,
        )
        self._incidents[incident_id] = inc
        return incident_id, True, True

    def mark_processing(self, incident_id: str, active: bool) -> None:
        inc = self._incidents.get(incident_id)
        if inc:
            inc.active_processing = active

    def get_active(self) -> list[dict[str, Any]]:
        now = time.time()
        self._expire_old(now)
        return [inc.to_dict() for inc in self._incidents.values()]

    def _should_correlate(
        self,
        now: float,
        namespace: str,
        services: set[str],
        alert_names: set[str],
        incident: CorrelatedIncident,
    ) -> bool:
        if now - incident.created_at > self.CORRELATION_WINDOW_S:
            return False
        if namespace and incident.namespace and namespace != incident.namespace:
            return False
        if services and incident.services and services.isdisjoint(incident.services):
            return False
        if alert_names and incident.alert_names and alert_names.intersection(incident.alert_names):
            return True
        return bool(services and incident.services)

    def _expire_old(self, now: float) -> None:
        stale = [
            inc_id
            for inc_id, inc in self._incidents.items()
            if (now - inc.last_alert_at > self.CORRELATION_WINDOW_S and not inc.active_processing)
        ]
        for inc_id in stale:
            self._incidents.pop(inc_id, None)

    @staticmethod
    def _extract_namespace(alert: dict[str, Any]) -> str:
        labels = alert.get("commonLabels", {}) if isinstance(alert, dict) else {}
        return str(labels.get("namespace", "")).strip()

    @staticmethod
    def _extract_services(alert: dict[str, Any]) -> set[str]:
        labels = alert.get("commonLabels", {}) if isinstance(alert, dict) else {}
        services = {
            str(labels.get("service", "")).strip(),
            str(labels.get("app", "")).strip(),
            str(labels.get("deployment", "")).strip(),
        }
        services.update(
            str(a.get("labels", {}).get("service", "")).strip()
            for a in alert.get("alerts", [])
            if isinstance(a, dict)
        )
        return {s for s in services if s}

    @staticmethod
    def _extract_alert_names(alert: dict[str, Any]) -> set[str]:
        names = set()
        labels = alert.get("commonLabels", {}) if isinstance(alert, dict) else {}
        common = str(labels.get("alertname", "")).strip()
        if common:
            names.add(common)
        for a in alert.get("alerts", []):
            if isinstance(a, dict):
                name = str(a.get("labels", {}).get("alertname", "")).strip()
                if name:
                    names.add(name)
        return names


correlator = IncidentCorrelator()
