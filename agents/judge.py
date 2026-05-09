"""LLM Judge — evaluates each agent's action quality using Qwen2.5-72B on AMD MI300X.

Three-persona evaluation system:
  Junior    (warmup, single_fault)   — lenient, checks basic resolution
  Senior    (cascade, multi_fault)   — standard SRE rubric + red herring handling
  Principal (named_replays, adversarial) — strict, demands evidence-before-action

Red herring handling scored as 4th dimension for multi-fault/adversarial tiers.
"""

import json
import os
from typing import Any

import httpx

JUDGE_URL   = os.getenv("JUDGE_URL",   "http://localhost:8001/v1")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "Qwen/Qwen2.5-72B-Instruct-AWQ")

# ── Persona rubrics ────────────────────────────────────────────────────────────

_RUBRIC_JUNIOR = """You are a junior SRE evaluating an AI agent's incident response. Be lenient.
Focus only on: did it resolve the incident? Were tool calls at least somewhat relevant?

Score each dimension 0.0–1.0. Output ONLY this JSON, nothing else:
{"correctness":0.0,"efficiency":0.0,"reasoning":0.0,"red_herring_handling":0.5,"overall":0.0,"critique":"<1 sentence>"}"""

_RUBRIC_SENIOR = """You are a senior SRE (8 years experience) evaluating an AI agent's incident response.

Score each dimension 0.0–1.0:
1. correctness: Did it correctly identify and fix the real root cause?
2. efficiency: Minimum blast-radius actions? No unnecessary mutations or restarts?
3. reasoning: Were tool calls justified by evidence gathered first?
4. red_herring_handling: Did it investigate broadly but avoid wasting time on misleading symptoms?
   1.0 = investigated multiple services, dismissed red herrings, fixed only the real fault
   0.5 = investigated only the obvious service (no red herrings present or neutral handling)
   0.0 = chased red herrings, attempted wrong fixes, wasted remediation on non-root-cause

Output ONLY this JSON, nothing else:
{"correctness":0.0,"efficiency":0.0,"reasoning":0.0,"red_herring_handling":0.0,"overall":0.0,"critique":"<2 sentences>"}"""

_RUBRIC_PRINCIPAL = """You are a principal SRE (15+ years) applying strict evaluation standards.

Score each dimension 0.0–1.0:
1. correctness: Root cause correctly identified WITH verifiable evidence? Fix confirmed working via metrics?
2. efficiency: Optimal tool selection? Zero redundant calls? Absolute minimum blast radius?
3. reasoning: Every mutating action preceded by diagnostic evidence? Post-fix verification via promql/jaeger?
4. red_herring_handling: For complex incidents with multiple symptoms across services:
   1.0 = systematically investigated all affected services, correctly dismissed misleading symptoms,
         remediated ONLY the actual root cause service(s) — no wasted fix attempts
   0.5 = partial investigation, may have been distracted by one red herring but recovered
   0.0 = chased wrong services, wasted remediation attempts on non-root-cause, missed real fault

Output ONLY this JSON, nothing else:
{"correctness":0.0,"efficiency":0.0,"reasoning":0.0,"red_herring_handling":0.0,"overall":0.0,"critique":"<2 precise sentences citing specific evidence>"}"""

_TIER_PERSONA = {
    "warmup":        _RUBRIC_JUNIOR,
    "single_fault":  _RUBRIC_JUNIOR,
    "cascade":       _RUBRIC_SENIOR,
    "multi_fault":   _RUBRIC_SENIOR,
    "named_replays": _RUBRIC_PRINCIPAL,
    "adversarial":   _RUBRIC_PRINCIPAL,
}

_FALLBACK = {
    "correctness": 0.5, "efficiency": 0.5, "reasoning": 0.5,
    "red_herring_handling": 0.5, "overall": 0.5, "critique": "judge_fallback",
}


async def judge_trajectory(incident: dict[str, Any], tier: str = "unknown") -> dict[str, Any]:
    """Score an entire incident response using the tier-appropriate persona.

    Args:
        incident: Full incident dict from coordinator (triage/diagnosis/remediation/comms).
        tier: Scenario tier — selects Junior/Senior/Principal rubric.
              Defaults to 'unknown' (falls back to Senior rubric).
    """
    try:
        rubric = _TIER_PERSONA.get(tier, _RUBRIC_SENIOR)

        user_msg = json.dumps({
            "tier": tier,
            "triage_output":        incident.get("triage",      {}).get("final"),
            "diagnosis_output":     incident.get("diagnosis",   {}).get("final"),
            "remediation_actions":  incident.get("remediation", {}).get("final", {}).get("actions_taken"),
            "remediation_outcome":  incident.get("remediation", {}).get("final", {}).get("outcome"),
            "postmortem_path":      incident.get("comms",       {}).get("final", {}).get("postmortem_path"),
        }, indent=2)

        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{JUDGE_URL}/chat/completions",
                json={
                    "model": JUDGE_MODEL,
                    "messages": [
                        {"role": "system", "content": rubric},
                        {"role": "user",   "content": user_msg[:3000]},
                    ],
                    "temperature": 0.0,
                    "max_tokens":  250,
                },
            )
            if r.status_code != 200:
                return _FALLBACK

            content = r.json()["choices"][0]["message"]["content"]

        start = content.find("{")
        end   = content.rfind("}") + 1
        if start == -1 or end == 0:
            return _FALLBACK

        result = json.loads(content[start:end])
        result.setdefault("red_herring_handling", 0.5)
        return result

    except Exception:
        return _FALLBACK
