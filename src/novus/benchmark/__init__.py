"""Benchmark harness for NOVUS-Bench style evaluation."""

from __future__ import annotations

import asyncio
import time
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, List
from novus.benchmark.trends import (
    BenchmarkSnapshot,
    compare_snapshots,
    load_snapshot,
    markdown_summary,
    save_snapshot,
    snapshot_from_report,
)


@dataclass
class BenchmarkCase:
    name: str
    prompt: str
    check: Callable[[str], bool]
    category: str


@dataclass
class BenchmarkResult:
    case_name: str
    category: str
    passed: bool
    latency_ms: float
    output: str


@dataclass
class BenchmarkReport:
    results: List[BenchmarkResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.passed) / len(self.results)


class BenchmarkHarness:
    def __init__(self, runner: Callable[[str], Awaitable[str]]):
        self.runner = runner

    async def run(self, cases: List[BenchmarkCase]) -> BenchmarkReport:
        report = BenchmarkReport()
        for case in cases:
            start = time.time()
            output = await self.runner(case.prompt)
            latency = (time.time() - start) * 1000
            report.results.append(
                BenchmarkResult(
                    case_name=case.name,
                    category=case.category,
                    passed=case.check(output),
                    latency_ms=latency,
                    output=output,
                )
            )
        return report


def default_cases() -> List[BenchmarkCase]:
    return [
        BenchmarkCase(
            name="arithmetic",
            prompt="What is 15 * 23?",
            check=lambda out: "345" in out,
            category="core_reasoning",
        ),
        BenchmarkCase(
            name="addition",
            prompt="What is 2 + 2?",
            check=lambda out: "4" in out,
            category="core_reasoning",
        ),
    ]


def load_external_cases(path: Path) -> List[BenchmarkCase]:
    """Load benchmark cases from JSON for SWE-style or custom suites."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases: List[BenchmarkCase] = []
    for idx, item in enumerate(payload.get("cases", [])):
        expected_contains = [str(x) for x in item.get("expected_contains", [])]
        case_name = str(item.get("name", f"external_{idx}"))
        prompt = str(item.get("prompt", ""))
        category = str(item.get("category", "external"))
        cases.append(
            BenchmarkCase(
                name=case_name,
                prompt=prompt,
                category=category,
                check=lambda out, expected=expected_contains: all(tok in out for tok in expected),
            )
        )
    return cases


__all__ = [
    "BenchmarkCase",
    "BenchmarkResult",
    "BenchmarkReport",
    "BenchmarkHarness",
    "BenchmarkSnapshot",
    "compare_snapshots",
    "load_snapshot",
    "markdown_summary",
    "save_snapshot",
    "snapshot_from_report",
    "default_cases",
    "load_external_cases",
]
