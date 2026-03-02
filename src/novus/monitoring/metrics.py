"""
Metrics and monitoring for NOVUS.

Integrates Prometheus for metrics collection and OpenTelemetry for tracing.
"""

from __future__ import annotations

import time
from typing import Callable, Optional
from functools import wraps

from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest, CONTENT_TYPE_LATEST
from prometheus_client.registry import CollectorRegistry
import structlog

logger = structlog.get_logger()

# Create a custom registry
REGISTRY = CollectorRegistry()

# System Info
NOVUS_INFO = Info(
    "novus_build",
    "NOVUS build information",
    registry=REGISTRY
)

# Task Metrics
TASKS_SUBMITTED = Counter(
    "novus_tasks_submitted_total",
    "Total number of tasks submitted",
    ["priority", "capability"],
    registry=REGISTRY
)

TASKS_COMPLETED = Counter(
    "novus_tasks_completed_total",
    "Total number of tasks completed",
    ["status", "capability"],
    registry=REGISTRY
)

TASK_DURATION = Histogram(
    "novus_task_duration_seconds",
    "Task execution duration",
    ["capability"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
    registry=REGISTRY
)

TASK_QUEUE_SIZE = Gauge(
    "novus_task_queue_size",
    "Current number of tasks in queue",
    registry=REGISTRY
)

# Agent Metrics
AGENTS_TOTAL = Gauge(
    "novus_agents_total",
    "Total number of agents",
    ["status"],
    registry=REGISTRY
)

AGENT_TASKS_ACTIVE = Gauge(
    "novus_agent_tasks_active",
    "Number of active tasks per agent",
    ["agent_id", "agent_name"],
    registry=REGISTRY
)

AGENT_FITNESS = Gauge(
    "novus_agent_fitness",
    "Fitness score of agents",
    ["agent_id", "agent_name"],
    registry=REGISTRY
)

AGENT_COMPUTE_TIME = Counter(
    "novus_agent_compute_seconds_total",
    "Total compute time per agent",
    ["agent_id"],
    registry=REGISTRY
)

# Swarm Metrics
SWARM_GENERATION = Gauge(
    "novus_swarm_generation",
    "Current evolution generation",
    registry=REGISTRY
)

SWARM_CONSENSUS_DURATION = Histogram(
    "novus_swarm_consensus_duration_seconds",
    "Time to reach consensus",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
    registry=REGISTRY
)

# Memory Metrics
MEMORY_ENTRIES = Gauge(
    "novus_memory_entries",
    "Number of memory entries by type",
    ["memory_type"],
    registry=REGISTRY
)

MEMORY_RETRIEVAL_DURATION = Histogram(
    "novus_memory_retrieval_duration_seconds",
    "Memory retrieval latency",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5],
    registry=REGISTRY
)

MEMORY_GENERATIVE_HITS = Counter(
    "novus_memory_generative_hits_total",
    "Number of times generative memory was used",
    registry=REGISTRY
)

# World Model Metrics
WORLD_MODEL_PREDICTIONS = Counter(
    "novus_world_model_predictions_total",
    "Number of world model predictions",
    registry=REGISTRY
)

WORLD_MODEL_PREDICTION_DURATION = Histogram(
    "novus_world_model_prediction_duration_seconds",
    "World model prediction latency",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0],
    registry=REGISTRY
)

# Execution Metrics
CODE_EXECUTIONS = Counter(
    "novus_code_executions_total",
    "Number of code executions",
    ["language", "status"],
    registry=REGISTRY
)

CODE_EXECUTION_DURATION = Histogram(
    "novus_code_execution_duration_seconds",
    "Code execution duration",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
    registry=REGISTRY
)

WEB_SEARCHES = Counter(
    "novus_web_searches_total",
    "Number of web searches",
    registry=REGISTRY
)

# API Metrics
API_REQUESTS = Counter(
    "novus_api_requests_total",
    "API request count",
    ["method", "endpoint", "status"],
    registry=REGISTRY
)

API_REQUEST_DURATION = Histogram(
    "novus_api_request_duration_seconds",
    "API request duration",
    ["method", "endpoint"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
    registry=REGISTRY
)


class MetricsCollector:
    """Centralized metrics collection for NOVUS."""
    
    def __init__(self):
        self.registry = REGISTRY
        self._setup_info()
    
    def _setup_info(self) -> None:
        """Set build information."""
        from novus import __version__
        NOVUS_INFO.info({
            "version": __version__,
            "build_date": "2026-02-28",
        })
    
    def record_task_submitted(self, priority: str, capability: str) -> None:
        """Record task submission."""
        TASKS_SUBMITTED.labels(priority=priority, capability=capability).inc()
    
    def record_task_completed(self, status: str, capability: str, duration: float) -> None:
        """Record task completion."""
        TASKS_COMPLETED.labels(status=status, capability=capability).inc()
        TASK_DURATION.labels(capability=capability).observe(duration)
    
    def update_task_queue_size(self, size: int) -> None:
        """Update task queue size gauge."""
        TASK_QUEUE_SIZE.set(size)
    
    def update_agent_count(self, status: str, count: int) -> None:
        """Update agent count."""
        AGENTS_TOTAL.labels(status=status).set(count)
    
    def update_agent_metrics(self, agent_id: str, agent_name: str, 
                            active_tasks: int, fitness: float) -> None:
        """Update per-agent metrics."""
        AGENT_TASKS_ACTIVE.labels(agent_id=agent_id, agent_name=agent_name).set(active_tasks)
        AGENT_FITNESS.labels(agent_id=agent_id, agent_name=agent_name).set(fitness)
    
    def record_agent_compute(self, agent_id: str, duration: float) -> None:
        """Record agent compute time."""
        AGENT_COMPUTE_TIME.labels(agent_id=agent_id).inc(duration)
    
    def update_swarm_generation(self, generation: int) -> None:
        """Update swarm generation."""
        SWARM_GENERATION.set(generation)
    
    def record_consensus(self, duration: float) -> None:
        """Record consensus duration."""
        SWARM_CONSENSUS_DURATION.observe(duration)
    
    def update_memory_entries(self, memory_type: str, count: int) -> None:
        """Update memory entry count."""
        MEMORY_ENTRIES.labels(memory_type=memory_type).set(count)
    
    def record_memory_retrieval(self, duration: float, used_generative: bool = False) -> None:
        """Record memory retrieval."""
        MEMORY_RETRIEVAL_DURATION.observe(duration)
        if used_generative:
            MEMORY_GENERATIVE_HITS.inc()
    
    def record_world_model_prediction(self, duration: float) -> None:
        """Record world model prediction."""
        WORLD_MODEL_PREDICTIONS.inc()
        WORLD_MODEL_PREDICTION_DURATION.observe(duration)
    
    def record_code_execution(self, language: str, status: str, duration: float) -> None:
        """Record code execution."""
        CODE_EXECUTIONS.labels(language=language, status=status).inc()
        CODE_EXECUTION_DURATION.observe(duration)
    
    def record_web_search(self) -> None:
        """Record web search."""
        WEB_SEARCHES.inc()
    
    def record_api_request(self, method: str, endpoint: str, status: int, duration: float) -> None:
        """Record API request."""
        status_class = f"{status // 100}xx"
        API_REQUESTS.labels(method=method, endpoint=endpoint, status=status_class).inc()
        API_REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)
    
    def get_metrics(self) -> bytes:
        """Get metrics in Prometheus format."""
        return generate_latest(self.registry)


# Global metrics instance
METRICS = MetricsCollector()


def timed(metric: Histogram):
    """Decorator to time function execution."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                metric.observe(time.time() - start)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                metric.observe(time.time() - start)
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


def track_api_request(endpoint: str):
    """Decorator to track API requests."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()
            status = 200
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = 500
                raise
            finally:
                duration = time.time() - start
                METRICS.record_api_request("GET", endpoint, status, duration)
        return wrapper
    return decorator
