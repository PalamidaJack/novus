"""Depth-limited subagent dispatch for parallel exploration tasks."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Iterable, List


@dataclass
class SubagentTask:
    name: str
    prompt: str


@dataclass
class SubagentResult:
    name: str
    summary: str
    confidence: float


class SubagentDispatcher:
    """Dispatches depth=1 subagents and returns summarized outputs."""

    def __init__(self, worker: Callable[[str], Any], max_depth: int = 1):
        self.worker = worker
        self.max_depth = max_depth

    async def dispatch_many(self, tasks: Iterable[SubagentTask], depth: int = 0) -> List[SubagentResult]:
        if depth >= self.max_depth:
            raise ValueError("Subagent depth limit reached")

        async def _run(task: SubagentTask) -> SubagentResult:
            response = self.worker(task.prompt)
            if asyncio.iscoroutine(response):
                response = await response
            return SubagentResult(name=task.name, summary=str(response)[:2000], confidence=0.7)

        return await asyncio.gather(*[_run(t) for t in tasks])
