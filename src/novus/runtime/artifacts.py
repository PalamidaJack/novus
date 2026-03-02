"""Run artifact logging for deterministic trace and replay."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class RunEvent:
    event_type: str
    session_id: str
    turn: int
    timestamp: str
    payload: Dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(
            {
                "event_type": self.event_type,
                "session_id": self.session_id,
                "turn": self.turn,
                "timestamp": self.timestamp,
                "payload": self.payload,
            },
            default=str,
        )


class RunArtifactLogger:
    """Writes append-only runtime event logs as JSONL."""

    def __init__(self, run_dir: Optional[Path] = None):
        self.run_dir = Path(run_dir or Path.home() / ".novus" / "runs")
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def run_path(self, session_id: str) -> Path:
        return self.run_dir / f"{session_id}.jsonl"

    def write(self, event: RunEvent) -> None:
        path = self.run_path(event.session_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(event.to_json() + "\n")

    def read(self, session_id: str) -> List[Dict[str, Any]]:
        path = self.run_path(session_id)
        if not path.exists():
            return []

        events: List[Dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            events.append(json.loads(line))
        return events

    def list_sessions(self, limit: int = 50) -> List[str]:
        files = sorted(self.run_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [p.stem for p in files[:limit]]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
