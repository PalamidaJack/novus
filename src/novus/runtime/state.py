"""Runtime state models for next-generation agent loops."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PlanItem:
    """A structured task plan item."""

    id: str
    task: str
    status: str = "pending"  # pending, in_progress, completed, blocked
    notes: str = ""

    @classmethod
    def create(cls, task: str, status: str = "pending") -> "PlanItem":
        return cls(id=str(uuid.uuid4()), task=task, status=status)


@dataclass
class RuntimeState:
    """Durable state for long-running agent loops."""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=_utcnow_iso)
    updated_at: str = field(default_factory=_utcnow_iso)

    original_request: str = ""
    plan: List[PlanItem] = field(default_factory=list)
    decisions: List[str] = field(default_factory=list)
    modified_files: List[str] = field(default_factory=list)
    tool_events: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def mark_updated(self) -> None:
        self.updated_at = _utcnow_iso()

    def append_decision(self, decision: str) -> None:
        self.decisions.append(decision)
        self.mark_updated()

    def ensure_plan(self, task_description: str) -> None:
        if not self.plan:
            self.plan = [
                PlanItem.create("Understand the task", status="completed"),
                PlanItem.create(task_description, status="in_progress"),
                PlanItem.create("Validate and return final answer", status="pending"),
            ]
            self.mark_updated()

    def set_in_progress(self, item_id: str) -> None:
        for item in self.plan:
            if item.id == item_id:
                item.status = "in_progress"
        self.mark_updated()

    def set_completed(self, item_id: str, notes: str = "") -> None:
        for item in self.plan:
            if item.id == item_id:
                item.status = "completed"
                if notes:
                    item.notes = notes
        self.mark_updated()

    def add_tool_event(self, name: str, args: Dict[str, Any], result: Any) -> None:
        self.tool_events.append(
            {
                "time": _utcnow_iso(),
                "name": name,
                "args": args,
                "result": str(result)[:2000],
            }
        )
        self.mark_updated()

    def to_prompt_block(self) -> str:
        lines = ["[CURRENT PLAN STATUS]"]
        for item in self.plan:
            icon = {
                "completed": "[x]",
                "in_progress": "[~]",
                "blocked": "[!]",
                "pending": "[ ]",
            }.get(item.status, "[ ]")
            line = f"{icon} {item.task}"
            if item.notes:
                line += f" ({item.notes})"
            lines.append(line)
        return "\n".join(lines)

    def dump(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "original_request": self.original_request,
            "plan": [item.__dict__ for item in self.plan],
            "decisions": self.decisions,
            "modified_files": self.modified_files,
            "tool_events": self.tool_events,
            "metadata": self.metadata,
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Optional["RuntimeState"]:
        if not path.exists():
            return None

        payload = json.loads(path.read_text(encoding="utf-8"))
        state = cls(
            session_id=payload.get("session_id", str(uuid.uuid4())),
            created_at=payload.get("created_at", _utcnow_iso()),
            updated_at=payload.get("updated_at", _utcnow_iso()),
            original_request=payload.get("original_request", ""),
            decisions=payload.get("decisions", []),
            modified_files=payload.get("modified_files", []),
            tool_events=payload.get("tool_events", []),
            metadata=payload.get("metadata", {}),
        )
        state.plan = [PlanItem(**i) for i in payload.get("plan", [])]
        return state
