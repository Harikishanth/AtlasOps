"""Tests for the adversarial scenario designer."""

import json
import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch


class TestWeaknessExtraction:
    def _episode(self, scenario_id="sf-001", resolved=False, tier="single_fault",
                 reasoning=0.3, correctness=0.4, efficiency=0.5):
        return {
            "scenario_id": scenario_id,
            "resolved": resolved,
            "tier": tier,
            "judge": {"reasoning": reasoning, "correctness": correctness, "efficiency": efficiency},
        }

    def test_extracts_dns_weakness(self):
        from agents.adversarial_designer import _extract_weaknesses
        history = [self._episode(scenario_id="sf-006-dns"), self._episode(scenario_id="sf-006-dns-2")]
        weaknesses = _extract_weaknesses(history)
        assert any("dns" in w.lower() for w in weaknesses)

    def test_extracts_poor_evidence_weakness(self):
        from agents.adversarial_designer import _extract_weaknesses
        history = [self._episode(reasoning=0.1, correctness=0.2) for _ in range(5)]
        weaknesses = _extract_weaknesses(history)
        assert any("evidence" in w.lower() for w in weaknesses)

    def test_resolved_episodes_not_counted(self):
        from agents.adversarial_designer import _extract_weaknesses
        history = [self._episode(resolved=True) for _ in range(10)]
        weaknesses = _extract_weaknesses(history)
        assert len(weaknesses) == 0

    def test_returns_top_3_max(self):
        from agents.adversarial_designer import _extract_weaknesses
        history = [
            self._episode(scenario_id="dns-1"),
            self._episode(scenario_id="network-1"),
            self._episode(scenario_id="cascade-1", tier="cascade"),
            self._episode(reasoning=0.1, correctness=0.1),
        ]
        weaknesses = _extract_weaknesses(history)
        assert len(weaknesses) <= 3


class TestFaultToYaml:
    def test_podchaos_yaml(self):
        from agents.adversarial_designer import _fault_to_yaml
        fault = {"kind": "PodChaos", "action": "pod-kill", "target_service": "frontend", "params": {}}
        yaml = _fault_to_yaml(fault, "adv-test-001", 0)
        assert "PodChaos" in yaml
        assert "pod-kill" in yaml
        assert "frontend" in yaml
        assert "adv-test-001" in yaml

    def test_networkchaos_delay_yaml(self):
        from agents.adversarial_designer import _fault_to_yaml
        fault = {"kind": "NetworkChaos", "action": "delay",
                 "target_service": "checkoutservice", "params": {"latency": "2000ms"}}
        yaml = _fault_to_yaml(fault, "adv-delay", 0)
        assert "NetworkChaos" in yaml
        assert "2000ms" in yaml

    def test_stresschaos_cpu_yaml(self):
        from agents.adversarial_designer import _fault_to_yaml
        fault = {"kind": "StressChaos", "action": "cpu",
                 "target_service": "paymentservice", "params": {"workers": 4, "load": 90}}
        yaml = _fault_to_yaml(fault, "adv-stress", 0)
        assert "StressChaos" in yaml
        assert "workers: 4" in yaml

    def test_dnschaos_yaml(self):
        from agents.adversarial_designer import _fault_to_yaml
        fault = {"kind": "DNSChaos", "action": "error",
                 "target_service": "frontend", "params": {}}
        yaml = _fault_to_yaml(fault, "adv-dns", 0)
        assert "DNSChaos" in yaml
        assert "*.default.svc.cluster.local." in yaml

    def test_yaml_has_no_deprecated_scheduler(self):
        from agents.adversarial_designer import _fault_to_yaml
        fault = {"kind": "PodChaos", "action": "pod-kill",
                 "target_service": "frontend", "params": {}}
        yaml = _fault_to_yaml(fault, "adv-test", 0)
        assert "scheduler" not in yaml


class TestDesignScenario:
    def test_fallback_on_judge_failure(self, tmp_path, monkeypatch):
        from agents.adversarial_designer import design_scenario
        monkeypatch.setattr("agents.adversarial_designer.ADVERSARIAL_DIR", tmp_path)

        with patch("agents.adversarial_designer._call_judge",
                   new_callable=AsyncMock, return_value="not valid json at all"):
            result = asyncio.run(design_scenario([]))

        assert "scenario_id" in result
        assert "manifest_path" in result
        assert Path(result["manifest_path"]).exists()

    def test_writes_yaml_and_json(self, tmp_path, monkeypatch):
        from agents.adversarial_designer import design_scenario
        monkeypatch.setattr("agents.adversarial_designer.ADVERSARIAL_DIR", tmp_path)

        mock_spec = json.dumps({
            "scenario_id": "adv-unit-test-001",
            "title": "Unit test scenario",
            "difficulty": "hard",
            "faults": [
                {"kind": "PodChaos", "action": "pod-kill",
                 "target_service": "cartservice", "params": {}}
            ],
        })
        with patch("agents.adversarial_designer._call_judge",
                   new_callable=AsyncMock, return_value=mock_spec):
            result = asyncio.run(design_scenario([]))

        assert (tmp_path / "adv-unit-test-001.yaml").exists()
        assert (tmp_path / "adv-unit-test-001.json").exists()
        meta = json.loads((tmp_path / "adv-unit-test-001.json").read_text())
        assert meta["scenario_id"] == "adv-unit-test-001"
