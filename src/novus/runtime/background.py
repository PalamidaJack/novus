"""Background runtime task manager with polling/cancel support."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class BackgroundTaskState:
    id: str
    prompt: str
    status: str = "queued"  # queued, running, completed, failed, cancelled
    created_at: str = field(default_factory=_utcnow_iso)
    updated_at: str = field(default_factory=_utcnow_iso)
    result: Optional[str] = None
    error: Optional[str] = None
    session_id: Optional[str] = None

    def touch(self) -> None:
        self.updated_at = _utcnow_iso()


class BackgroundRunManager:
    """Runs async agent calls in background tasks with durable status map."""

    def __init__(self, runner: Callable[[str], Awaitable[str]], session_getter: Optional[Callable[[], Optional[str]]] = None):
        self.runner = runner
        self.session_getter = session_getter
        self.tasks: Dict[str, BackgroundTaskState] = {}
        self._handles: Dict[str, asyncio.Task[Any]] = {}

    def submit(self, prompt: str) -> BackgroundTaskState:
        task_id = str(uuid.uuid4())
        state = BackgroundTaskState(id=task_id, prompt=prompt)
        self.tasks[task_id] = state
        self._handles[task_id] = asyncio.create_task(self._run(task_id))
        return state

    async def _run(self, task_id: str) -> None:
        state = self.tasks[task_id]
        state.status = "running"
        state.touch()
        try:
            state.result = await self.runner(state.prompt)
            if self.session_getter:
                state.session_id = self.session_getter()
            if state.status != "cancelled":
                state.status = "completed"
            state.touch()
        except asyncio.CancelledError:
            state.status = "cancelled"
            state.touch()
        except Exception as exc:
            state.status = "failed"
            state.error = str(exc)
            state.touch()

    def get(self, task_id: str) -> Optional[BackgroundTaskState]:
        return self.tasks.get(task_id)

    def list(self, limit: int = 100) -> list[BackgroundTaskState]:
        return list(self.tasks.values())[-max(1, limit) :]

    def cancel(self, task_id: str) -> bool:
        handle = self._handles.get(task_id)
        state = self.tasks.get(task_id)
        if state is None:
            return False
        if handle and not handle.done():
            handle.cancel()
            state.status = "cancelled"
            state.touch()
            return True
        if state.status in {"queued", "running"}:
            state.status = "cancelled"
            state.touch()
            return True
        return False

