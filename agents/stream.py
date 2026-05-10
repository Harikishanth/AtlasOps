"""Real-time thought streaming for AtlasOps agents.

Agents emit narrated thoughts as they work. The dashboard subscribes
via SSE (/stream endpoint) and displays them live alongside Grafana.
"""

import asyncio
import json
import time
from collections import deque
from typing import AsyncGenerator


# In-memory ring buffer — last 200 thought events
_thought_buffer: deque = deque(maxlen=200)
_subscribers: list[asyncio.Queue] = []


class ThoughtEvent:
    def __init__(self, role: str, phase: str, thought: str, tool: str = "",
                 result_summary: str = ""):
        self.ts        = time.time()
        self.role      = role       # triage / diagnosis / remediation / comms
        self.phase     = phase      # thinking / tool_call / tool_result / waiting_approval / conclusion
        self.thought   = thought    # human-readable narration
        self.tool      = tool       # tool name if phase=tool_call
        self.result_summary = result_summary

    def to_dict(self) -> dict:
        return {
            "ts":             round(self.ts, 3),
            "role":           self.role,
            "phase":          self.phase,
            "thought":        self.thought,
            "tool":           self.tool,
            "result_summary": self.result_summary,
        }

    def to_sse(self) -> str:
        return f"data: {json.dumps(self.to_dict())}\n\n"


def emit(role: str, phase: str, thought: str, tool: str = "",
         result_summary: str = "") -> None:
    """Emit a thought event to all live subscribers + buffer."""
    event = ThoughtEvent(role, phase, thought, tool, result_summary)
    _thought_buffer.append(event)
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


def clear() -> None:
    """Flush the thought buffer so new SSE subscribers don't replay stale events."""
    _thought_buffer.clear()


def get_history() -> list[dict]:
    return [e.to_dict() for e in _thought_buffer]


async def subscribe() -> AsyncGenerator[str, None]:
    """SSE generator — yields thought events as they arrive."""
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers.append(q)
    # Send buffered history first so new subscribers catch up
    for event in list(_thought_buffer):
        yield event.to_sse()
    try:
        while True:
            event = await asyncio.wait_for(q.get(), timeout=30.0)
            yield event.to_sse()
    except asyncio.TimeoutError:
        yield "data: {\"heartbeat\": true}\n\n"
    finally:
        _subscribers.remove(q)
