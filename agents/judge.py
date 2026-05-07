"""LLM Judge — evaluates each agent's action quality.

Used during trajectory generation (label rewards) and benchmark evaluation
(score postmortem quality, action correctness).

Backend: Qwen2.5-72B served by vLLM on the same MI300X (separate endpoint).
"""

import json
import os
from typing import Any

import httpx


JUDGE_URL = os.getenv("JUDGE_URL", "http://localhost:8001/v1")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "Qwen/Qwen2.5-72B-Instruct")


JUDGE_RUBRIC = """You are an SRE staff engineer evaluating an AI agent's action.

Score the action on a 0-1 scale across three dimensions:
1. **Correctness** — did it solve the problem? (0=no, 0.5=partial, 1=yes)
2. **Efficiency** — was it the minimum-blast-radius action? (0=destructive, 0.5=ok, 1=optimal)
3. **Reasoning** — were the tool calls justified by evidence? (0=random, 0.5=plausible, 1=well-reasoned)

Output ONLY this JSON:
{
  "correctness": 0.0-1.0,
  "efficiency": 0.0-1.0,
  "reasoning": 0.0-1.0,
  "overall": 0.0-1.0,
  "critique": "<2 sentences>"
}"""


async def judge_trajectory(incident: dict[str, Any]) -> dict[str, Any]:
    """Score an entire incident response (all 4 agents)."""
    user_msg = json.dumps(
        {
            "alert": incident.get("alert"),
            "triage_output": incident.get("triage", {}).get("final"),
            "diagnosis_output": incident.get("diagnosis", {}).get("final"),
            "remediation_actions": incident.get("remediation", {}).get("final", {}).get("actions_taken"),
            "remediation_outcome": incident.get("remediation", {}).get("final", {}).get("outcome"),
            "postmortem_path": incident.get("comms", {}).get("final", {}).get("postmortem_path"),
        },
        indent=2,
    )

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{JUDGE_URL}/chat/completions",
            json={
                "model": JUDGE_MODEL,
                "messages": [
                    {"role": "system", "content": JUDGE_RUBRIC},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.0,
            },
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]

    try:
        start = content.find("{")
        end = content.rfind("}")
        return json.loads(content[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return {"correctness": 0.0, "efficiency": 0.0, "reasoning": 0.0, "overall": 0.0,
                "critique": "judge_parse_failure", "raw": content}
