"""
NOVUS API Server.

FastAPI-based REST API for interacting with the NOVUS platform.
"""

from __future__ import annotations

import asyncio
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
world_model_planner: Optional[WorldModelPlanner] = None
ws_manager = WebSocketManager()
artifact_logger = RunArtifactLogger()
run_replayer = RunReplayer()
run_exporter = RunExporter(artifact_logger=artifact_logger)
run_verifier = RunBundleVerifier()
background_runs: Optional[BackgroundRunManager] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global swarm, world_model, world_model_planner, background_runs
    
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
    allow_origins=["*"],
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
