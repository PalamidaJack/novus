"""Benchmark trend snapshots, comparisons, and markdown summaries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class BenchmarkSnapshot:
    pass_rate: float
    total: int
    avg_latency_ms: float
    p95_latency_ms: float
    timestamp: str
    commit: Optional[str] = None
    case_details: Optional[Dict[str, Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pass_rate": self.pass_rate,
            "total": self.total,
            "avg_latency_ms": self.avg_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "timestamp": self.timestamp,
            "commit": self.commit,
            "case_details": self.case_details or {},
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "BenchmarkSnapshot":
        return cls(
            pass_rate=float(payload.get("pass_rate", 0.0)),
            total=int(payload.get("total", 0)),
            avg_latency_ms=float(payload.get("avg_latency_ms", 0.0)),
            p95_latency_ms=float(payload.get("p95_latency_ms", 0.0)),
            timestamp=str(payload.get("timestamp", _utcnow_iso())),
            commit=payload.get("commit"),
            case_details=payload.get("case_details", {}) or {},
        )


def _p95(values: List[float]) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    idx = int((len(sorted_values) - 1) * 0.95)
    return float(sorted_values[idx])


def snapshot_from_report(report_payload: Dict[str, Any], commit: Optional[str] = None) -> BenchmarkSnapshot:
    bench = report_payload.get("benchmark", {})
    results = bench.get("results", [])
    latencies = [float(r.get("latency_ms", 0.0)) for r in results]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    case_details = {
        str(r.get("case_name", f"case_{idx}")): {
            "passed": bool(r.get("passed", False)),
            "latency_ms": float(r.get("latency_ms", 0.0)),
            "category": r.get("category"),
        }
        for idx, r in enumerate(results)
    }
    return BenchmarkSnapshot(
        pass_rate=float(bench.get("pass_rate", 0.0)),
        total=int(bench.get("total", 0)),
        avg_latency_ms=avg_latency,
        p95_latency_ms=_p95(latencies),
        timestamp=_utcnow_iso(),
        commit=commit,
        case_details=case_details,
    )


def load_snapshot(path: Path) -> BenchmarkSnapshot:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "benchmark" in payload:
        # Accept full benchmark report JSON as input for convenience.
        return snapshot_from_report(payload, commit=payload.get("git", {}).get("commit"))
    return BenchmarkSnapshot.from_dict(payload)


def save_snapshot(path: Path, snapshot: BenchmarkSnapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot.to_dict(), indent=2), encoding="utf-8")


def compare_snapshots(
    baseline: BenchmarkSnapshot,
    current: BenchmarkSnapshot,
    max_pass_rate_drop: float = 0.05,
    max_latency_regression_pct: float = 200.0,
    max_case_latency_regression_pct: float = 300.0,
    allow_case_pass_failures: int = 0,
    category_thresholds: Optional[Dict[str, Dict[str, float]]] = None,
) -> Dict[str, Any]:
    pass_rate_delta = current.pass_rate - baseline.pass_rate

    if baseline.avg_latency_ms <= 0:
        avg_latency_delta_pct = 0.0 if current.avg_latency_ms <= 0 else 100.0
    else:
        avg_latency_delta_pct = ((current.avg_latency_ms - baseline.avg_latency_ms) / baseline.avg_latency_ms) * 100.0

    if baseline.p95_latency_ms <= 0:
        p95_latency_delta_pct = 0.0 if current.p95_latency_ms <= 0 else 100.0
    else:
        p95_latency_delta_pct = ((current.p95_latency_ms - baseline.p95_latency_ms) / baseline.p95_latency_ms) * 100.0

    regression_reasons: List[str] = []
    if pass_rate_delta < -abs(max_pass_rate_drop):
        regression_reasons.append(
            f"pass_rate_drop {pass_rate_delta:.4f} below allowed {-abs(max_pass_rate_drop):.4f}"
        )
    if avg_latency_delta_pct > abs(max_latency_regression_pct):
        regression_reasons.append(
            f"avg_latency_regression {avg_latency_delta_pct:.2f}% above allowed {abs(max_latency_regression_pct):.2f}%"
        )

    case_regressions: List[Dict[str, Any]] = []
    case_pass_failures = 0
    category_pass_failures: Dict[str, int] = {}
    category_latency_regressions: Dict[str, int] = {}
    baseline_cases = baseline.case_details or {}
    current_cases = current.case_details or {}
    for case_name, b in baseline_cases.items():
        if case_name not in current_cases:
            case_regressions.append(
                {"case_name": case_name, "reason": "missing_in_current", "baseline": b, "current": None}
            )
            case_pass_failures += 1
            continue

        c = current_cases[case_name]
        b_pass = bool(b.get("passed", False))
        c_pass = bool(c.get("passed", False))
        if b_pass and not c_pass:
            category = str(b.get("category") or c.get("category") or "uncategorized")
            case_regressions.append(
                {
                    "case_name": case_name,
                    "reason": "pass_to_fail",
                    "baseline": b,
                    "current": c,
                    "category": category,
                }
            )
            case_pass_failures += 1
            category_pass_failures[category] = category_pass_failures.get(category, 0) + 1

        b_latency = float(b.get("latency_ms", 0.0))
        c_latency = float(c.get("latency_ms", 0.0))
        if b_latency > 0:
            case_latency_pct = ((c_latency - b_latency) / b_latency) * 100.0
        else:
            case_latency_pct = 0.0 if c_latency <= 0 else 100.0
        if case_latency_pct > abs(max_case_latency_regression_pct):
            category = str(b.get("category") or c.get("category") or "uncategorized")
            case_regressions.append(
                {
                    "case_name": case_name,
                    "reason": "latency_regression",
                    "latency_pct": case_latency_pct,
                    "baseline": b,
                    "current": c,
                    "category": category,
                }
            )
            category_latency_regressions[category] = category_latency_regressions.get(category, 0) + 1

    if case_pass_failures > max(0, allow_case_pass_failures):
        regression_reasons.append(
            f"case_pass_failures {case_pass_failures} above allowed {max(0, allow_case_pass_failures)}"
        )
    if any(item.get("reason") == "latency_regression" for item in case_regressions):
        regression_reasons.append("case_latency_regressions detected")

    category_thresholds = category_thresholds or {}
    category_violations: List[str] = []
    for category, rules in category_thresholds.items():
        allowed_failures = int(max(0, float(rules.get("allow_case_pass_failures", 0))))
        actual_failures = category_pass_failures.get(category, 0)
        if actual_failures > allowed_failures:
            category_violations.append(
                f"category={category} pass_failures={actual_failures} allowed={allowed_failures}"
            )

        allowed_latency_pct = float(abs(rules.get("max_case_latency_regression_pct", max_case_latency_regression_pct)))
        category_latency_items = [
            item
            for item in case_regressions
            if item.get("reason") == "latency_regression" and item.get("category") == category
        ]
        exceeded = [
            item
            for item in category_latency_items
            if float(item.get("latency_pct", 0.0)) > allowed_latency_pct
        ]
        if exceeded:
            category_violations.append(
                f"category={category} latency_regressions={len(exceeded)} allowed_pct={allowed_latency_pct:.2f}"
            )

    if category_violations:
        regression_reasons.append("category_threshold_violations detected")

    return {
        "baseline": baseline.to_dict(),
        "current": current.to_dict(),
        "delta": {
            "pass_rate": pass_rate_delta,
            "avg_latency_ms": current.avg_latency_ms - baseline.avg_latency_ms,
            "avg_latency_pct": avg_latency_delta_pct,
            "p95_latency_ms": current.p95_latency_ms - baseline.p95_latency_ms,
            "p95_latency_pct": p95_latency_delta_pct,
        },
        "thresholds": {
            "max_pass_rate_drop": abs(max_pass_rate_drop),
            "max_latency_regression_pct": abs(max_latency_regression_pct),
            "max_case_latency_regression_pct": abs(max_case_latency_regression_pct),
            "allow_case_pass_failures": max(0, allow_case_pass_failures),
            "category_thresholds": category_thresholds,
        },
        "category_metrics": {
            "pass_failures": category_pass_failures,
            "latency_regressions": category_latency_regressions,
            "violations": category_violations,
        },
        "case_regressions": case_regressions,
        "regression": bool(regression_reasons),
        "reasons": regression_reasons,
    }


def markdown_summary(report_payload: Dict[str, Any], comparison: Optional[Dict[str, Any]] = None) -> str:
    bench = report_payload.get("benchmark", {})
    lines = [
        "## NOVUS Benchmark Summary",
        "",
        f"- Pass rate: **{float(bench.get('pass_rate', 0.0)):.2%}**",
        f"- Cases: **{int(bench.get('total', 0))}**",
    ]
    results = bench.get("results", [])
    if results:
        avg = sum(float(r.get("latency_ms", 0.0)) for r in results) / len(results)
        lines.append(f"- Avg latency: **{avg:.2f} ms**")

    if comparison:
        delta = comparison.get("delta", {})
        lines.extend(
            [
                "",
                "### Baseline Delta",
                "",
                f"- Pass rate delta: **{float(delta.get('pass_rate', 0.0)):+.4f}**",
                f"- Avg latency delta: **{float(delta.get('avg_latency_ms', 0.0)):+.2f} ms** ({float(delta.get('avg_latency_pct', 0.0)):+.2f}%)",
                f"- P95 latency delta: **{float(delta.get('p95_latency_ms', 0.0)):+.2f} ms** ({float(delta.get('p95_latency_pct', 0.0)):+.2f}%)",
            ]
        )
        if comparison.get("regression"):
            lines.append("- Regression: **YES**")
            for reason in comparison.get("reasons", []):
                lines.append(f"  - {reason}")
        else:
            lines.append("- Regression: **NO**")
        case_regressions = comparison.get("case_regressions", [])
        if case_regressions:
            lines.append("")
            lines.append("### Case Regressions")
            for item in case_regressions:
                case_name = item.get("case_name", "unknown")
                reason = item.get("reason", "unknown")
                if reason == "latency_regression":
                    pct = float(item.get("latency_pct", 0.0))
                    lines.append(f"- `{case_name}`: latency regression {pct:+.2f}%")
                elif reason == "pass_to_fail":
                    lines.append(f"- `{case_name}`: pass -> fail")
                else:
                    lines.append(f"- `{case_name}`: {reason}")
        violations = comparison.get("category_metrics", {}).get("violations", [])
        if violations:
            lines.append("")
            lines.append("### Category Threshold Violations")
            for item in violations:
                lines.append(f"- {item}")

    return "\n".join(lines) + "\n"
