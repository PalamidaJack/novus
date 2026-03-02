"""Context engineering utilities: layered memory and compaction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


@dataclass
class CompactionResult:
    summary: str
    dropped_messages: int


class LayeredMemoryManager:
    """Loads memory in progressively scoped layers."""

    def __init__(self, cwd: Optional[Path] = None, max_chars: int = 6000):
        self.cwd = Path(cwd or Path.cwd())
        self.max_chars = max_chars

    def build_context(self) -> str:
        blocks: List[str] = []

        global_mem = Path.home() / ".novus" / "NOVUS.md"
        project_mem = self.cwd / "NOVUS.md"

        blocks.extend(self._load_file(global_mem, "Global Memory"))
        blocks.extend(self._load_file(project_mem, "Project Memory"))

        # Progressive disclosure: only load directory memory for current path chain.
        for parent in [self.cwd] + list(self.cwd.parents):
            scoped = parent / "NOVUS.md"
            if scoped.exists() and scoped != project_mem:
                blocks.extend(self._load_file(scoped, f"Directory Memory ({parent})"))
                break

        context = "\n\n".join(blocks)
        return context[: self.max_chars]

    def _load_file(self, path: Path, title: str) -> List[str]:
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8")
        return [f"## {title}\n{text[:2000]}"]


class ContextCompressor:
    """Compacts message history when token pressure is high."""

    def __init__(self, threshold_chars: int = 24000):
        self.threshold_chars = threshold_chars

    def maybe_compact(self, messages: List[dict]) -> tuple[List[dict], Optional[CompactionResult]]:
        total = sum(len(m.get("content", "")) for m in messages)
        if total < self.threshold_chars:
            return messages, None

        preserve = messages[-12:]
        old = messages[:-12]
        summary_lines = [
            "Compacted conversation summary:",
            f"- Prior turns: {len(old)}",
            "- Preserved facts: user intent, decisions, and tool outcomes.",
        ]

        # Keep a short digest of old content to preserve continuity.
        digest = "\n".join(
            f"- {m.get('role', 'unknown')}: {str(m.get('content', ''))[:120]}" for m in old[-15:]
        )
        summary = "\n".join(summary_lines + [digest])

        compacted = [{"role": "system", "content": summary}] + preserve
        return compacted, CompactionResult(summary=summary, dropped_messages=len(old))
