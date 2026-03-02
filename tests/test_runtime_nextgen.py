"""Tests for next-generation runtime foundations."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from novus.benchmark import compare_snapshots, markdown_summary, snapshot_from_report
from novus.core.agent import Agent
from novus.cli.main import app, run_benchmark_export
from novus.core.models import AgentCapability, AgentConfig, Task, TaskStatus
from novus.runtime.artifacts import RunArtifactLogger
from novus.runtime.context import ContextCompressor
from novus.runtime.exporter import RunExporter
from novus.runtime.loop import RecursiveAgentRuntime
from novus.runtime.manifest import BenchmarkRunManifest, MANIFEST_SCHEMA_VERSION
from novus.runtime.policy import RuntimePolicyEngine
from novus.runtime.replay import RunReplayer
from novus.runtime.state import RuntimeState
from novus.runtime.subagents import SubagentDispatcher, SubagentTask
from novus.runtime.tools import ToolRegistry
from novus.runtime.verifier import RunBundleVerifier
from novus.swarm.orchestrator import SwarmOrchestrator


@pytest.mark.asyncio
async def test_agent_run_fallback_math() -> None:
    agent = Agent(AgentConfig(name="runner", capabilities={AgentCapability.REASONING}))
    out = await agent.run("What is 15 * 23?")
    assert "345" in out


def test_context_compressor() -> None:
    comp = ContextCompressor(threshold_chars=100)
    messages = [{"role": "user", "content": "x" * 90}, {"role": "assistant", "content": "y" * 90}]
    compacted, result = comp.maybe_compact(messages)
    assert result is not None
    assert compacted[0]["role"] == "system"


def test_runtime_state_prompt_block() -> None:
    state = RuntimeState(original_request="test")
    state.ensure_plan("Implement feature")
    block = state.to_prompt_block()
    assert "CURRENT PLAN STATUS" in block
    assert "Implement feature" in block


@pytest.mark.asyncio
async def test_subagent_depth_limit() -> None:
    async def worker(prompt: str) -> str:
        return f"ok: {prompt}"

    dispatcher = SubagentDispatcher(worker=worker, max_depth=1)
    results = await dispatcher.dispatch_many([SubagentTask(name="a", prompt="scan")], depth=0)
    assert len(results) == 1

    with pytest.raises(ValueError):
        await dispatcher.dispatch_many([SubagentTask(name="b", prompt="scan")], depth=1)


@pytest.mark.asyncio
async def test_swarm_tracks_completed_tasks() -> None:
    swarm = SwarmOrchestrator()
    await swarm.start()
    try:
        task = Task(description="hello", required_capabilities={AgentCapability.REASONING})
        await swarm.submit_task(task)

        for _ in range(100):
            if task.id in swarm.completed_tasks:
                break
            await asyncio.sleep(0.05)

        assert task.id in swarm.completed_tasks or task.status in {TaskStatus.RUNNING, TaskStatus.ASSIGNED}
    finally:
        swarm.stop()


def test_tool_registry_validation() -> None:
    registry = ToolRegistry()
    ok = registry.validate("search_web", {"query": "novus", "num_results": 3})
    assert ok.valid is True
    assert ok.normalized_args["num_results"] == 3

    bad = registry.validate("search_web", {"num_results": 0})
    assert bad.valid is False
    assert bad.schema is not None


@pytest.mark.asyncio
async def test_runtime_protocol_error_self_correction() -> None:
    calls = {"n": 0}

    async def fake_llm(prompt: str, model: str | None = None) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return "not json"
        return '{"type":"final","answer":"fixed"}'

    runtime = RecursiveAgentRuntime(llm_caller=fake_llm)
    out = await runtime.run("Say fixed")
    assert out == "fixed"


@pytest.mark.asyncio
async def test_runtime_tool_validation_error_self_correction() -> None:
    calls = {"n": 0}

    async def fake_llm(prompt: str, model: str | None = None) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return '{"type":"tool_call","tool":"search_web","args":{"num_results":0}}'
        return '{"type":"final","answer":"recovered"}'

    runtime = RecursiveAgentRuntime(llm_caller=fake_llm)
    out = await runtime.run("recover from validation")
    assert out == "recovered"


@pytest.mark.asyncio
async def test_runtime_executes_multiple_tool_calls_in_order() -> None:
    call_num = {"n": 0}

    async def fake_llm(prompt: str, model: str | None = None) -> str:
        call_num["n"] += 1
        if call_num["n"] == 1:
            return (
                '{"tool_calls": ['
                '{"tool":"search_web","args":{"query":"alpha","num_results":1}},'
                '{"tool":"search_web","args":{"query":"beta","num_results":1}}'
                "],\"type\":\"tool_call\"}"
            )
        return '{"type":"final","answer":"done"}'

    runtime = RecursiveAgentRuntime(llm_caller=fake_llm)
    out = await runtime.run("run two tools")
    assert out == "done"


@pytest.mark.asyncio
async def test_multi_tool_results_are_deterministically_sorted() -> None:
    async def fake_llm(prompt: str, model: str | None = None) -> str:
        return '{"type":"final","answer":"unused"}'

    runtime = RecursiveAgentRuntime(llm_caller=fake_llm, max_parallel_tools=3)

    async def fake_execute(tool: str, args: dict) -> dict:
        if args.get("delay"):
            await asyncio.sleep(args["delay"])
        return {"tool": tool, "id": args.get("id")}

    runtime._execute_tool = fake_execute  # type: ignore[method-assign]
    calls = [
        (0, "search_web", {"id": "a", "delay": 0.06}),
        (1, "search_web", {"id": "b", "delay": 0.01}),
        (2, "search_web", {"id": "c", "delay": 0.02}),
    ]
    results = await runtime._execute_tool_calls(calls)
    assert [r["index"] for r in results] == [0, 1, 2]
    assert [r["result"]["id"] for r in results] == ["a", "b", "c"]


def test_policy_engine_risk_decision() -> None:
    engine = RuntimePolicyEngine()
    low = engine.evaluate("search_web", {"query": "x", "num_results": 1})
    high = engine.evaluate("execute_code", {"code": "print(1)"})

    assert low.allowed is True
    assert low.risk == "low"
    assert high.allowed is False
    assert high.action == "escalate"


@pytest.mark.asyncio
async def test_runtime_policy_violation_self_correction() -> None:
    calls = {"n": 0}

    async def fake_llm(prompt: str, model: str | None = None) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return '{"type":"tool_call","tool":"execute_code","args":{"code":"print(1)"}}'
        return '{"type":"final","answer":"policy-respected"}'

    runtime = RecursiveAgentRuntime(
        llm_caller=fake_llm,
        policy_engine=RuntimePolicyEngine(block_high_risk_without_approval=True),
    )
    out = await runtime.run("do something safely")
    assert out == "policy-respected"


@pytest.mark.asyncio
async def test_runtime_writes_artifacts_and_replays_summary(tmp_path: Path) -> None:
    async def fake_llm(prompt: str, model: str | None = None) -> str:
        return '{"type":"final","answer":"artifact-ok"}'

    logger = RunArtifactLogger(run_dir=tmp_path / "runs")
    runtime = RecursiveAgentRuntime(llm_caller=fake_llm, artifact_logger=logger)
    out = await runtime.run("artifact test")
    assert out == "artifact-ok"
    assert runtime.last_session_id is not None

    events = logger.read(runtime.last_session_id)
    assert len(events) >= 2  # start + final/end

    summary = RunReplayer().summarize(runtime.last_session_id, events)
    assert summary.session_id == runtime.last_session_id
    assert summary.total_events >= 2
    assert summary.final_answer == "artifact-ok"


@pytest.mark.asyncio
async def test_run_export_bundle_contains_manifest_and_events(tmp_path: Path) -> None:
    async def fake_llm(prompt: str, model: str | None = None) -> str:
        return '{"type":"final","answer":"export-ok"}'

    run_dir = tmp_path / "runs"
    state_dir = tmp_path / "sessions"
    export_dir = tmp_path / "exports"

    logger = RunArtifactLogger(run_dir=run_dir)
    runtime = RecursiveAgentRuntime(llm_caller=fake_llm, artifact_logger=logger, state_dir=state_dir)
    out = await runtime.run("export test")
    assert out == "export-ok"
    assert runtime.last_session_id is not None

    exporter = RunExporter(artifact_logger=logger, state_dir=state_dir, export_dir=export_dir)
    bundle = exporter.export(runtime.last_session_id)

    assert bundle.manifest_path.exists()
    assert bundle.events_path.exists()

    manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
    parsed_manifest = BenchmarkRunManifest.model_validate(manifest)
    assert manifest["session_id"] == runtime.last_session_id
    assert manifest["event_count"] >= 2
    assert manifest["checksums"]["events_sha256"]
    assert parsed_manifest.schema_version == MANIFEST_SCHEMA_VERSION
    assert parsed_manifest.provenance.novus_version
    assert len(parsed_manifest.provenance.dependency_fingerprint) == 64


@pytest.mark.asyncio
async def test_run_export_bundle_includes_signature_when_key_set(tmp_path: Path) -> None:
    async def fake_llm(prompt: str, model: str | None = None) -> str:
        return '{"type":"final","answer":"signed-ok"}'

    run_dir = tmp_path / "runs"
    state_dir = tmp_path / "sessions"
    export_dir = tmp_path / "exports"
    logger = RunArtifactLogger(run_dir=run_dir)
    runtime = RecursiveAgentRuntime(llm_caller=fake_llm, artifact_logger=logger, state_dir=state_dir)
    await runtime.run("signed export")

    exporter = RunExporter(
        artifact_logger=logger,
        state_dir=state_dir,
        export_dir=export_dir,
        signing_key="test-secret",
    )
    bundle = exporter.export(runtime.last_session_id)
    manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
    parsed = BenchmarkRunManifest.model_validate(manifest)
    assert parsed.signature is not None
    assert parsed.signature.algorithm == "hmac-sha256"


@pytest.mark.asyncio
async def test_run_bundle_verifier_passes_for_valid_bundle(tmp_path: Path) -> None:
    async def fake_llm(prompt: str, model: str | None = None) -> str:
        return '{"type":"final","answer":"verify-ok"}'

    run_dir = tmp_path / "runs"
    state_dir = tmp_path / "sessions"
    export_dir = tmp_path / "exports"
    logger = RunArtifactLogger(run_dir=run_dir)
    runtime = RecursiveAgentRuntime(llm_caller=fake_llm, artifact_logger=logger, state_dir=state_dir)
    await runtime.run("verify test")

    exporter = RunExporter(
        artifact_logger=logger,
        state_dir=state_dir,
        export_dir=export_dir,
        signing_key="secret",
    )
    bundle = exporter.export(runtime.last_session_id)
    result = RunBundleVerifier().verify(bundle.bundle_dir, signing_key="secret")
    assert result.ok is True
    assert result.checksum_ok is True
    assert result.signature_ok is True


@pytest.mark.asyncio
async def test_run_bundle_verifier_fails_for_tampered_events(tmp_path: Path) -> None:
    async def fake_llm(prompt: str, model: str | None = None) -> str:
        return '{"type":"final","answer":"verify-fail"}'

    run_dir = tmp_path / "runs"
    state_dir = tmp_path / "sessions"
    export_dir = tmp_path / "exports"
    logger = RunArtifactLogger(run_dir=run_dir)
    runtime = RecursiveAgentRuntime(llm_caller=fake_llm, artifact_logger=logger, state_dir=state_dir)
    await runtime.run("verify tamper")

    exporter = RunExporter(
        artifact_logger=logger,
        state_dir=state_dir,
        export_dir=export_dir,
    )
    bundle = exporter.export(runtime.last_session_id)
    # Tamper after export to force checksum mismatch.
    with bundle.events_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"event_type": "tamper", "payload": {"x": 1}}) + "\\n")

    result = RunBundleVerifier().verify(bundle.bundle_dir)
    assert result.ok is False
    assert result.checksum_ok is False
    assert "events checksum mismatch" in result.errors


@pytest.mark.asyncio
async def test_run_benchmark_export_generates_verified_bundles(tmp_path: Path) -> None:
    payload = await run_benchmark_export(output_dir=tmp_path / "bench", signing_key="bench-key")
    assert payload["benchmark"]["total"] >= 1
    assert payload["summary"]["sessions"] >= 1
    assert payload["summary"]["verification_failures"] == 0

    report_path = tmp_path / "bench" / "benchmark_report.json"
    assert report_path.exists()

    report_data = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_data["summary"]["verification_failures"] == 0


@pytest.mark.asyncio
async def test_run_benchmark_export_with_baseline_and_summary(tmp_path: Path) -> None:
    baseline_snapshot_path = tmp_path / "baseline_snapshot.json"
    baseline_snapshot_path.write_text(
        json.dumps(
            {
                "pass_rate": 1.0,
                "total": 2,
                "avg_latency_ms": 10.0,
                "p95_latency_ms": 12.0,
                "timestamp": "2026-03-02T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    summary_path = tmp_path / "bench" / "summary.md"
    snapshot_path = tmp_path / "bench" / "current_snapshot.json"

    payload = await run_benchmark_export(
        output_dir=tmp_path / "bench",
        signing_key="bench-key",
        baseline_path=baseline_snapshot_path,
        summary_md_path=summary_path,
        snapshot_path=snapshot_path,
        max_pass_rate_drop=0.5,
        max_latency_regression_pct=1000.0,
    )

    assert payload["comparison"]["baseline"]["pass_rate"] == 1.0
    assert summary_path.exists()
    assert "NOVUS Benchmark Summary" in summary_path.read_text(encoding="utf-8")
    assert snapshot_path.exists()


def test_benchmark_trend_compare_and_markdown() -> None:
    payload = {
        "benchmark": {
            "pass_rate": 0.5,
            "total": 2,
            "results": [
                {"latency_ms": 10.0},
                {"latency_ms": 30.0},
            ],
        }
    }
    current = snapshot_from_report(payload, commit="abc")
    baseline = snapshot_from_report(
        {
            "benchmark": {
                "pass_rate": 1.0,
                "total": 2,
                "results": [{"latency_ms": 10.0}, {"latency_ms": 10.0}],
            }
        },
        commit="def",
    )
    comparison = compare_snapshots(
        baseline=baseline,
        current=current,
        max_pass_rate_drop=0.1,
        max_latency_regression_pct=50.0,
    )
    assert comparison["regression"] is True
    md = markdown_summary(payload, comparison=comparison)
    assert "Regression: **YES**" in md


def test_benchmark_case_level_regression_detection() -> None:
    baseline = snapshot_from_report(
        {
            "benchmark": {
                "pass_rate": 1.0,
                "total": 2,
                "results": [
                    {"case_name": "arithmetic", "passed": True, "latency_ms": 10.0},
                    {"case_name": "addition", "passed": True, "latency_ms": 10.0},
                ],
            }
        }
    )
    current = snapshot_from_report(
        {
            "benchmark": {
                "pass_rate": 0.5,
                "total": 2,
                "results": [
                    {"case_name": "arithmetic", "passed": False, "latency_ms": 12.0},
                    {"case_name": "addition", "passed": True, "latency_ms": 80.0},
                ],
            }
        }
    )

    comparison = compare_snapshots(
        baseline=baseline,
        current=current,
        max_pass_rate_drop=0.01,
        max_latency_regression_pct=500.0,
        max_case_latency_regression_pct=100.0,
        allow_case_pass_failures=0,
    )
    assert comparison["regression"] is True
    reasons = " ".join(comparison["reasons"])
    assert "case_pass_failures" in reasons
    assert "case_latency_regressions" in reasons
    case_reasons = {item["reason"] for item in comparison["case_regressions"]}
    assert "pass_to_fail" in case_reasons
    assert "latency_regression" in case_reasons


def test_benchmark_category_threshold_violations() -> None:
    baseline = snapshot_from_report(
        {
            "benchmark": {
                "pass_rate": 1.0,
                "total": 2,
                "results": [
                    {"case_name": "arithmetic", "passed": True, "latency_ms": 10.0, "category": "core_reasoning"},
                    {"case_name": "addition", "passed": True, "latency_ms": 10.0, "category": "core_reasoning"},
                ],
            }
        }
    )
    current = snapshot_from_report(
        {
            "benchmark": {
                "pass_rate": 0.5,
                "total": 2,
                "results": [
                    {"case_name": "arithmetic", "passed": False, "latency_ms": 50.0, "category": "core_reasoning"},
                    {"case_name": "addition", "passed": True, "latency_ms": 60.0, "category": "core_reasoning"},
                ],
            }
        }
    )
    comparison = compare_snapshots(
        baseline=baseline,
        current=current,
        max_pass_rate_drop=0.8,
        max_latency_regression_pct=1000.0,
        max_case_latency_regression_pct=1000.0,
        allow_case_pass_failures=5,
        category_thresholds={
            "core_reasoning": {
                "allow_case_pass_failures": 0,
                "max_case_latency_regression_pct": 200.0,
            }
        },
    )
    assert comparison["regression"] is True
    assert "category_threshold_violations detected" in comparison["reasons"]
    assert comparison["category_metrics"]["violations"]


def test_benchmark_snapshot_save_and_load(tmp_path: Path) -> None:
    report_payload = {
        "benchmark": {
            "pass_rate": 1.0,
            "total": 2,
            "results": [{"latency_ms": 12.0}, {"latency_ms": 24.0}],
        },
        "git": {"commit": "abc123"},
    }
    snap = snapshot_from_report(report_payload, commit="abc123")
    snapshot_path = tmp_path / "snap.json"

    from novus.benchmark import load_snapshot, save_snapshot

    save_snapshot(snapshot_path, snap)
    loaded = load_snapshot(snapshot_path)

    assert loaded.pass_rate == snap.pass_rate
    assert loaded.total == snap.total
    assert loaded.commit == "abc123"
    assert "case_0" in (loaded.case_details or {})


def test_readiness_writes_success_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], capture_output: bool = False) -> SimpleNamespace:
        calls.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("novus.cli.main.subprocess.run", fake_run)
    report_path = tmp_path / "readiness.json"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "readiness",
            "--output-dir",
            str(tmp_path / "bench"),
            "--baseline",
            ".github/benchmarks/baseline_snapshot.json",
            "--category-thresholds",
            ".github/benchmarks/category_thresholds.json",
            "--signing-key",
            "s",
            "--no-fail-on-regression",
            "--skip-tests",
            "--report-json",
            str(report_path),
        ],
    )
    assert result.exit_code == 0

    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["ok"] is True
    assert len(data["steps"]) == 2
    assert "--signing-key" in calls[0]
    assert "--no-fail-on-regression" in calls[1]


def test_readiness_writes_failure_report_and_exits(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_run(cmd: list[str], capture_output: bool = False) -> SimpleNamespace:
        return SimpleNamespace(returncode=2)

    monkeypatch.setattr("novus.cli.main.subprocess.run", fake_run)
    report_path = tmp_path / "readiness_fail.json"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "readiness",
            "--output-dir",
            str(tmp_path / "bench"),
            "--skip-tests",
            "--skip-benchmark-evaluate",
            "--report-json",
            str(report_path),
        ],
    )
    assert result.exit_code == 2

    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["ok"] is False
    assert data["steps"][0]["exit_code"] == 2
