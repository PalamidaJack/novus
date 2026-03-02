"""Interrupt queue for human-in-the-loop mid-execution interjections."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class InterruptMessage:
    content: str
    timestamp: str


class InterruptQueue:
    def __init__(self):
        self._queue: asyncio.Queue[InterruptMessage] = asyncio.Queue()

    async def push(self, content: str) -> None:
        await self._queue.put(InterruptMessage(content=content, timestamp=datetime.utcnow().isoformat()))

    async def pop_nowait(self) -> Optional[InterruptMessage]:
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None
