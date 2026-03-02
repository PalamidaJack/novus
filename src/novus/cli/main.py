"""
NOVUS CLI.

Command-line interface for interacting with NOVUS.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional
import structlog

import typer
import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

from novus.swarm.orchestrator import SwarmOrchestrator
from novus.benchmark import (
    BenchmarkHarness,
    compare_snapshots,
    default_cases,
    load_snapshot,
    markdown_summary,
    save_snapshot,
    snapshot_from_report,
)
from novus.core.agent import Agent
from novus.core.models import AgentConfig, SwarmConfig, AgentCapability
from novus.world_model.engine import WorldModel, WorldModelPlanner
from novus.runtime.artifacts import RunArtifactLogger
from novus.runtime.exporter import RunExporter
from novus.runtime.replay import RunReplayer
from novus.runtime.verifier import RunBundleVerifier

# Rich console
console = Console()

# Create app
app = typer.Typer(
    name="novus",
    help="NOVUS: Next-Generation Agentic AI Platform",
    add_completion=False
)

logger = structlog.get_logger()


async def run_benchmark_export(
    output_dir: Path,
    signing_key: Optional[str] = None,
    baseline_path: Optional[Path] = None,
    summary_md_path: Optional[Path] = None,
    snapshot_path: Optional[Path] = None,
    max_pass_rate_drop: float = 0.05,
    max_latency_regression_pct: float = 200.0,
    max_case_latency_regression_pct: float = 300.0,
    allow_case_pass_failures: int = 0,
    category_thresholds_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Run default benchmark cases, export bundles, and verify reproducibility."""
    output_dir.mkdir(parents=True, exist_ok=True)
    bundles_dir = output_dir / "bundles"
    bundles_dir.mkdir(parents=True, exist_ok=True)

    agent = Agent(AgentConfig(name="BenchmarkAgent"))
    seen_sessions: list[str] = []

    async def runner(prompt: str) -> str:
        out = await agent.run(prompt)
        session_id = agent.get_last_session_id()
        if session_id:
            seen_sessions.append(session_id)
        return out

    harness = BenchmarkHarness(runner=runner)
    report = await harness.run(default_cases())

    exporter = RunExporter(export_dir=bundles_dir, signing_key=signing_key)
    verifier = RunBundleVerifier()
    export_results: list[dict[str, Any]] = []
    verification_failures = 0

    unique_sessions = list(dict.fromkeys(seen_sessions))
    for session_id in unique_sessions:
        exported = exporter.export(session_id)
        verification = verifier.verify(exported.bundle_dir, signing_key=signing_key)
        if not verification.ok:
            verification_failures += 1
        export_results.append(
            {
                "session_id": session_id,
                "bundle_dir": str(exported.bundle_dir),
                "manifest_path": str(exported.manifest_path),
                "events_path": str(exported.events_path),
                "state_path": str(exported.state_path) if exported.state_path else None,
                "verification": {
                    "ok": verification.ok,
                    "checksum_ok": verification.checksum_ok,
                    "signature_ok": verification.signature_ok,
                    "errors": verification.errors,
                },
            }
        )

    payload: dict[str, Any] = {
        "benchmark": {
            "pass_rate": report.pass_rate,
            "total": len(report.results),
            "results": [
                {
                    "case_name": r.case_name,
                    "category": r.category,
                    "passed": r.passed,
                    "latency_ms": r.latency_ms,
                    "output": r.output,
                }
                for r in report.results
            ],
        },
        "exports": export_results,
        "summary": {
            "sessions": len(unique_sessions),
            "verification_failures": verification_failures,
        },
        "git": {
            "commit": os.getenv("GITHUB_SHA"),
        },
    }

    current_snapshot = snapshot_from_report(payload, commit=payload["git"]["commit"])
    payload["snapshot"] = current_snapshot.to_dict()

    comparison: Optional[dict[str, Any]] = None
    category_thresholds: Optional[dict[str, dict[str, float]]] = None
    if category_thresholds_path and category_thresholds_path.exists():
        category_thresholds = json.loads(category_thresholds_path.read_text(encoding="utf-8"))

    if baseline_path and baseline_path.exists():
        baseline_snapshot = load_snapshot(baseline_path)
        comparison = compare_snapshots(
            baseline=baseline_snapshot,
            current=current_snapshot,
            max_pass_rate_drop=max_pass_rate_drop,
            max_latency_regression_pct=max_latency_regression_pct,
            max_case_latency_regression_pct=max_case_latency_regression_pct,
            allow_case_pass_failures=allow_case_pass_failures,
            category_thresholds=category_thresholds,
        )
        payload["comparison"] = comparison

    if snapshot_path:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(json.dumps(current_snapshot.to_dict(), indent=2), encoding="utf-8")

    report_path = output_dir / "benchmark_report.json"
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if summary_md_path:
        summary_md_path.parent.mkdir(parents=True, exist_ok=True)
        summary_md_path.write_text(markdown_summary(payload, comparison), encoding="utf-8")
    return payload


@app.command()
def start(
    agents: int = typer.Option(5, "--agents", "-a", help="Number of agents to start"),
    port: int = typer.Option(8000, "--port", "-p", help="API server port"),
    host: str = typer.Option("0.0.0.0", "--host", help="API server host"),
    evolve: bool = typer.Option(False, "--evolve", help="Enable evolutionary optimization"),
):
    """Start the NOVUS API server."""
    from novus.api.server import app as fastapi_app
    import uvicorn
    
    console.print(f"[bold green]Starting NOVUS with {agents} agents...[/bold green]")
    
    # Run server
    uvicorn.run(
        fastapi_app,
        host=host,
        port=port,
        log_level="info"
    )


@app.command()
def swarm(
    agents: int = typer.Option(5, "--agents", "-a", help="Number of agents"),
    problem: str = typer.Option(..., "--problem", "-p", help="Problem to solve"),
    evolve: bool = typer.Option(False, "--evolve", help="Enable evolution"),
):
    """Solve a problem using swarm intelligence."""
    
    async def _run():
        config = SwarmConfig(
            target_agent_count=agents,
            enable_evolution=evolve
        )
        
        swarm = SwarmOrchestrator(config)
        await swarm.start()
        
        console.print(f"[bold]Solving:[/bold] {problem}")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Running swarm...", total=None)
            
            solution = await swarm.collective_solve(
                problem=problem,
                n_agents=min(agents, 5)
            )
        
        console.print("\n[bold green]Solution:[/bold green]")
        console.print(solution.content)
        console.print(f"\n[bold]Confidence:[/bold] {solution.confidence:.2%}")
        console.print(f"[bold]Generated by:[/bold] {solution.generated_by}")
        
        swarm.stop()
    
    asyncio.run(_run())


@app.command()
def status():
    """Show NOVUS system status."""
    
    async def _run():
        config = SwarmConfig(target_agent_count=3)
        swarm = SwarmOrchestrator(config)
        await swarm.start()
        
        status = swarm.get_status()
        
        # Display status
        table = Table(title="NOVUS Swarm Status")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Population", str(status["population"]))
        table.add_row("Generation", str(status["generation"]))
        table.add_row("Pending Tasks", str(status["pending_tasks"]))
        table.add_row("Active Tasks", str(status["active_tasks"]))
        table.add_row("Completed Tasks", str(status["completed_tasks"]))
        
        console.print(table)
        
        # Agent details
        if status["agents"]:
            agent_table = Table(title="Agents")
            agent_table.add_column("Name", style="cyan")
            agent_table.add_column("Status", style="green")
            agent_table.add_column("Active Tasks", style="yellow")
            agent_table.add_column("Fitness", style="magenta")
            
            for agent_id, info in status["agents"].items():
                agent_table.add_row(
                    info["name"],
                    info["status"],
                    str(info["active_tasks"]),
                    f"{info['fitness']:.2f}"
                )
            
            console.print(agent_table)
        
        swarm.stop()
    
    asyncio.run(_run())


@app.command()
def plan(
    goal: str = typer.Option(..., "--goal", "-g", help="Goal state as JSON"),
    initial: str = typer.Option(..., "--initial", "-i", help="Initial state as JSON"),
    max_steps: int = typer.Option(10, "--max-steps", help="Maximum plan length"),
):
    """Plan using world model simulation."""
    import json
    
    async def _run():
        try:
            goal_state = json.loads(goal)
            initial_state = json.loads(initial)
        except json.JSONDecodeError as e:
            console.print(f"[bold red]Error:[/bold red] Invalid JSON: {e}")
            raise typer.Exit(1)
        
        world_model = WorldModel()
        planner = WorldModelPlanner(world_model)
        
        console.print("[bold]Planning...[/bold]")
        
        result = await planner.plan(
            goal_state=goal_state,
            initial_state=initial_state,
            max_plan_length=max_steps
        )
        
        console.print(f"\n[bold green]Best Plan Score:[/bold green] {result['best_score']:.2f}")
        console.print(f"\n[bold]Best Plan:[/bold]")
        
        for i, action in enumerate(result["best_plan"], 1):
            console.print(f"  {i}. {action.get('type', 'unknown')}")
        
        if result["alternatives"]:
            console.print(f"\n[bold]Top Alternatives:[/bold]")
            for i, alt in enumerate(result["alternatives"][:3], 1):
                console.print(f"  {i}. Score: {alt['score']:.2f}")
    
    asyncio.run(_run())


@app.command()
def onboard(
    quick: bool = typer.Option(False, "--quick", "-q", help="QuickStart mode (defaults)"),
    advanced: bool = typer.Option(False, "--advanced", "-a", help="Advanced mode (full control)"),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Non-interactive mode"),
):
    """Interactive onboarding wizard - setup NOVUS with guided configuration."""
    from pathlib import Path
    import os
    
    console.print("[bold green]╔══════════════════════════════════════════╗[/bold green]")
    console.print("[bold green]║         NOVUS Onboarding Wizard          ║[/bold green]")
    console.print("[bold green]╚══════════════════════════════════════════╝[/bold green]")
    console.print()
    
    # Determine mode
    if non_interactive:
        mode = "quickstart"
    elif quick:
        mode = "quickstart"
    elif advanced:
        mode = "advanced"
    else:
        mode = typer.prompt(
            "Choose setup mode",
            type=click.Choice(["quickstart", "advanced"], case_sensitive=False),
            default="quickstart"
        )
    
    # Create NOVUS home directory
    novus_home = Path.home() / ".novus"
    novus_home.mkdir(exist_ok=True)
    
    # Create subdirectories
    dirs = ["knowledge", "logs", "cache", "sessions", "agents", "configs"]
    for d in dirs:
        (novus_home / d).mkdir(exist_ok=True)
    
    console.print(f"\n[bold]Step 1: Workspace[/bold]")
    console.print(f"Created directories: {', '.join(dirs)}")
    
    # Step 2: Identity (all modes)
    console.print(f"\n[bold]Step 2: Identity[/bold]")
    if non_interactive:
        name = "User"
        email = "user@example.com"
    else:
        name = typer.prompt("Your name", default="User")
        email = typer.prompt("Your email", default="user@example.com")
    
    # Step 3: API Keys (critical for functionality)
    console.print(f"\n[bold]Step 3: API Configuration[/bold]")
    console.print("[yellow]⚠️  API keys are required for NOVUS to function[/yellow]")
    
    api_keys = {}
    
    if mode == "advanced" or non_interactive:
        # Collect all provider keys in advanced mode
        providers = ["openai", "anthropic", "deepseek", "groq"]
        
        for provider in providers:
            env_var = f"{provider.upper()}_API_KEY"
            existing = os.environ.get(env_var)
            
            if existing:
                console.print(f"  ✓ {provider}: Found in environment ({env_var})")
                api_keys[provider] = existing
            elif non_interactive:
                console.print(f"  ⚠ {provider}: Not set (set {env_var} env var)")
            else:
                key = typer.prompt(
                    f"{provider.upper()} API key (optional, press Enter to skip)",
                    default="",
                    show_default=False,
                    hide_input=True
                )
                if key:
                    api_keys[provider] = key
                    console.print(f"  ✓ {provider}: Configured")
    else:
        # QuickStart - just get one key to get started
        console.print("\n[bold]Primary LLM Provider[/bold]")
        console.print("Choose your main AI provider (you can add more later):")
        
        provider = typer.prompt(
            "Provider",
            type=click.Choice(["openai", "anthropic", "skip"], case_sensitive=False),
            default="openai"
        )
        
        if provider != "skip":
            key = typer.prompt(
                f"{provider.upper()} API key",
                hide_input=True
            )
            if key:
                api_keys[provider] = key
                console.print(f"  ✓ {provider}: API key configured")
    
    # Store API keys securely
    if api_keys:
        keys_file = novus_home / "api-keys.yaml"
        with open(keys_file, "w") as f:
            f.write("# NOVUS API Keys\n")
            f.write("# IMPORTANT: Keep this file secure!\n\n")
            for provider, key in api_keys.items():
                # In production, these should be encrypted
                f.write(f"{provider}: \"{key[:8]}...{key[-4:]}\"\n")
        
        # Also create environment setup script
        env_file = novus_home / "env.sh"
        with open(env_file, "w") as f:
            f.write("#!/bin/bash\n# NOVUS Environment Setup\n\n")
            for provider, key in api_keys.items():
                f.write(f"export {provider.upper()}_API_KEY=\"{key}\"\n")
        os.chmod(env_file, 0o600)
        
        console.print(f"\n[green]API keys saved to {keys_file}[/green]")
        console.print(f"[dim]Environment script: {env_file}[/dim]")
    
    # Step 4: Preferences
    console.print(f"\n[bold]Step 4: Preferences[/bold]")
    if non_interactive:
        style = "direct"
        risk = "medium"
        auto_approve = False
    else:
        style = typer.prompt(
            "Communication style",
            type=click.Choice(["direct", "detailed", "casual"], case_sensitive=False),
            default="direct"
        )
        risk = typer.prompt(
            "Risk tolerance",
            type=click.Choice(["low", "medium", "high"], case_sensitive=False),
            default="medium"
        )
        auto_approve = typer.confirm("Auto-approve low-risk actions?", default=False)
    
    # Create identity file
    identity = f"""# NOVUS Identity
user:
  name: "{name}"
  email: "{email}"
  timezone: "UTC"

preferences:
  communication_style: "{style}"
  risk_tolerance: "{risk}"
  auto_approve: {str(auto_approve).lower()}

safety:
  require_approval_for:
    - code_execution
    - network_calls
    - file_deletion
    - external_api_calls
  auto_approve_below_cost: 0.50
"""
    
    identity_file = novus_home / "identity.yaml"
    with open(identity_file, "w") as f:
        f.write(identity)
    
    console.print(f"\n[green]✓ Identity saved: {identity_file}[/green]")
    
    # Step 5: Advanced settings (advanced mode only)
    if mode == "advanced" and not non_interactive:
        console.print(f"\n[bold]Step 5: Advanced Settings[/bold]")
        
        swarm_size = typer.prompt(
            "Default swarm size (number of agents)",
            type=int,
            default=5
        )
        
        enable_evolution = typer.confirm(
            "Enable agent evolution?",
            default=False
        )
        
        enable_guardrails = typer.confirm(
            "Enable safety guardrails?",
            default=True
        )
        
        # Write advanced config
        config_file = novus_home / "config.yaml"
        config_content = f"""# NOVUS Configuration
swarm:
  target_agent_count: {swarm_size}
  enable_evolution: {str(enable_evolution).lower()}

safety:
  enable_guardrails: {str(enable_guardrails).lower()}
  max_execution_time: 30
  allow_code_execution: true

memory:
  max_entries: 10000
  enable_engram: true
"""
        with open(config_file, "w") as f:
            f.write(config_content)
        
        console.print(f"[green]✓ Config saved: {config_file}[/green]")
    
    # Step 6: Health check
    console.print(f"\n[bold]Step 6: Health Check[/bold]")
    
    checks = []
    
    # Check Python version
    import sys
    py_version = sys.version_info
    py_ok = py_version >= (3, 11)
    checks.append(("Python 3.11+", "✅" if py_ok else "❌"))
    
    # Check directories
    checks.append(("Config directory", "✅"))
    
    # Check identity
    checks.append(("Identity file", "✅"))
    
    # Check API keys
    has_keys = len(api_keys) > 0
    checks.append(("API keys configured", "✅" if has_keys else "⚠️ "))
    
    # Check optional dependencies
    try:
        import fastapi
        checks.append(("FastAPI", "✅"))
    except ImportError:
        checks.append(("FastAPI", "❌"))
    
    try:
        import playwright
        checks.append(("Playwright (optional)", "✅"))
    except ImportError:
        checks.append(("Playwright (optional)", "⚠️ "))
    
    for check, status in checks:
        console.print(f"  {status} {check}")
    
    # Final summary
    console.print(f"\n[bold green]╔══════════════════════════════════════════╗[/bold green]")
    console.print(f"[bold green]║     Onboarding Complete! 🎉              ║[/bold green]")
    console.print(f"[bold green]╚══════════════════════════════════════════╝[/bold green]")
    console.print()
    console.print(f"[dim]Configuration directory:[/dim] {novus_home}")
    console.print()
    console.print("[bold]Next steps:[/bold]")
    
    if not has_keys:
        console.print("  1. [yellow]Set API keys:[/yellow]")
        console.print("     export OPENAI_API_KEY=sk-...")
        console.print("     export ANTHROPIC_API_KEY=sk-ant-...")
    else:
        console.print("  1. Source environment: source ~/.novus/env.sh")
    
    console.print("  2. Test installation: novus doctor")
    console.print("  3. Run first task: novus swarm 'What is 15 * 23?'")
    console.print("  4. Start API server: novus start")
    console.print()
    console.print("[dim]Documentation: https://docs.novus.ai[/dim]")
    console.print("[dim]Support: https://discord.gg/novus[/dim]")


@app.command()
def init():
    """Initialize a new NOVUS project (legacy, use 'onboard' instead)."""
    console.print("[yellow]⚠️  'novus init' is deprecated.[/yellow]")
    console.print("[yellow]   Use 'novus onboard' instead.[/yellow]")
    onboard(quick=True, non_interactive=True)


@app.command("doctor")
def doctor():
    """Run environment diagnostics for local testing readiness."""
    checks: list[tuple[str, str, str]] = []

    py_ok = sys.version_info >= (3, 11)
    checks.append(("Python >= 3.11", "PASS" if py_ok else "FAIL", sys.version.split()[0]))

    for mod in ["pytest", "fastapi", "pydantic", "typer"]:
        present = importlib.util.find_spec(mod) is not None
        checks.append((f"Dependency: {mod}", "PASS" if present else "FAIL", "installed" if present else "missing"))

    for path in [".github/benchmarks/baseline_snapshot.json", ".github/benchmarks/category_thresholds.json"]:
        exists = Path(path).exists()
        checks.append((f"File: {path}", "PASS" if exists else "FAIL", "present" if exists else "missing"))

    api_key_present = bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))
    checks.append(
        (
            "LLM API key",
            "PASS" if api_key_present else "WARN",
            "configured" if api_key_present else "not set (offline fallback still works for smoke tests)",
        )
    )

    table = Table(title="NOVUS Doctor")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Detail", style="white")
    for name, status, detail in checks:
        color = "green" if status == "PASS" else ("yellow" if status == "WARN" else "red")
        table.add_row(name, f"[{color}]{status}[/{color}]", detail)
    console.print(table)

    if any(status == "FAIL" for _, status, _ in checks):
        raise typer.Exit(1)


@app.command("readiness")
def readiness(
    output_dir: str = typer.Option(".novus-bench", "--output-dir", help="Benchmark output directory"),
    baseline: str = typer.Option(
        ".github/benchmarks/baseline_snapshot.json",
        "--baseline",
        help="Baseline snapshot/report JSON path",
    ),
    category_thresholds: str = typer.Option(
        ".github/benchmarks/category_thresholds.json",
        "--category-thresholds",
        help="Category thresholds JSON path",
    ),
    signing_key: str = typer.Option("", "--signing-key", help="Optional HMAC signing key for bundle export"),
    fail_on_regression: bool = typer.Option(
        True, "--fail-on-regression/--no-fail-on-regression", help="Fail readiness if regression is detected"
    ),
    skip_tests: bool = typer.Option(False, "--skip-tests", help="Skip pytest step"),
    skip_benchmark_export: bool = typer.Option(False, "--skip-benchmark-export", help="Skip benchmark export step"),
    skip_benchmark_evaluate: bool = typer.Option(False, "--skip-benchmark-evaluate", help="Skip benchmark evaluate step"),
    report_json: str = typer.Option("", "--report-json", help="Optional JSON report output path"),
):
    """Run local readiness pipeline: tests + benchmark export + benchmark evaluation."""
    steps: list[tuple[str, list[str]]] = []
    if not skip_tests:
        steps.append(("Pytest", [sys.executable, "-m", "pytest", "-q"]))
    if not skip_benchmark_export:
        export_cmd = [
            sys.executable,
            "-m",
            "novus.cli",
            "benchmark-export",
            "--output-dir",
            output_dir,
            "--baseline",
            baseline,
            "--category-thresholds",
            category_thresholds,
            "--summary-md",
            f"{output_dir}/summary.md",
            "--snapshot-out",
            f"{output_dir}/current_snapshot.json",
        ]
        if signing_key:
            export_cmd.extend(["--signing-key", signing_key])
        steps.append(
            (
                "Benchmark Export",
                export_cmd,
            )
        )
    if not skip_benchmark_evaluate:
        eval_cmd = [
            sys.executable,
            "-m",
            "novus.cli",
            "benchmark-evaluate",
            "--report",
            f"{output_dir}/benchmark_report.json",
            "--baseline",
            baseline,
            "--category-thresholds",
            category_thresholds,
        ]
        eval_cmd.append("--fail-on-regression" if fail_on_regression else "--no-fail-on-regression")
        steps.append(
            (
                "Benchmark Evaluate",
                eval_cmd,
            )
        )

    if not steps:
        console.print("[yellow]No readiness steps selected.[/yellow]")
        return

    started_at = time.time()
    step_reports: list[dict[str, Any]] = []

    for name, cmd in steps:
        console.print(f"[bold]Running:[/bold] {name}")
        step_start = time.time()
        result = subprocess.run(cmd, capture_output=False)
        step_reports.append(
            {
                "name": name,
                "command": cmd,
                "exit_code": int(result.returncode),
                "duration_seconds": time.time() - step_start,
            }
        )
        if result.returncode != 0:
            console.print(f"[bold red]{name} failed with exit code {result.returncode}[/bold red]")
            if report_json:
                out_path = Path(report_json)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(
                    json.dumps(
                        {
                            "ok": False,
                            "output_dir": output_dir,
                            "duration_seconds": time.time() - started_at,
                            "steps": step_reports,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            raise typer.Exit(result.returncode)

    console.print("[bold green]Readiness pipeline passed.[/bold green]")
    if report_json:
        out_path = Path(report_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(
                {
                    "ok": True,
                    "output_dir": output_dir,
                    "duration_seconds": time.time() - started_at,
                    "steps": step_reports,
                },
                indent=2,
            ),
            encoding="utf-8",
        )


@app.command()
def replay(
    session_id: str = typer.Argument(..., help="Runtime session ID to replay"),
):
    """Replay a runtime artifact and print summary."""
    logger = RunArtifactLogger()
    replayer = RunReplayer()
    events = logger.read(session_id)

    if not events:
        console.print(f"[bold red]Run not found:[/bold red] {session_id}")
        raise typer.Exit(1)

    summary = replayer.summarize(session_id, events)

    table = Table(title=f"Run Replay: {session_id}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Events", str(summary.total_events))
    table.add_row("Turns", str(summary.turns))
    table.add_row("Tool Calls", str(summary.tool_calls))
    table.add_row("Errors", str(summary.errors))
    table.add_row("Final Answer", (summary.final_answer or "")[:200])
    console.print(table)


@app.command("export-run")
def export_run(
    session_id: str = typer.Argument(..., help="Runtime session ID to export"),
):
    """Export a portable run bundle for benchmark reproducibility."""
    exporter = RunExporter()
    try:
        result = exporter.export(session_id)
    except FileNotFoundError:
        console.print(f"[bold red]Run not found:[/bold red] {session_id}")
        raise typer.Exit(1)

    table = Table(title=f"Run Export: {session_id}")
    table.add_column("Artifact", style="cyan")
    table.add_column("Path", style="green")
    table.add_row("Bundle Dir", str(result.bundle_dir))
    table.add_row("Manifest", str(result.manifest_path))
    table.add_row("Events", str(result.events_path))
    table.add_row("State", str(result.state_path) if result.state_path else "(none)")
    console.print(table)


@app.command("verify-run")
def verify_run(
    session_id: str = typer.Argument(..., help="Exported runtime session ID to verify"),
    signing_key: str = typer.Option("", "--signing-key", help="HMAC signing key for signed manifests"),
):
    """Verify an exported run bundle integrity and optional signature."""
    exporter = RunExporter()
    bundle_dir = exporter.export_dir / session_id
    if not bundle_dir.exists():
        console.print(f"[bold red]Bundle not found:[/bold red] {bundle_dir}")
        raise typer.Exit(1)

    verifier = RunBundleVerifier()
    result = verifier.verify(bundle_dir=bundle_dir, signing_key=signing_key or None)

    table = Table(title=f"Run Verify: {session_id}")
    table.add_column("Check", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Overall", "PASS" if result.ok else "FAIL")
    table.add_row("Checksum", "PASS" if result.checksum_ok else "FAIL")
    table.add_row(
        "Signature",
        "N/A" if result.signature_ok is None else ("PASS" if result.signature_ok else "FAIL"),
    )
    table.add_row("Errors", "; ".join(result.errors) if result.errors else "(none)")
    console.print(table)

    if not result.ok:
        raise typer.Exit(1)


@app.command("benchmark-export")
def benchmark_export(
    output_dir: str = typer.Option(
        ".novus-bench",
        "--output-dir",
        help="Directory to write benchmark report and exported bundles",
    ),
    signing_key: str = typer.Option(
        "",
        "--signing-key",
        help="Optional HMAC key for signed bundle export and verification",
    ),
    baseline: str = typer.Option(
        "",
        "--baseline",
        help="Optional baseline snapshot/report JSON path for regression deltas",
    ),
    summary_md: str = typer.Option(
        "",
        "--summary-md",
        help="Optional markdown summary output path (for CI step summary)",
    ),
    snapshot_out: str = typer.Option(
        "",
        "--snapshot-out",
        help="Optional current snapshot output path",
    ),
    max_pass_rate_drop: float = typer.Option(
        0.05,
        "--max-pass-rate-drop",
        help="Allowed absolute pass-rate drop before marking regression",
    ),
    max_latency_regression_pct: float = typer.Option(
        200.0,
        "--max-latency-regression-pct",
        help="Allowed avg-latency regression percentage before marking regression",
    ),
    max_case_latency_regression_pct: float = typer.Option(
        300.0,
        "--max-case-latency-regression-pct",
        help="Allowed per-case latency regression percentage before marking regression",
    ),
    allow_case_pass_failures: int = typer.Option(
        0,
        "--allow-case-pass-failures",
        help="Allowed number of baseline pass -> current fail case regressions",
    ),
    category_thresholds: str = typer.Option(
        "",
        "--category-thresholds",
        help="Optional JSON file with per-category regression budgets",
    ),
    fail_on_regression: bool = typer.Option(
        False,
        "--fail-on-regression/--no-fail-on-regression",
        help="Exit non-zero if baseline comparison reports regression",
    ),
):
    """Run benchmark suite and export+verify portable bundles for CI artifacts."""
    payload = asyncio.run(
        run_benchmark_export(
            output_dir=Path(output_dir),
            signing_key=signing_key or None,
            baseline_path=Path(baseline) if baseline else None,
            summary_md_path=Path(summary_md) if summary_md else None,
            snapshot_path=Path(snapshot_out) if snapshot_out else None,
            max_pass_rate_drop=max_pass_rate_drop,
            max_latency_regression_pct=max_latency_regression_pct,
            max_case_latency_regression_pct=max_case_latency_regression_pct,
            allow_case_pass_failures=allow_case_pass_failures,
            category_thresholds_path=Path(category_thresholds) if category_thresholds else None,
        )
    )

    table = Table(title="Benchmark Export")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Pass Rate", f"{payload['benchmark']['pass_rate']:.2%}")
    table.add_row("Cases", str(payload["benchmark"]["total"]))
    table.add_row("Sessions Exported", str(payload["summary"]["sessions"]))
    table.add_row("Verification Failures", str(payload["summary"]["verification_failures"]))
    if payload.get("comparison"):
        table.add_row("Regression", "YES" if payload["comparison"]["regression"] else "NO")
    table.add_row("Report", str(Path(output_dir) / "benchmark_report.json"))
    if summary_md:
        table.add_row("Summary MD", str(Path(summary_md)))
    if snapshot_out:
        table.add_row("Snapshot", str(Path(snapshot_out)))
    console.print(table)

    if payload["summary"]["verification_failures"] > 0:
        raise typer.Exit(1)
    if fail_on_regression and payload.get("comparison", {}).get("regression"):
        raise typer.Exit(1)


@app.command("benchmark-promote-baseline")
def benchmark_promote_baseline(
    source: str = typer.Option(
        ".novus-bench/benchmark_report.json",
        "--source",
        help="Benchmark report JSON or snapshot JSON to promote",
    ),
    output: str = typer.Option(
        ".github/benchmarks/baseline_snapshot.json",
        "--output",
        help="Destination baseline snapshot path",
    ),
):
    """Promote a benchmark run into the baseline snapshot."""
    source_path = Path(source)
    if not source_path.exists():
        console.print(f"[bold red]Source not found:[/bold red] {source_path}")
        raise typer.Exit(1)

    snapshot = load_snapshot(source_path)
    save_snapshot(Path(output), snapshot)

    table = Table(title="Benchmark Baseline Promotion")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Source", str(source_path))
    table.add_row("Output", str(Path(output)))
    table.add_row("Pass Rate", f"{snapshot.pass_rate:.2%}")
    table.add_row("Avg Latency", f"{snapshot.avg_latency_ms:.2f} ms")
    table.add_row("P95 Latency", f"{snapshot.p95_latency_ms:.2f} ms")
    table.add_row("Timestamp", snapshot.timestamp)
    console.print(table)


@app.command("benchmark-evaluate")
def benchmark_evaluate(
    report: str = typer.Option(
        ".novus-bench/benchmark_report.json",
        "--report",
        help="Benchmark report JSON path",
    ),
    baseline: str = typer.Option(
        ".github/benchmarks/baseline_snapshot.json",
        "--baseline",
        help="Baseline snapshot/report JSON path",
    ),
    category_thresholds: str = typer.Option(
        ".github/benchmarks/category_thresholds.json",
        "--category-thresholds",
        help="Optional category threshold JSON path",
    ),
    max_pass_rate_drop: float = typer.Option(0.05, "--max-pass-rate-drop"),
    max_latency_regression_pct: float = typer.Option(200.0, "--max-latency-regression-pct"),
    max_case_latency_regression_pct: float = typer.Option(300.0, "--max-case-latency-regression-pct"),
    allow_case_pass_failures: int = typer.Option(0, "--allow-case-pass-failures"),
    fail_on_regression: bool = typer.Option(True, "--fail-on-regression/--no-fail-on-regression"),
):
    """Evaluate a benchmark report against baseline thresholds."""
    report_path = Path(report)
    baseline_path = Path(baseline)
    if not report_path.exists():
        console.print(f"[bold red]Report not found:[/bold red] {report_path}")
        raise typer.Exit(1)
    if not baseline_path.exists():
        console.print(f"[bold red]Baseline not found:[/bold red] {baseline_path}")
        raise typer.Exit(1)

    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    current = snapshot_from_report(report_payload, commit=report_payload.get("git", {}).get("commit"))
    baseline_snapshot = load_snapshot(baseline_path)

    thresholds_payload: Optional[dict[str, dict[str, float]]] = None
    category_path = Path(category_thresholds) if category_thresholds else None
    if category_path and category_path.exists():
        thresholds_payload = json.loads(category_path.read_text(encoding="utf-8"))

    comparison = compare_snapshots(
        baseline=baseline_snapshot,
        current=current,
        max_pass_rate_drop=max_pass_rate_drop,
        max_latency_regression_pct=max_latency_regression_pct,
        max_case_latency_regression_pct=max_case_latency_regression_pct,
        allow_case_pass_failures=allow_case_pass_failures,
        category_thresholds=thresholds_payload,
    )

    table = Table(title="Benchmark Evaluation")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Regression", "YES" if comparison["regression"] else "NO")
    table.add_row("Pass Rate Delta", f"{comparison['delta']['pass_rate']:+.4f}")
    table.add_row("Avg Latency Delta %", f"{comparison['delta']['avg_latency_pct']:+.2f}%")
    table.add_row("Case Regressions", str(len(comparison.get("case_regressions", []))))
    table.add_row("Reasons", "; ".join(comparison.get("reasons", [])) or "(none)")
    console.print(table)

    if fail_on_regression and comparison["regression"]:
        raise typer.Exit(1)


def main():
    """Main entry point."""
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
