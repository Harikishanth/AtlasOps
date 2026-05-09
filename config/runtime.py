"""Central runtime constants and reward contract helpers.

Keeping these values in one module avoids config drift across benchmark,
training, and evaluation pipelines.
"""

from __future__ import annotations

import json
import math
import random
from typing import Any

FROZEN_SCENARIOS = [
    # single-fault
    "single_fault/sf-001", "single_fault/sf-002", "single_fault/sf-003", "single_fault/sf-004",
    "single_fault/sf-005", "single_fault/sf-006", "single_fault/sf-007", "single_fault/sf-008",
    # cascade
    "cascade/cs-001", "cascade/cs-002", "cascade/cs-003", "cascade/cs-004", "cascade/cs-005",
    # multi-fault
    "multi_fault/mf-001", "multi_fault/mf-002", "multi_fault/mf-003", "multi_fault/mf-004",
    "multi_fault/mf-005",
    # named replays
    "named_replays/hist-cloudflare-2019", "named_replays/hist-aws-s3-2017",
    "named_replays/hist-github-2018", "named_replays/hist-datadog-2023",
    "named_replays/hist-discord-2022", "named_replays/hist-fastly-2021",
    "named_replays/hist-facebook-bgp-2021", "named_replays/hist-slack-2022",
    "named_replays/hist-azure-dns-2019", "named_replays/hist-knight-capital-2012",
]

EVAL_SCENARIOS_BY_TIER = {
    "single_fault": [
        "single_fault/sf-001", "single_fault/sf-002", "single_fault/sf-003",
        "single_fault/sf-004", "single_fault/sf-005",
    ],
    "cascade": ["cascade/cs-001", "cascade/cs-002", "cascade/cs-003"],
    "named_replays": [
        "named_replays/hist-cloudflare-2019",
        "named_replays/hist-github-2018",
        "named_replays/hist-discord-2022",
    ],
}

LEADERBOARD_SCENARIOS = [
    ("single_fault/sf-001", "single_fault"),
    ("single_fault/sf-002", "single_fault"),
    ("single_fault/sf-006", "single_fault"),
    ("cascade/cs-001", "cascade"),
    ("cascade/cs-002", "cascade"),
    ("named_replays/hist-cloudflare-2019", "named_replays"),
    ("named_replays/hist-github-2018", "named_replays"),
]

SCENARIOS_BY_TIER = {
    "single_fault": [f"single_fault/sf-{i:03d}" for i in range(1, 9)],
    "cascade": [f"cascade/cs-{i:03d}" for i in range(1, 6)],
    "multi_fault": [f"multi_fault/mf-{i:03d}" for i in range(1, 6)],
    "named_replays": [
        "named_replays/hist-cloudflare-2019",
        "named_replays/hist-github-2018",
        "named_replays/hist-discord-2022",
        "named_replays/hist-datadog-2023",
        "named_replays/hist-aws-s3-2017",
    ],
}

TIER_SAMPLING_WEIGHTS = {
    "single_fault": 0.20,
    "cascade": 0.30,
    "multi_fault": 0.25,
    "named_replays": 0.25,
}

SPEED_MIDPOINTS = {
    "warmup": 90.0,
    "single_fault": 150.0,
    "cascade": 240.0,
    "multi_fault": 300.0,
    "named_replays": 300.0,
    "adversarial": 360.0,
}

BASE_REWARD_WEIGHTS = {
    "r_resolve": 0.35,
    "r_speed": 0.15,
    "r_evidence": 0.20,
    "r_safety": 0.20,
    "r_comms": 0.10,
}


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def bounded_speed_score(seconds: float, tier: str) -> float:
    midpoint = SPEED_MIDPOINTS.get(tier, 240.0)
    slope = 40.0
    return max(0.0, min(1.0, 1.0 / (1.0 + math.exp((seconds - midpoint) / slope))))


def evaluate_reward_contract(episode: dict[str, Any]) -> dict[str, Any]:
    """Tier-aware anti-gaming reward contract used across train/eval/bench.

    Improvements over baseline:
      + Red herring bonus (+0.15): rewards agents that dismiss misleading symptoms
        on multi-fault/adversarial/named-replay tiers (scored by 72B judge)
      + Phase skip penalty (-0.20): penalises agents that skip investigation phases
      + Lazy investigation penalty (-0.15): penalises fast resolution without evidence
        gathering on hard tiers (likely guessed, not diagnosed)
    """
    tier      = str(episode.get("tier", "unknown"))
    resolved  = bool(episode.get("resolved", False))
    outcome   = str(episode.get("outcome", "unknown"))
    turns     = int(episode.get("total_turns", 0))
    ttr       = float(episode.get("time_to_resolve_s", 9999))
    judge     = episode.get("judge", {}) or {}

    reasoning    = float(judge.get("reasoning",            0.0))
    correctness  = float(judge.get("correctness",          0.0))
    efficiency   = float(judge.get("efficiency",           0.0))
    red_herring  = float(judge.get("red_herring_handling", 0.5))

    r_resolve = 1.0 if resolved else (0.5 if outcome == "partial" else 0.0)
    r_speed   = bounded_speed_score(ttr, tier)
    r_evidence = clamp01((reasoning + correctness) / 2.0)
    r_safety   = clamp01(efficiency)
    r_comms    = 1.0 if episode.get("postmortem_path") else 0.3

    # ── Red herring bonus ─────────────────────────────────────────────────────
    # Only awarded on tiers that contain misleading symptoms. Requires the 72B
    # judge to score red_herring_handling >= 0.8 (correctly dismissed red herrings).
    _rh_tiers = {"multi_fault", "named_replays", "adversarial"}
    red_herring_bonus = 0.15 if (tier in _rh_tiers and red_herring >= 0.8) else 0.0

    # ── Penalties ─────────────────────────────────────────────────────────────
    penalties = {
        "command_spam":          0.10 if turns > 40 else 0.0,
        "false_resolution":      0.25 if (not resolved and outcome == "resolved") else 0.0,
        "unsafe_shortcut":       0.20 if efficiency < 0.3 else 0.0,
        "hallucinated_evidence": 0.20 if (reasoning < 0.25 and correctness < 0.5) else 0.0,
        "over_silence":          0.10 if ("silence" in json.dumps(episode).lower() and not resolved) else 0.0,
        # Phase ordering: too few turns without resolution = investigation was skipped
        "phase_skip":            0.20 if (turns < 4 and not resolved) else 0.0,
        # Lazy investigation: suspiciously fast resolution on hard tiers without
        # enough tool calls suggests the agent guessed rather than diagnosed
        "lazy_investigation":    0.15 if (
            resolved and turns < 5
            and tier not in ("warmup", "single_fault")
        ) else 0.0,
    }

    # ── Tier-specific weight adjustments ─────────────────────────────────────
    weights = dict(BASE_REWARD_WEIGHTS)
    if tier == "single_fault":
        weights.update({"r_evidence": 0.25, "r_speed": 0.10})
    elif tier == "cascade":
        weights.update({"r_resolve": 0.30, "r_evidence": 0.25, "r_speed": 0.10})
    elif tier == "multi_fault":
        weights.update({"r_safety": 0.25, "r_evidence": 0.25, "r_speed": 0.10})
    elif tier in ("adversarial", "named_replays"):
        penalties = {k: v * 1.25 for k, v in penalties.items()}
        weights.update({"r_safety": 0.25, "r_evidence": 0.25, "r_speed": 0.05})

    weighted = (
        weights["r_resolve"] * r_resolve
        + weights["r_speed"]   * r_speed
        + weights["r_evidence"] * r_evidence
        + weights["r_safety"]  * r_safety
        + weights["r_comms"]   * r_comms
        + red_herring_bonus
    )
    penalty_total = sum(penalties.values())
    total = clamp01(weighted - penalty_total)

    return {
        "components": {
            "resolve":           round(r_resolve,        4),
            "speed":             round(r_speed,          4),
            "evidence":          round(r_evidence,       4),
            "safety":            round(r_safety,         4),
            "comms":             round(r_comms,          4),
            "red_herring_bonus": round(red_herring_bonus, 4),
        },
        "penalties":     {k: round(v, 4) for k, v in penalties.items()},
        "penalty_total": round(penalty_total, 4),
        "total":         round(total, 4),
    }


# ── Spaced-Repetition Curriculum Manager ─────────────────────────────────────

class CurriculumManager:
    """Adaptive scenario selector with spaced repetition.

    Priority score = +100 (novel) + 50×(1−success_rate) + 30 (SR bonus) − 20 (recency).
    Graduated scenarios resurface at intervals [3, 6, 12, 24, 48] episodes;
    pass → double interval, fail → reset to 3.
    """

    SPACED_REP_INTERVALS = [3, 6, 12, 24, 48]
    MASTERY_THRESHOLD = 0.7
    MASTERY_WINDOW = 10
    MASTERY_DECAY = 0.85
    MIN_ATTEMPTS_FOR_MASTERY = 3

    def __init__(self) -> None:
        # scenario_id → list of (episode_idx, reward) tuples
        self._history: dict[str, list[tuple[int, float]]] = {}
        # scenario_id → index into SPACED_REP_INTERVALS
        self._graduated: dict[str, int] = {}
        # scenario_id → episode number when it should resurface
        self._next_resurface: dict[str, int] = {}
        # last 2 scenario IDs (recency penalty)
        self._recent: list[str] = []
        self._episode_count = 0

    def record(self, scenario_id: str, resolved: bool, reward: float) -> None:
        """Call after every episode to update mastery and spaced-rep state."""
        self._history.setdefault(scenario_id, []).append(
            (self._episode_count, reward)
        )
        self._recent = (self._recent + [scenario_id])[-2:]

        if scenario_id in self._graduated:
            # Already graduated — update interval based on result
            idx = self._graduated[scenario_id]
            if resolved:
                idx = min(idx + 1, len(self.SPACED_REP_INTERVALS) - 1)
            else:
                idx = 0
            self._graduated[scenario_id] = idx
        elif self._is_mastered(scenario_id):
            # Newly mastered → enter spaced repetition
            self._graduated[scenario_id] = 0

        if scenario_id in self._graduated:
            interval = self.SPACED_REP_INTERVALS[self._graduated[scenario_id]]
            self._next_resurface[scenario_id] = self._episode_count + interval

        self._episode_count += 1

    def next_scenario(self, pool: list[tuple[str, str]]) -> tuple[str, str]:
        """Return (scenario_id, tier) chosen by priority scoring.

        Uses soft-max over the top-3 candidates so training isn't fully
        deterministic (avoids overfitting to the argmax scenario).
        """
        if not pool:
            pool = [(s, s.split("/")[0]) for s in FROZEN_SCENARIOS]

        scored = sorted(
            ((self._priority_score(sid), sid, tier) for sid, tier in pool),
            reverse=True,
        )
        top = scored[: min(3, len(scored))]
        weights = [max(s, 0.01) for s, _, _ in top]
        total_w = sum(weights)
        probs = [w / total_w for w in weights]
        chosen_idx = random.choices(range(len(top)), weights=probs)[0]
        _, scenario_id, tier = top[chosen_idx]
        return scenario_id, tier

    def stats(self) -> dict[str, Any]:
        return {
            "total_episodes": self._episode_count,
            "scenarios_tried": len(self._history),
            "graduated": len(self._graduated),
            "due_for_resurface": sum(
                1 for sid, ep in self._next_resurface.items()
                if self._episode_count >= ep
            ),
        }

    # ── internals ──

    def _success_rate(self, scenario_id: str) -> float:
        history = self._history.get(scenario_id, [])
        if not history:
            return 0.0
        window = history[-self.MASTERY_WINDOW :]
        weighted_sum = total_w = 0.0
        for i, (_, reward) in enumerate(window):
            w = self.MASTERY_DECAY ** (len(window) - 1 - i)
            weighted_sum += w * reward
            total_w += w
        return weighted_sum / total_w if total_w else 0.0

    def _is_mastered(self, scenario_id: str) -> bool:
        history = self._history.get(scenario_id, [])
        return (
            len(history) >= self.MIN_ATTEMPTS_FOR_MASTERY
            and self._success_rate(scenario_id) >= self.MASTERY_THRESHOLD
        )

    def _priority_score(self, scenario_id: str) -> float:
        score = 0.0
        history = self._history.get(scenario_id, [])

        if not history:
            score += 100.0                             # novelty bonus
        score += 50.0 * (1.0 - self._success_rate(scenario_id))  # weakness targeting
        if (
            scenario_id in self._next_resurface
            and self._episode_count >= self._next_resurface[scenario_id]
        ):
            score += 30.0                              # spaced-rep resurface bonus
        if scenario_id in self._recent:
            score -= 20.0                              # recency penalty
        return score


# ── Dense Per-Step Reward Tracker ─────────────────────────────────────────────

class StepRewardTracker:
    """Accumulates dense per-tool-call rewards within one agent role's turn loop.

    Base formula (progress-based):
      progress_delta × 0.8 + 0.1 if forward progress
      × 0.5 if tool failed
      − 0.1 per rollback

    Tool category bonuses (per-action scoring):
      +0.05  investigative tool success (evidence gathering rewarded)
      +0.08  mutating tool success (remediation action rewarded)
      −0.08  mutating tool failure (failed fix penalised harder)
      −0.05  redundant call (exact same tool+args seen before)

    Clamped to [−0.5, 0.99].
    Partial progress = success_count / total_calls (monotonic — never decreases).
    """

    _MUTATING = frozenset({
        "argocd_rollback", "kubectl_rollout", "kubectl_scale", "alertmanager_silence",
    })
    _INVESTIGATIVE = frozenset({
        "promql_query", "promql_query_range", "jaeger_search", "jaeger_get_trace",
        "kubectl_logs", "kubectl_describe", "alertmanager_list_alerts",
        "gcloud_logs_read", "cloud_monitoring_query",
    })

    def __init__(self) -> None:
        self._calls: list[tuple[str, dict]] = []
        self._success = 0
        self._fail = 0
        self._rollbacks = 0
        self._partial_progress = 0.0
        self._step_rewards: list[float] = []

    def record(self, tool_name: str, args: dict, output: dict) -> float:
        """Record one tool call. Returns the per-step reward for this call."""
        success = bool(output.get("success", True)) and "error" not in output

        rollback = self._detect_rollback(tool_name, args)
        if rollback:
            self._rollbacks += 1

        idempotent_retry = success and self._was_tried(tool_name, args)

        self._calls.append((tool_name, args))
        if success:
            self._success += 1
        else:
            self._fail += 1

        # Monotonic partial-progress
        total = self._success + self._fail
        prev = self._partial_progress
        self._partial_progress = max(self._success / max(total, 1), prev)
        delta = self._partial_progress - prev

        r = delta * 0.8
        if delta > 0:
            r += 0.1
        if not success:
            r *= 0.5
        if rollback:
            r -= 0.1
        if idempotent_retry:
            r += 0.02

        # ── Tool category bonuses ──────────────────────────────────────────
        if success and tool_name in self._INVESTIGATIVE:
            r += 0.05   # reward evidence gathering
        if success and tool_name in self._MUTATING:
            r += 0.08   # reward successful remediation
        if not success and tool_name in self._MUTATING:
            r -= 0.08   # extra penalty for failed mutating action
        if not idempotent_retry and self._was_tried(tool_name, args):
            r -= 0.05   # penalty for redundant call with same args

        r = max(-0.5, min(0.99, r))

        self._step_rewards.append(r)
        return r

    def total(self) -> float:
        return sum(self._step_rewards)

    def partial_progress(self) -> float:
        return self._partial_progress

    def summary(self) -> dict[str, Any]:
        return {
            "success_count": self._success,
            "fail_count": self._fail,
            "rollback_count": self._rollbacks,
            "partial_progress": round(self._partial_progress, 4),
            "dense_reward_total": round(self.total(), 4),
            "step_rewards": [round(r, 4) for r in self._step_rewards],
        }

    def _detect_rollback(self, tool_name: str, args: dict) -> bool:
        if tool_name not in self._MUTATING:
            return False
        resource = args.get("deployment") or args.get("app") or args.get("resource") or ""
        return any(
            t == tool_name
            and (a.get("deployment") or a.get("app") or a.get("resource")) == resource
            for t, a in self._calls
        )

    def _was_tried(self, tool_name: str, args: dict) -> bool:
        return any(t == tool_name and a == args for t, a in self._calls[:-1])


# Module-level curriculum singleton shared across bench/train/eval
curriculum = CurriculumManager()
