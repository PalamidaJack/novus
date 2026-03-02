"""Trace grading for runtime behavior quality gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class TraceGrade:
    session_id: str
    score: float
    max_score: float
    passed: bool
    reasons: List[str]
    metrics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "score": self.score,
            "max_score": self.max_score,
            "passed": self.passed,
            "reasons": self.reasons,
            "metrics": self.metrics,
        }


class TraceGrader:
    """Grades whether traces show robust agent behavior, not only final output."""

    def __init__(self, min_score: float = 0.7):
        self.min_score = min_score

    def grade(self, session_id: str, events: List[Dict[str, Any]]) -> TraceGrade:
        if not events:
            return TraceGrade(
                session_id=session_id,
                score=0.0,
                max_score=1.0,
                passed=False,
                reasons=["no_events"],
                metrics={"total_events": 0},
            )

        total_events = len(events)
        has_start = any(e.get("event_type") == "start" for e in events)
        has_end = any(e.get("event_type") == "end" for e in events)
        has_final = any(e.get("event_type") == "final" for e in events)
        has_error_terminal = any(str(e.get("event_type", "")).startswith("error_") for e in events)
        has_terminal = has_final or has_error_terminal
        infer_count = sum(1 for e in events if e.get("event_type") == "infer")
        error_count = sum(1 for e in events if "error" in str(e.get("event_type", "")))
        tool_count = sum(1 for e in events if e.get("event_type") in {"tool_result", "multi_tool_result"})
        trace_id_coverage = sum(
            1 for e in events if isinstance(e.get("payload"), dict) and e.get("payload", {}).get("trace_id")
        ) / total_events

        score = 0.0
        reasons: List[str] = []

        if has_start:
            score += 0.15
        else:
            reasons.append("missing_start_event")
        if has_terminal:
            score += 0.2
        else:
            reasons.append("missing_terminal_event")
        if not has_final and has_error_terminal:
            reasons.append("ended_with_error")
        if has_end:
            score += 0.15
        else:
            reasons.append("missing_end_event")

        if infer_count > 0:
            score += 0.15
        else:
            reasons.append("no_inference_events")

        if tool_count > 0:
            score += 0.15

        if error_count == 0:
            score += 0.1
        else:
            reasons.append(f"errors_detected:{error_count}")

        if trace_id_coverage >= 0.95:
            score += 0.1
        else:
            reasons.append(f"low_trace_id_coverage:{trace_id_coverage:.2f}")

        score = min(1.0, score)
        return TraceGrade(
            session_id=session_id,
            score=score,
            max_score=1.0,
            passed=score >= self.min_score,
            reasons=reasons,
            metrics={
                "total_events": total_events,
                "has_start": has_start,
                "has_final": has_final,
                "has_end": has_end,
                "infer_count": infer_count,
                "tool_count": tool_count,
                "error_count": error_count,
                "trace_id_coverage": trace_id_coverage,
            },
        )
