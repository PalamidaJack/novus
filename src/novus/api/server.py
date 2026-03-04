"""
NOVUS API Server.

FastAPI-based REST API for interacting with the NOVUS platform.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from datetime import datetime
import structlog

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
import time

from novus.swarm.orchestrator import SwarmOrchestrator
from novus.core.models import SwarmConfig, Task, TaskPriority, AgentCapability
from novus.world_model.engine import WorldModel, WorldModelPlanner
from novus.monitoring import METRICS
from novus.streaming import StreamingAgent, stream_to_sse
from novus.mcp import mcp_router, get_mcp_server
from novus.a2a import a2a_router, get_a2a_bridge, get_agent_card
from novus.human_in_loop import approval_router, get_approval_manager
from novus.eval import Evaluator, create_math_suite
from novus.benchmark import BenchmarkHarness, default_cases
from novus.runtime.artifacts import RunArtifactLogger
from novus.runtime.exporter import RunExporter
from novus.runtime.replay import RunReplayer
from novus.runtime.trace_grade import TraceGrader
from novus.runtime.verifier import RunBundleVerifier
from novus.runtime.background import BackgroundRunManager
from novus.memory.unified import UnifiedMemory
from novus.guardrails import Guardrails, GuardrailRule, GuardrailType
from pydantic import BaseModel

logger = structlog.get_logger()


class WebSocketManager:
    """Simple broadcast manager for runtime status updates."""

    def __init__(self):
        self.connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.connections.discard(websocket)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        to_remove: list[WebSocket] = []
        for ws in self.connections:
            try:
                await ws.send_json(message)
            except Exception:
                to_remove.append(ws)
        for ws in to_remove:
            self.disconnect(ws)


class Settings(BaseSettings):
    """Application settings."""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    log_level: str = "INFO"
    
    class Config:
        env_prefix = "NOVUS_"


# Global state
swarm: Optional[SwarmOrchestrator] = None
world_model: Optional[WorldModel] = None
# Runtime LLM config – updated from the Settings panel
llm_config: Dict[str, str] = {
    "provider": "",
    "api_key": "",
    "model": "",
}
world_model_planner: Optional[WorldModelPlanner] = None
ws_manager = WebSocketManager()
artifact_logger = RunArtifactLogger()
run_replayer = RunReplayer()
run_exporter = RunExporter(artifact_logger=artifact_logger)
run_verifier = RunBundleVerifier()
background_runs: Optional[BackgroundRunManager] = None
memory: Optional[UnifiedMemory] = None
guardrails_engine: Optional[Guardrails] = None

# Platform-level config persisted across restarts (in-memory for now)
platform_config: Dict[str, Any] = {
    "swarm": {
        "target_agent_count": 5,
        "enable_evolution": False,
        "mutation_rate": 0.1,
        "consensus_threshold": 0.75,
        "selection_pressure": 0.3,
    },
    "execution": {
        "sandbox_profile": "standard",
        "timeout_seconds": 300,
        "enable_network": True,
        "enable_computer_use": False,
    },
    "guardrails": [],  # list of per-rule overrides
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global swarm, world_model, world_model_planner, background_runs, memory, guardrails_engine
    
    # Startup
    logger.info("starting_novus_api")
    
    # Initialize swarm
    swarm = SwarmOrchestrator(SwarmConfig(
        target_agent_count=5,
        enable_evolution=False  # Disable for API mode
    ))
    await swarm.start()
    
    # Initialize world model
    world_model = WorldModel()
    world_model_planner = WorldModelPlanner(world_model)

    # Initialize memory and guardrails
    memory = UnifiedMemory()
    guardrails_engine = Guardrails()

    bridge = get_a2a_bridge()

    async def _handle_a2a_task_run(params: Dict[str, Any]) -> Dict[str, Any]:
        from novus.core.agent import Agent
        from novus.core.models import AgentConfig

        prompt = str(params.get("prompt", "")).strip()
        if not prompt:
            return {"error": "missing prompt"}
        agent = Agent(AgentConfig(name="A2AAgent"))
        answer = await agent.run(prompt)
        return {"answer": answer}

    bridge.register_handler("task.run", _handle_a2a_task_run)
    from novus.core.agent import Agent
    from novus.core.models import AgentConfig

    background_agent = Agent(AgentConfig(name="BackgroundAgent"))
    background_runs = BackgroundRunManager(
        runner=background_agent.run,
        session_getter=background_agent.get_last_session_id,
    )
    
    logger.info("novus_api_started")
    
    yield
    
    # Shutdown
    if swarm:
        swarm.stop()
    logger.info("novus_api_stopped")


# Create FastAPI app
app = FastAPI(
    title="NOVUS API",
    description="Next-Generation Agentic AI Platform",
    version="0.1.0",
    lifespan=lifespan
)

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Metrics middleware
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Track API request metrics."""
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    # Record metrics
    METRICS.record_api_request(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code,
        duration=duration
    )

    # Best-effort live telemetry for web UI.
    await ws_manager.broadcast(
        {
            "type": "api_request",
            "data": {
                "method": request.method,
                "endpoint": request.url.path,
                "status": response.status_code,
                "duration_ms": duration * 1000,
            },
            "timestamp": time.time(),
        }
    )
    
    return response


# Request/Response Models

class TaskRequest(BaseModel):
    """Request to submit a task."""
    description: str = Field(..., min_length=1, max_length=10000)
    priority: str = Field(default="normal", pattern="^(critical|high|normal|low|background)$")
    capabilities: List[str] = Field(default_factory=lambda: ["reasoning"])
    constraints: Dict[str, Any] = Field(default_factory=dict)
    wait_for_result: bool = Field(default=True)
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=300.0)


class TaskResponse(BaseModel):
    """Response for a submitted task."""
    task_id: str
    status: str
    message: str


class TaskResultResponse(BaseModel):
    """Response containing task result."""
    task_id: str
    status: str
    result: Any
    created_at: datetime
    completed_at: Optional[datetime]
    error: Optional[str] = None


class TaskListItem(BaseModel):
    task_id: str
    description: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    assigned_agent_id: Optional[str] = None


class SwarmStatusResponse(BaseModel):
    """Response containing swarm status."""
    population: int
    generation: int
    pending_tasks: int
    active_tasks: int
    completed_tasks: int
    agents: List[Dict[str, Any]]


class SolveRequest(BaseModel):
    """Request for collective solve."""
    problem: str = Field(..., min_length=1)
    num_agents: int = Field(default=5, ge=1, le=20)
    consensus_threshold: float = Field(default=0.75, ge=0.0, le=1.0)


class SolveResponse(BaseModel):
    """Response for collective solve."""
    solution: Any
    confidence: float
    generated_by: str
    agents_used: int


class PlanRequest(BaseModel):
    """Request for world model planning."""
    goal_state: Dict[str, Any]
    initial_state: Dict[str, Any]
    max_plan_length: int = Field(default=10, ge=1, le=50)


class PlanResponse(BaseModel):
    """Response for world model planning."""
    best_plan: List[Dict[str, Any]]
    best_score: float
    alternatives: List[Dict[str, Any]]


# API Endpoints

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "NOVUS API",
        "version": "0.1.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/tasks", response_model=List[TaskListItem])
async def list_tasks():
    """List known tasks with their current status."""
    if not swarm:
        raise HTTPException(status_code=503, detail="Swarm not initialized")

    tasks = list(swarm.all_tasks.values())
    tasks.sort(key=lambda t: t.created_at, reverse=True)
    return [
        TaskListItem(
            task_id=t.id,
            description=t.description,
            status=t.status.value,
            created_at=t.created_at,
            completed_at=t.completed_at,
            assigned_agent_id=t.assigned_agent_id,
        )
        for t in tasks
    ]


@app.post("/tasks", response_model=TaskResponse)
async def submit_task(request: TaskRequest, background_tasks: BackgroundTasks):
    """Submit a task to the swarm."""
    if not swarm:
        raise HTTPException(status_code=503, detail="Swarm not initialized")
    
    # Map priority string to enum
    priority_map = {
        "critical": TaskPriority.CRITICAL,
        "high": TaskPriority.HIGH,
        "normal": TaskPriority.NORMAL,
        "low": TaskPriority.LOW,
        "background": TaskPriority.BACKGROUND,
    }
    
    # Map capabilities
    try:
        capabilities = {AgentCapability(c) for c in request.capabilities}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid capability: {e}")
    
    # Create task
    task = Task(
        description=request.description,
        priority=priority_map[request.priority],
        required_capabilities=capabilities,
        constraints=request.constraints
    )
    
    # Submit to swarm
    await swarm.submit_task(task)
    await ws_manager.broadcast(
        {
            "type": "task_submitted",
            "data": {"task_id": task.id, "description": task.description, "status": task.status.value},
            "timestamp": time.time(),
        }
    )
    
    return TaskResponse(
        task_id=task.id,
        status=task.status.value,
        message="Task submitted successfully"
    )


@app.get("/tasks/{task_id}", response_model=TaskResultResponse)
async def get_task_result(task_id: str, wait: bool = False, timeout: float = 60.0):
    """Get task result."""
    if not swarm:
        raise HTTPException(status_code=503, detail="Swarm not initialized")
    
    # Check if task exists
    if task_id in swarm.completed_tasks:
        task = swarm.completed_tasks[task_id]
        return TaskResultResponse(
            task_id=task.id,
            status=task.status.value,
            result=task.result,
            created_at=task.created_at,
            completed_at=task.completed_at,
            error=task.result.get("error") if isinstance(task.result, dict) else None
        )
    
    # Check pending/running tasks
    if wait:
        task = await swarm.get_task_result(task_id, timeout=timeout)
        if task:
            return TaskResultResponse(
                task_id=task.id,
                status=task.status.value,
                result=task.result,
                created_at=task.created_at,
                completed_at=task.completed_at,
                error=task.result.get("error") if isinstance(task.result, dict) else None
            )
        raise HTTPException(status_code=408, detail="Task timed out")
    
    raise HTTPException(status_code=404, detail="Task not found")


@app.get("/swarm/status", response_model=SwarmStatusResponse)
async def get_swarm_status():
    """Get swarm status."""
    if not swarm:
        raise HTTPException(status_code=503, detail="Swarm not initialized")
    
    status = swarm.get_status()
    # Convert agents dict to list, embedding the agent ID in each entry
    agents_dict = status.pop("agents", {})
    status["agents"] = [
        {"agent_id": aid, **info} for aid, info in agents_dict.items()
    ]
    return SwarmStatusResponse(**status)


@app.post("/swarm/solve", response_model=SolveResponse)
async def collective_solve(request: SolveRequest):
    """Use collective intelligence to solve a problem."""
    if not swarm:
        raise HTTPException(status_code=503, detail="Swarm not initialized")
    
    try:
        solution = await swarm.collective_solve(
            problem=request.problem,
            n_agents=request.num_agents,
            consensus_threshold=request.consensus_threshold
        )
        
        return SolveResponse(
            solution=solution.content,
            confidence=solution.confidence,
            generated_by=solution.generated_by,
            agents_used=request.num_agents
        )
    except Exception as e:
        logger.error("solve_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/world-model/plan", response_model=PlanResponse)
async def plan_with_world_model(request: PlanRequest):
    """Use world model for planning."""
    if not world_model_planner:
        raise HTTPException(status_code=503, detail="World model not initialized")
    
    try:
        result = await world_model_planner.plan(
            goal_state=request.goal_state,
            initial_state=request.initial_state,
            max_plan_length=request.max_plan_length
        )
        
        return PlanResponse(**result)
    except Exception as e:
        logger.error("plan_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/world-model/stats")
async def get_world_model_stats():
    """Get world model statistics."""
    if not world_model:
        raise HTTPException(status_code=503, detail="World model not initialized")
    
    return world_model.get_stats()


@app.get("/metrics")
async def get_metrics():
    """Get Prometheus metrics."""
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=METRICS.get_metrics(),
        media_type="text/plain"
    )


@app.get("/.well-known/agent-card.json")
async def well_known_agent_card():
    return get_agent_card(base_url="http://localhost:8000")


# Include additional routers
app.include_router(mcp_router)
app.include_router(approval_router)
app.include_router(a2a_router)


@app.websocket("/ws")
async def websocket_events(websocket: WebSocket):
    """WebSocket endpoint for live dashboard events."""
    await ws_manager.connect(websocket)
    try:
        while True:
            _ = await websocket.receive_text()
            # Keepalive/no-op, client messages currently unused.
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# Streaming endpoint
@app.get("/stream/chat")
async def stream_chat(message: str):
    """Stream a chat response with real-time updates."""
    from fastapi.responses import StreamingResponse
    
    agent = StreamingAgent("stream-1", "Assistant")
    return StreamingResponse(
        stream_to_sse(agent.stream_think(message)),
        media_type="text/event-stream"
    )


# Evaluation endpoints
class EvalResultItem(BaseModel):
    test: str
    passed: bool
    score: float
    latency_ms: float


class EvalResponse(BaseModel):
    suite: str
    total_tests: int
    passed: int
    results: List[EvalResultItem]


class BenchmarkItem(BaseModel):
    case_name: str
    category: str
    passed: bool
    latency_ms: float


class BenchmarkResponse(BaseModel):
    pass_rate: float
    total: int
    results: List[BenchmarkItem]


class RunSummaryResponse(BaseModel):
    session_id: str
    total_events: int
    turns: int
    tool_calls: int
    errors: int
    final_answer: Optional[str]


class RunExportResponse(BaseModel):
    session_id: str
    bundle_dir: str
    manifest_path: str
    events_path: str
    state_path: Optional[str]


class RunVerifyResponse(BaseModel):
    session_id: str
    ok: bool
    checksum_ok: bool
    signature_ok: Optional[bool]
    errors: List[str]


class RunTraceGradeResponse(BaseModel):
    session_id: str
    score: float
    max_score: float
    passed: bool
    reasons: List[str]
    metrics: Dict[str, Any]


class BackgroundTaskRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=10000)


class BackgroundTaskResponse(BaseModel):
    task_id: str
    status: str
    created_at: str


class BackgroundTaskStatusResponse(BaseModel):
    task_id: str
    status: str
    created_at: str
    updated_at: str
    result: Optional[str] = None
    error: Optional[str] = None
    session_id: Optional[str] = None


@app.post("/eval/run", response_model=EvalResponse)
async def run_evaluation():
    """Run evaluation suite on agents."""
    from novus.core.agent import Agent
    from novus.core.models import AgentConfig
    
    evaluator = Evaluator()
    suite = create_math_suite()
    
    # Create test agent
    config = AgentConfig(name="TestAgent")
    agent = Agent(config)
    
    # Run eval
    results = await evaluator.evaluate_agent(agent, suite)
    
    return {
        "suite": suite.name,
        "total_tests": len(results),
        "passed": sum(1 for r in results if r.passed),
        "results": [
            {
                "test": r.test_name,
                "passed": r.passed,
                "score": r.score,
                "latency_ms": r.execution_time_ms
            }
            for r in results
        ]
    }


@app.post("/benchmark/run", response_model=BenchmarkResponse)
async def run_benchmark():
    """Run a compact benchmark suite against an agent runtime."""
    from novus.core.agent import Agent
    from novus.core.models import AgentConfig

    agent = Agent(AgentConfig(name="BenchmarkAgent"))
    harness = BenchmarkHarness(runner=agent.run)
    report = await harness.run(default_cases())
    return {
        "pass_rate": report.pass_rate,
        "total": len(report.results),
        "results": [
            {
                "case_name": r.case_name,
                "category": r.category,
                "passed": r.passed,
                "latency_ms": r.latency_ms,
            }
            for r in report.results
        ],
    }


@app.post("/background-runs", response_model=BackgroundTaskResponse)
async def submit_background_run(request: BackgroundTaskRequest):
    """Submit a long-running background agent task."""
    if background_runs is None:
        raise HTTPException(status_code=503, detail="Background manager not initialized")
    state = background_runs.submit(request.prompt)
    return {
        "task_id": state.id,
        "status": state.status,
        "created_at": state.created_at,
    }


@app.get("/background-runs", response_model=List[BackgroundTaskStatusResponse])
async def list_background_runs(limit: int = 50):
    if background_runs is None:
        raise HTTPException(status_code=503, detail="Background manager not initialized")
    return [
        {
            "task_id": item.id,
            "status": item.status,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "result": item.result,
            "error": item.error,
            "session_id": item.session_id,
        }
        for item in background_runs.list(limit=limit)
    ]


@app.get("/background-runs/{task_id}", response_model=BackgroundTaskStatusResponse)
async def get_background_run(task_id: str):
    if background_runs is None:
        raise HTTPException(status_code=503, detail="Background manager not initialized")
    item = background_runs.get(task_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Background task not found")
    return {
        "task_id": item.id,
        "status": item.status,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "result": item.result,
        "error": item.error,
        "session_id": item.session_id,
    }


@app.post("/background-runs/{task_id}/cancel")
async def cancel_background_run(task_id: str):
    if background_runs is None:
        raise HTTPException(status_code=503, detail="Background manager not initialized")
    cancelled = background_runs.cancel(task_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Background task not found or already finished")
    return {"task_id": task_id, "cancelled": True}


@app.get("/runs", response_model=List[str])
async def list_runs(limit: int = 50):
    """List recent runtime session IDs with stored artifacts."""
    return artifact_logger.list_sessions(limit=limit)


@app.get("/runs/{session_id}")
async def get_run_events(session_id: str):
    """Get raw JSONL event stream for a session."""
    events = artifact_logger.read(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"session_id": session_id, "events": events}


@app.get("/runs/{session_id}/summary", response_model=RunSummaryResponse)
async def get_run_summary(session_id: str):
    """Replay a run artifact into a concise deterministic summary."""
    events = artifact_logger.read(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="Run not found")
    summary = run_replayer.summarize(session_id=session_id, events=events)
    return {
        "session_id": summary.session_id,
        "total_events": summary.total_events,
        "turns": summary.turns,
        "tool_calls": summary.tool_calls,
        "errors": summary.errors,
        "final_answer": summary.final_answer,
    }


@app.post("/runs/{session_id}/export", response_model=RunExportResponse)
async def export_run_bundle(session_id: str):
    """Export a portable run bundle (manifest + events + optional state)."""
    try:
        exported = run_exporter.export(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found")

    return {
        "session_id": exported.session_id,
        "bundle_dir": str(exported.bundle_dir),
        "manifest_path": str(exported.manifest_path),
        "events_path": str(exported.events_path),
        "state_path": str(exported.state_path) if exported.state_path else None,
    }


@app.post("/runs/{session_id}/verify", response_model=RunVerifyResponse)
async def verify_run_bundle(session_id: str, signing_key: Optional[str] = None):
    """Verify exported run bundle integrity and optional signature."""
    bundle_dir = run_exporter.export_dir / session_id
    if not bundle_dir.exists():
        raise HTTPException(status_code=404, detail="Exported run bundle not found")

    result = run_verifier.verify(bundle_dir=bundle_dir, signing_key=signing_key)
    return {
        "session_id": result.session_id,
        "ok": result.ok,
        "checksum_ok": result.checksum_ok,
        "signature_ok": result.signature_ok,
        "errors": result.errors,
    }


@app.get("/runs/{session_id}/trace-grade", response_model=RunTraceGradeResponse)
async def grade_run_trace(session_id: str, min_score: float = 0.7):
    events = artifact_logger.read(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="Run not found")
    grade = TraceGrader(min_score=min_score).grade(session_id=session_id, events=events)
    return grade.to_dict()


# --- LLM Provider proxy ---------------------------------------------------

class ProviderModelsRequest(BaseModel):
    provider: str
    api_key: str = ""


class ProviderModelItem(BaseModel):
    id: str
    name: str
    context_length: Optional[int] = None


class ProviderModelsResponse(BaseModel):
    provider: str
    models: List[ProviderModelItem]


PROVIDER_URLS: Dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1/models",
    "openai": "https://api.openai.com/v1/models",
    "kilo": "https://api.kilo.ai/api/gateway/models",
    "anthropic": "https://api.anthropic.com/v1/models",
}


@app.get("/providers")
async def list_providers():
    """Return the list of known LLM providers."""
    return {
        "providers": [
            {"id": "openrouter", "name": "OpenRouter", "url": PROVIDER_URLS["openrouter"]},
            {"id": "openai", "name": "OpenAI", "url": PROVIDER_URLS["openai"]},
            {"id": "kilo", "name": "Kilo Code", "url": PROVIDER_URLS["kilo"]},
            {"id": "anthropic", "name": "Anthropic", "url": PROVIDER_URLS["anthropic"]},
        ]
    }


@app.post("/providers/models", response_model=ProviderModelsResponse)
async def fetch_provider_models(req: ProviderModelsRequest):
    """Proxy-fetch the model list from a provider API."""
    import httpx

    url = PROVIDER_URLS.get(req.provider)
    if not url:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {req.provider}")

    headers: Dict[str, str] = {}
    if req.api_key:
        if req.provider == "anthropic":
            headers["x-api-key"] = req.api_key
            headers["anthropic-version"] = "2023-06-01"
        else:
            headers["Authorization"] = f"Bearer {req.api_key}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"Provider returned {exc.response.status_code}: {exc.response.text[:200]}",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to reach provider: {exc}")

    raw_models = body.get("data", body if isinstance(body, list) else [])

    models = [
        ProviderModelItem(
            id=m.get("id", ""),
            name=m.get("name") or m.get("id", ""),
            context_length=m.get("context_length"),
        )
        for m in raw_models
        if m.get("id")
    ]

    models.sort(key=lambda m: m.name.lower())
    return ProviderModelsResponse(provider=req.provider, models=models)


# --- LLM runtime config ---------------------------------------------------

class LLMConfigPayload(BaseModel):
    provider: str
    api_key: str = ""
    model: str = ""


@app.get("/config/llm")
async def get_llm_config():
    """Return the current LLM config (key masked)."""
    masked_key = ""
    if llm_config["api_key"]:
        k = llm_config["api_key"]
        masked_key = k[:4] + "..." + k[-4:] if len(k) > 8 else "***"
    return {
        "provider": llm_config["provider"],
        "model": llm_config["model"],
        "api_key_set": bool(llm_config["api_key"]),
        "api_key_masked": masked_key,
    }


@app.post("/config/llm")
async def set_llm_config(payload: LLMConfigPayload):
    """Save the active LLM provider, model, and API key.

    Also injects the key into the process environment so that
    ``get_llm_client`` picks it up for all subsequent agent calls.
    """
    import os
    from novus.llm import clear_llm_cache

    llm_config["provider"] = payload.provider
    llm_config["model"] = payload.model
    llm_config["api_key"] = payload.api_key

    # Expose the key as an env-var so get_llm_client finds it automatically.
    env_var = f"{payload.provider.upper()}_API_KEY"
    if payload.api_key:
        os.environ[env_var] = payload.api_key
    elif env_var in os.environ:
        del os.environ[env_var]

    # Flush the cached LLM clients so the next call uses the new config.
    clear_llm_cache()

    # Push the new provider/model into every running swarm agent so
    # subsequent collective_solve calls use the chosen LLM.
    if swarm:
        for agent in swarm.agents.values():
            agent.config.llm_provider = payload.provider
            if payload.model:
                agent.config.model_name = payload.model

    logger.info(
        "llm_config_updated",
        provider=payload.provider,
        model=payload.model,
        key_set=bool(payload.api_key),
    )

    return {"status": "ok", "provider": payload.provider, "model": payload.model}


# --- Platform config endpoints -----------------------------------------------

class SwarmConfigPayload(BaseModel):
    target_agent_count: int = Field(default=5, ge=1, le=50)
    enable_evolution: bool = False
    mutation_rate: float = Field(default=0.1, ge=0.0, le=1.0)
    consensus_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    selection_pressure: float = Field(default=0.3, ge=0.0, le=1.0)


@app.get("/config/swarm")
async def get_swarm_config():
    return platform_config["swarm"]


@app.post("/config/swarm")
async def set_swarm_config(payload: SwarmConfigPayload):
    platform_config["swarm"] = payload.model_dump()
    # Apply to running swarm
    if swarm:
        swarm.config.target_agent_count = payload.target_agent_count
        swarm.config.enable_evolution = payload.enable_evolution
        swarm.config.mutation_rate = payload.mutation_rate
        swarm.config.consensus_threshold = payload.consensus_threshold
        swarm.config.selection_pressure = payload.selection_pressure
    logger.info("swarm_config_updated", config=platform_config["swarm"])
    return {"status": "ok", **platform_config["swarm"]}


class ExecutionConfigPayload(BaseModel):
    sandbox_profile: str = Field(default="standard", pattern="^(standard|restricted|permissive)$")
    timeout_seconds: int = Field(default=300, ge=10, le=3600)
    enable_network: bool = True
    enable_computer_use: bool = False


@app.get("/config/execution")
async def get_execution_config():
    return platform_config["execution"]


@app.post("/config/execution")
async def set_execution_config(payload: ExecutionConfigPayload):
    platform_config["execution"] = payload.model_dump()
    logger.info("execution_config_updated", config=platform_config["execution"])
    return {"status": "ok", **platform_config["execution"]}


class GuardrailRuleOverride(BaseModel):
    name: str
    enabled: bool = True
    action: str = Field(default="block", pattern="^(block|warn|truncate|redact)$")
    severity: str = Field(default="high", pattern="^(low|medium|high|critical)$")


class GuardrailsConfigPayload(BaseModel):
    rules: List[GuardrailRuleOverride]


@app.get("/config/guardrails")
async def get_guardrails_config():
    if not guardrails_engine:
        raise HTTPException(status_code=503, detail="Guardrails not initialized")
    stats = guardrails_engine.get_stats()
    rules = []
    for rule in guardrails_engine.rules.values():
        rules.append({
            "name": rule.name,
            "type": rule.guardrail_type.value if hasattr(rule.guardrail_type, 'value') else str(rule.guardrail_type),
            "enabled": rule.enabled,
            "action": rule.action,
            "severity": rule.severity,
        })
    return {"stats": stats, "rules": rules}


@app.post("/config/guardrails")
async def set_guardrails_config(payload: GuardrailsConfigPayload):
    if not guardrails_engine:
        raise HTTPException(status_code=503, detail="Guardrails not initialized")
    platform_config["guardrails"] = [r.model_dump() for r in payload.rules]
    # Apply overrides to the engine rules
    rule_map = {r.name: r for r in payload.rules}
    for rule in guardrails_engine.rules.values():
        if rule.name in rule_map:
            override = rule_map[rule.name]
            rule.enabled = override.enabled
            rule.action = override.action
            rule.severity = override.severity
    logger.info("guardrails_config_updated", rule_count=len(payload.rules))
    return {"status": "ok", "rules_updated": len(payload.rules)}


# --- Memory endpoints ---------------------------------------------------------

@app.get("/memory/stats")
async def get_memory_stats():
    if not memory:
        raise HTTPException(status_code=503, detail="Memory not initialized")
    return memory.get_stats()


class MemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    memory_types: Optional[List[str]] = None
    k: int = Field(default=10, ge=1, le=50)


@app.post("/memory/search")
async def search_memory(request: MemorySearchRequest):
    if not memory:
        raise HTTPException(status_code=503, detail="Memory not initialized")
    from novus.core.models import MemoryType
    types = None
    if request.memory_types:
        try:
            types = [MemoryType(t) for t in request.memory_types]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid memory type: {e}")
    results = await memory.retrieve(
        query=request.query,
        memory_types=types,
        k=request.k,
    )
    return {
        "query": request.query,
        "results": [
            {
                "content": r.entry.content,
                "memory_type": r.entry.memory_type.value if hasattr(r.entry.memory_type, 'value') else str(r.entry.memory_type),
                "relevance_score": r.relevance_score,
                "retrieval_method": r.retrieval_method,
                "created_at": r.entry.created_at.isoformat() if hasattr(r.entry, 'created_at') else None,
            }
            for r in results
        ],
    }


# --- Agent spawn endpoint ----------------------------------------------------

class SpawnAgentRequest(BaseModel):
    name: str = Field(default="NewAgent", min_length=1, max_length=100)
    capabilities: List[str] = Field(default_factory=lambda: ["reasoning"])
    llm_provider: str = ""
    model_name: str = ""


@app.post("/swarm/spawn")
async def spawn_agent(request: SpawnAgentRequest):
    if not swarm:
        raise HTTPException(status_code=503, detail="Swarm not initialized")
    from novus.core.agent import Agent
    from novus.core.models import AgentConfig

    try:
        caps = {AgentCapability(c) for c in request.capabilities}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid capability: {e}")

    config = AgentConfig(
        name=request.name,
        capabilities=caps,
        llm_provider=request.llm_provider or llm_config.get("provider", "openai"),
        model_name=request.model_name or llm_config.get("model", "gpt-4"),
    )
    agent = Agent(config)
    swarm.agents[config.id] = agent
    swarm.config.target_agent_count = len(swarm.agents)
    await ws_manager.broadcast({
        "type": "agent_spawned",
        "data": {"agent_id": config.id, "name": request.name},
        "timestamp": time.time(),
    })
    logger.info("agent_spawned", agent_id=config.id, name=request.name)
    return {"status": "ok", "agent_id": config.id, "name": request.name}


# --- Task cancel endpoint -----------------------------------------------------

@app.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    if not swarm:
        raise HTTPException(status_code=503, detail="Swarm not initialized")
    task = swarm.all_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status.value in ("completed", "failed"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel task with status: {task.status.value}")
    from novus.core.models import TaskStatus
    task.status = TaskStatus.FAILED
    task.result = {"error": "Cancelled by user"}
    task.completed_at = datetime.utcnow()
    await ws_manager.broadcast({
        "type": "task_cancelled",
        "data": {"task_id": task_id},
        "timestamp": time.time(),
    })
    return {"task_id": task_id, "cancelled": True}


# Run server if executed directly

if __name__ == "__main__":
    import uvicorn
    
    settings = Settings()
    uvicorn.run(
        "novus.api.server:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
