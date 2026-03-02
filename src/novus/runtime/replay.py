"""Replay and summarization of runtime artifact logs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class ReplaySummary:
    session_id: str
    total_events: int
    turns: int
    tool_calls: int
    errors: int
    final_answer: str | None


class RunReplayer:
    def summarize(self, session_id: str, events: List[Dict[str, Any]]) -> ReplaySummary:
        tool_calls = 0
        errors = 0
        max_turn = 0
        final_answer = None

        for e in events:
            et = e.get("event_type", "")
            turn = int(e.get("turn", 0))
            max_turn = max(max_turn, turn)

            if et in {"tool_result", "multi_tool_result"}:
                tool_calls += 1
            if "error" in et:
                errors += 1
            if et == "final":
                final_answer = str(e.get("payload", {}).get("answer", ""))

        return ReplaySummary(
            session_id=session_id,
            total_events=len(events),
            turns=max_turn + 1 if events else 0,
            tool_calls=tool_calls,
            errors=errors,
            final_answer=final_answer,
        )
