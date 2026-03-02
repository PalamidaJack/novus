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

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Response
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
from novus.human_in_loop import approval_router, get_approval_manager
from novus.eval import Evaluator, create_math_suite
from pydantic import BaseModel

logger = structlog.get_logger()


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global swarm, world_model, world_model_planner
    
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


# Include additional routers
app.include_router(mcp_router)
app.include_router(approval_router)


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
