"""
Core data models and types for NOVUS.

All domain objects are implemented as Pydantic models for validation,
serialization, and type safety.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Callable
from pydantic import BaseModel, Field, ConfigDict


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TaskStatus(str, Enum):
    """Task lifecycle states."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(int, Enum):
    """Task priority levels."""
    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4
    BACKGROUND = 5


class AgentCapability(str, Enum):
    """Agent capability types."""
    REASONING = "reasoning"
    RESEARCH = "research"
    CODE = "code"
    CREATIVE = "creative"
    ANALYSIS = "analysis"
    VERIFICATION = "verification"
    COORDINATION = "coordination"


class MemoryType(str, Enum):
    """Types of memory storage."""
    EPISODIC = "episodic"      # Event-based memories
    SEMANTIC = "semantic"      # Factual knowledge
    PROCEDURAL = "procedural"  # Skills/workflows
    GENERATIVE = "generative"  # Synthesized memories


class Task(BaseModel):
    """
    A unit of work to be executed by the NOVUS system.
    
    Tasks are the fundamental unit of work in NOVUS. They can be
    simple (single-step) or complex (multi-step, requiring decomposition).
    """
    model_config = ConfigDict(frozen=False)
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: Optional[str] = None
    description: str
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    
    # Requirements
    required_capabilities: Set[AgentCapability] = Field(default_factory=set)
    constraints: Dict[str, Any] = Field(default_factory=dict)
    
    # Metadata
    created_at: datetime = Field(default_factory=_utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    assigned_agent_id: Optional[str] = None
    
    # Results
    result: Optional[Any] = None
    artifacts: List[str] = Field(default_factory=list)
    metrics: Dict[str, float] = Field(default_factory=dict)
    
    # Decomposition
    subtasks: List[Task] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    
    def mark_assigned(self, agent_id: str) -> None:
        """Mark task as assigned to an agent."""
        self.status = TaskStatus.ASSIGNED
        self.assigned_agent_id = agent_id

    def mark_started(self, agent_id: str) -> None:
        """Mark task as started by an agent."""
        self.status = TaskStatus.RUNNING
        self.started_at = _utcnow()
        self.assigned_agent_id = agent_id
    
    def mark_completed(self, result: Any) -> None:
        """Mark task as completed with result."""
        self.status = TaskStatus.COMPLETED
        self.completed_at = _utcnow()
        self.result = result
    
    def mark_failed(self, error: str) -> None:
        """Mark task as failed with error."""
        self.status = TaskStatus.FAILED
        self.completed_at = _utcnow()
        self.result = {"error": error}


class AgentConfig(BaseModel):
    """Configuration for an agent."""
    model_config = ConfigDict(frozen=False)
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    capabilities: Set[AgentCapability] = Field(default_factory=set)
    
    # Model configuration
    llm_provider: str = "openai"  # openai, anthropic, local, etc.
    model_name: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 4096
    
    # Resource limits
    max_concurrent_tasks: int = 5
    timeout_seconds: int = 300
    
    # Specialization
    domain_expertise: List[str] = Field(default_factory=list)
    tool_access: List[str] = Field(default_factory=list)
    
    # Memory
    memory_enabled: bool = True
    memory_limit_mb: int = 1024


class AgentState(BaseModel):
    """Runtime state of an agent."""
    model_config = ConfigDict(frozen=False)
    
    agent_id: str
    status: str = "idle"  # idle, busy, error
    current_task_id: Optional[str] = None
    active_tasks: List[str] = Field(default_factory=list)
    
    # Performance metrics
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_compute_time: float = 0.0
    
    # Load metrics
    last_heartbeat: datetime = Field(default_factory=_utcnow)
    cpu_percent: float = 0.0
    memory_percent: float = 0.0


class Solution(BaseModel):
    """A solution produced by the system."""
    model_config = ConfigDict(frozen=False)
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    
    # Solution content
    content: Any
    confidence: float = Field(ge=0.0, le=1.0)
    novelty_score: Optional[float] = None
    verification_status: str = "unverified"
    
    # Provenance
    generated_by: str
    generated_at: datetime = Field(default_factory=_utcnow)
    reasoning_trace: Optional[str] = None
    
    # Validation
    validation_results: List[ValidationResult] = Field(default_factory=list)


class ValidationResult(BaseModel):
    """Result of solution validation."""
    model_config = ConfigDict(frozen=False)
    
    validator_id: str
    passed: bool
    score: float
    feedback: str
    validated_at: datetime = Field(default_factory=_utcnow)


class MemoryEntry(BaseModel):
    """A single memory entry."""
    model_config = ConfigDict(frozen=False)
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    memory_type: MemoryType
    
    # Content
    content: str
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Temporal
    created_at: datetime = Field(default_factory=_utcnow)
    last_accessed: datetime = Field(default_factory=_utcnow)
    access_count: int = 0
    
    # Relationships
    related_entries: List[str] = Field(default_factory=list)
    source_task_id: Optional[str] = None
    
    def touch(self) -> None:
        """Update access metadata."""
        self.last_accessed = _utcnow()
        self.access_count += 1


class SwarmConfig(BaseModel):
    """Configuration for the swarm orchestrator."""
    model_config = ConfigDict(frozen=False)
    
    # Population settings
    min_agents: int = 3
    max_agents: int = 100
    target_agent_count: int = 10
    
    # Evolution settings
    enable_evolution: bool = True
    evolution_interval_seconds: int = 3600
    selection_pressure: float = 0.3
    mutation_rate: float = 0.1
    
    # Consensus settings
    consensus_threshold: float = 0.75
    max_consensus_rounds: int = 10
    
    # Communication
    communication_protocol: str = "async"  # async, sync, hybrid
    message_ttl_seconds: int = 300


class WorldModelPrediction(BaseModel):
    """A prediction from the world model."""
    model_config = ConfigDict(frozen=False)
    
    initial_state: Dict[str, Any]
    actions: List[Dict[str, Any]]
    predicted_states: List[Dict[str, Any]]
    
    # Uncertainty
    confidence_intervals: List[Dict[str, float]] = Field(default_factory=list)
    probability_distribution: Optional[Dict[str, float]] = None
    
    # Metadata
    model_version: str
    prediction_time_ms: float


class Experiment(BaseModel):
    """An experiment designed to test a hypothesis."""
    model_config = ConfigDict(frozen=False)
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    hypothesis_id: str
    
    # Design
    experiment_type: str  # simulation, lab, field, computational
    design: Dict[str, Any]
    variables: Dict[str, Any]
    
    # Execution
    status: str = "designed"
    results: Optional[Dict[str, Any]] = None
    analysis: Optional[str] = None
    
    # Metadata
    created_at: datetime = Field(default_factory=_utcnow)
    executed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
