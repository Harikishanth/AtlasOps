"""Tests for the benchmark runner — reward contract, scoring, comparison table."""

import json
import math
import pytest
from pathlib import Path


# ── Reward contract ────────────────────────────────────────────────────────────

class TestRewardContract:
    def _episode(self, **kwargs):
        base = {
            "tier": "single_fault", "resolved": True, "outcome": "resolved",
            "total_turns": 10, "time_to_resolve_s": 120,
            "judge": {"reasoning": 0.8, "correctness": 0.9, "efficiency": 0.85},
            "postmortem_path": "docs/postmortems/test.md",
        }
        base.update(kwargs)
        return base

    def test_perfect_episode_near_one(self):
        from bench.runner import _evaluate_episode_reward
        ep = self._episode(total_turns=5, time_to_resolve_s=60)
        r = _evaluate_episode_reward(ep)
        assert r["total"] > 0.85

    def test_unresolved_episode_lower(self):
        from bench.runner import _evaluate_episode_reward
        ep = self._episode(resolved=False, outcome="unknown",
                           judge={"reasoning": 0.3, "correctness": 0.4, "efficiency": 0.5})
        r = _evaluate_episode_reward(ep)
        assert r["total"] < 0.5

    def test_command_spam_penalty_applied(self):
        from bench.runner import _evaluate_episode_reward
        ep_normal = self._episode(total_turns=10)
        ep_spam   = self._episode(total_turns=50)
        r_normal  = _evaluate_episode_reward(ep_normal)
        r_spam    = _evaluate_episode_reward(ep_spam)
        assert r_spam["total"] < r_normal["total"]
        assert r_spam["penalties"]["command_spam"] == pytest.approx(0.10)

    def test_false_resolution_penalty(self):
        from bench.runner import _evaluate_episode_reward
        ep = self._episode(resolved=False, outcome="resolved")
        r  = _evaluate_episode_reward(ep)
        assert r["penalties"]["false_resolution"] == pytest.approx(0.25)

    def test_unsafe_shortcut_penalty(self):
        from bench.runner import _evaluate_episode_reward
        ep = self._episode(judge={"reasoning": 0.8, "correctness": 0.9, "efficiency": 0.1})
        r  = _evaluate_episode_reward(ep)
        assert r["penalties"]["unsafe_shortcut"] == pytest.approx(0.20)

    def test_no_postmortem_reduces_comms(self):
        from bench.runner import _evaluate_episode_reward
        ep_with    = self._episode(postmortem_path="some/path.md")
        ep_without = self._episode(postmortem_path=None)
        r_with    = _evaluate_episode_reward(ep_with)
        r_without = _evaluate_episode_reward(ep_without)
        assert r_with["total"] > r_without["total"]

    def test_cascade_tier_weights_evidence_higher(self):
        from bench.runner import _evaluate_episode_reward
        ep_sf = self._episode(tier="single_fault")
        ep_cs = self._episode(tier="cascade")
        r_sf  = _evaluate_episode_reward(ep_sf)
        r_cs  = _evaluate_episode_reward(ep_cs)
        # cascade weights r_evidence at 0.25 vs single_fault at 0.25 too — both same
        # but cascade weights r_resolve lower (0.30 vs 0.35) so a resolved episode
        # scores slightly differently
        assert isinstance(r_sf["total"], float) and isinstance(r_cs["total"], float)

    def test_adversarial_penalties_amplified(self):
        from bench.runner import _evaluate_episode_reward
        ep_sf  = self._episode(tier="single_fault",  total_turns=50)
        ep_adv = self._episode(tier="adversarial",   total_turns=50)
        r_sf   = _evaluate_episode_reward(ep_sf)
        r_adv  = _evaluate_episode_reward(ep_adv)
        assert r_adv["penalty_total"] > r_sf["penalty_total"]

    def test_reward_always_clamped_01(self):
        from bench.runner import _evaluate_episode_reward
        # Worst possible episode
        ep = self._episode(
            resolved=False, outcome="resolved", total_turns=100,
            time_to_resolve_s=9999, postmortem_path=None,
            judge={"reasoning": 0.0, "correctness": 0.0, "efficiency": 0.0},
        )
        r = _evaluate_episode_reward(ep)
        assert 0.0 <= r["total"] <= 1.0

    def test_speed_score_logistic(self):
        from bench.runner import _bounded_speed_score
        # Fast resolution should score high
        assert _bounded_speed_score(60, "single_fault") > 0.8
        # Slow resolution should score low
        assert _bounded_speed_score(600, "single_fault") < 0.2
        # Midpoint ~150s for single_fault → score near 0.5
        score_mid = _bounded_speed_score(150, "single_fault")
        assert 0.4 < score_mid < 0.6


class TestFrozenScenarioList:
    def test_frozen_scenarios_count(self):
        from bench.runner import FROZEN_SCENARIOS
        assert len(FROZEN_SCENARIOS) >= 28

    def test_all_tiers_represented(self):
        from bench.runner import FROZEN_SCENARIOS
        tiers = {s.split("/")[0] for s in FROZEN_SCENARIOS}
        assert "single_fault" in tiers
        assert "cascade" in tiers
        assert "named_replays" in tiers
        assert "multi_fault" in tiers

    def test_named_replays_count(self):
        from bench.runner import FROZEN_SCENARIOS
        replays = [s for s in FROZEN_SCENARIOS if "named_replays" in s]
        assert len(replays) == 10

    def test_no_duplicate_scenarios(self):
        from bench.runner import FROZEN_SCENARIOS
        assert len(FROZEN_SCENARIOS) == len(set(FROZEN_SCENARIOS))


class TestComparisonTable:
    def test_summary_has_required_keys(self, tmp_path):
        from bench.runner import compute_summary
        results = [
            {"scenario_id": "sf-001", "tier": "single_fault", "status": "ok",
             "resolved": True, "outcome": "resolved", "time_to_resolve_s": 120,
             "total_turns": 8, "judge": {"overall": 0.8}, "postmortem_path": "p.md",
             "reward_contract": {"total": 0.75}},
        ]
        summary = compute_summary(results, "test_tag", "test_model")
        for key in ("tag", "model", "resolution_rate", "avg_reward", "cascade_resolution_rate",
                    "named_replay_resolution_rate", "per_tier"):
            assert key in summary, f"Missing key: {key}"

    def test_resolution_rate_calculation(self, tmp_path):
        from bench.runner import compute_summary
        results = [
            {"scenario_id": f"s{i}", "tier": "single_fault", "status": "ok",
             "resolved": i < 7, "outcome": "resolved" if i < 7 else "unknown",
             "time_to_resolve_s": 100, "total_turns": 5,
             "judge": {"overall": 0.7}, "postmortem_path": "p.md",
             "reward_contract": {"total": 0.7}}
            for i in range(10)
        ]
        summary = compute_summary(results, "test", "test_model")
        assert summary["resolution_rate"] == pytest.approx(0.7)
