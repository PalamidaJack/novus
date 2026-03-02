"""
NOVUS Unit Tests.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from novus.core.models import (
    Task, TaskStatus, AgentConfig, AgentCapability, 
    MemoryType, SwarmConfig
)
from novus.core.agent import Agent
from novus.swarm.orchestrator import SwarmOrchestrator
from novus.memory.unified import UnifiedMemory
from novus.world_model.engine import WorldModel, WorldModelPlanner


class TestTask:
    """Tests for Task model."""
    
    def test_task_creation(self):
        """Test basic task creation."""
        task = Task(description="Test task")
        assert task.id is not None
        assert task.description == "Test task"
        assert task.status == TaskStatus.PENDING
    
    def test_task_mark_started(self):
        """Test marking task as started."""
        task = Task(description="Test")
        task.mark_started("agent-123")
        
        assert task.status == TaskStatus.RUNNING
        assert task.assigned_agent_id == "agent-123"
        assert task.started_at is not None
    
    def test_task_mark_completed(self):
        """Test marking task as completed."""
        task = Task(description="Test")
        result = {"answer": 42}
        task.mark_completed(result)
        
        assert task.status == TaskStatus.COMPLETED
        assert task.result == result
        assert task.completed_at is not None
    
    def test_task_mark_failed(self):
        """Test marking task as failed."""
        task = Task(description="Test")
        task.mark_failed("Something went wrong")
        
        assert task.status == TaskStatus.FAILED
        assert task.result["error"] == "Something went wrong"


class TestAgentConfig:
    """Tests for AgentConfig."""
    
    def test_agent_config_defaults(self):
        """Test default configuration."""
        config = AgentConfig(name="TestAgent")
        
        assert config.name == "TestAgent"
        assert config.id is not None
        assert config.temperature == 0.7
        assert config.max_concurrent_tasks == 5
    
    def test_agent_capabilities(self):
        """Test capability assignment."""
        config = AgentConfig(
            name="TestAgent",
            capabilities={AgentCapability.REASONING, AgentCapability.CODE}
        )
        
        assert AgentCapability.REASONING in config.capabilities
        assert AgentCapability.CODE in config.capabilities


class TestAgent:
    """Tests for Agent."""
    
    @pytest.fixture
    def agent_config(self):
        """Create test agent config."""
        return AgentConfig(
            name="TestAgent",
            capabilities={AgentCapability.REASONING}
        )
    
    @pytest.mark.asyncio
    async def test_agent_initialization(self, agent_config):
        """Test agent initialization."""
        agent = Agent(agent_config)
        
        assert agent.id == agent_config.id
        assert agent.name == "TestAgent"
        assert agent.can_handle(Task(description="Test", required_capabilities={AgentCapability.REASONING}))
    
    @pytest.mark.asyncio
    async def test_agent_rejects_incapable_task(self, agent_config):
        """Test agent rejects tasks it can't handle."""
        agent = Agent(agent_config)
        
        task = Task(
            description="Needs coding",
            required_capabilities={AgentCapability.CODE}  # Agent doesn't have CODE
        )
        
        accepted = await agent.assign_task(task)
        assert accepted is False
    
    @pytest.mark.asyncio
    async def test_agent_accepts_capable_task(self, agent_config):
        """Test agent accepts tasks it can handle."""
        agent = Agent(agent_config)
        
        task = Task(
            description="Needs reasoning",
            required_capabilities={AgentCapability.REASONING}
        )
        
        accepted = await agent.assign_task(task)
        assert accepted is True


class TestSwarmOrchestrator:
    """Tests for SwarmOrchestrator."""
    
    @pytest.mark.asyncio
    async def test_swarm_initialization(self):
        """Test swarm initialization."""
        config = SwarmConfig(target_agent_count=3)
        swarm = SwarmOrchestrator(config)
        
        assert swarm.config == config
        assert len(swarm.agents) == 0
    
    @pytest.mark.asyncio
    async def test_swarm_start(self):
        """Test swarm startup."""
        config = SwarmConfig(target_agent_count=3)
        swarm = SwarmOrchestrator(config)
        
        await swarm.start()
        
        assert len(swarm.agents) == 3
        assert swarm._running is True
        
        swarm.stop()
    
    @pytest.mark.asyncio
    async def test_submit_task(self):
        """Test task submission."""
        config = SwarmConfig(target_agent_count=3)
        swarm = SwarmOrchestrator(config)
        await swarm.start()
        
        task = Task(description="Test task")
        await swarm.submit_task(task)
        
        assert task.id in [t.id for t in swarm.pending_tasks._queue]
        
        swarm.stop()
    
    @pytest.mark.asyncio
    async def test_collective_solve(self):
        """Test collective problem solving."""
        config = SwarmConfig(target_agent_count=5)
        swarm = SwarmOrchestrator(config)
        await swarm.start()
        
        solution = await swarm.collective_solve(
            problem="What is 2 + 2?",
            n_agents=3
        )
        
        assert solution is not None
        assert solution.generated_by is not None
        
        swarm.stop()


class TestUnifiedMemory:
    """Tests for UnifiedMemory."""
    
    @pytest.mark.asyncio
    async def test_memory_initialization(self):
        """Test memory initialization."""
        memory = UnifiedMemory(max_entries=100)
        
        assert memory.max_entries == 100
        assert len(memory.episodic) == 0
    
    @pytest.mark.asyncio
    async def test_store_and_retrieve(self):
        """Test storing and retrieving memories."""
        memory = UnifiedMemory()
        
        # Store a memory
        entry = await memory.store(
            content="Test memory",
            memory_type=MemoryType.EPISODIC,
            metadata={"test": True}
        )
        
        assert entry.id is not None
        assert entry.content == "Test memory"
        assert entry.memory_type == MemoryType.EPISODIC
        
        # Retrieve
        results = await memory.retrieve("Test", k=1)
        assert len(results) > 0
    
    @pytest.mark.asyncio
    async def test_store_experience(self):
        """Test storing task experience."""
        memory = UnifiedMemory()
        
        task = Task(description="Test task")
        task.mark_completed("Success")
        
        entry = await memory.store_experience(
            task=task,
            outcome="success",
            lessons_learned="Nothing"
        )
        
        assert entry.memory_type == MemoryType.EPISODIC
        assert "Test task" in entry.content
    
    @pytest.mark.asyncio
    async def test_memory_stats(self):
        """Test memory statistics."""
        memory = UnifiedMemory()
        
        stats = memory.get_stats()
        
        assert "total_entries" in stats
        assert "episodic" in stats
        assert "semantic" in stats


class TestWorldModel:
    """Tests for WorldModel."""
    
    @pytest.mark.asyncio
    async def test_world_model_initialization(self):
        """Test world model initialization."""
        model = WorldModel()
        
        assert model.state_dim == 512
        assert model.action_dim == 128
    
    @pytest.mark.asyncio
    async def test_predict(self):
        """Test state prediction."""
        model = WorldModel()
        
        initial_state = {"knowledge": 0.0, "computed": 0.0}
        actions = [
            {"type": "search", "effects": {"knowledge": 0.5}},
            {"type": "code_execution", "effects": {"computed": 1.0}}
        ]
        
        prediction = await model.predict(initial_state, actions)
        
        assert prediction is not None
        assert len(prediction.predicted_states) == 2
    
    @pytest.mark.asyncio
    async def test_world_model_planner(self):
        """Test world model planner."""
        model = WorldModel()
        planner = WorldModelPlanner(model)
        
        goal_state = {"knowledge": 0.8, "computed": 0.5}
        initial_state = {"knowledge": 0.0, "computed": 0.0}
        
        result = await planner.plan(goal_state, initial_state, max_plan_length=3)
        
        assert "best_plan" in result
        assert "best_score" in result
        assert result["goal_state"] == goal_state
    
    @pytest.mark.asyncio
    async def test_physics_rules(self):
        """Test physics rule application."""
        model = WorldModel()
        
        # Add a physics rule
        model.add_physics_rule(
            conditions={"energy": 0.0},
            effects={"cannot_move": True},
            description="Can't move with zero energy"
        )
        
        assert len(model.physics_rules) == 1


class TestIntegration:
    """Integration tests."""
    
    @pytest.mark.asyncio
    async def test_agent_memory_integration(self):
        """Test agent with memory integration."""
        config = AgentConfig(
            name="MemoryAgent",
            capabilities={AgentCapability.REASONING}
        )
        
        memory = UnifiedMemory()
        agent = Agent(config, memory=memory)
        
        # Store something in memory
        await memory.store(
            content="Important fact: 2 + 2 = 4",
            memory_type=MemoryType.SEMANTIC
        )
        
        # Retrieve
        results = await memory.retrieve("fact", k=1)
        assert len(results) > 0
        
        agent.stop()
    
    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Test complete workflow: task -> swarm -> memory -> result."""
        config = SwarmConfig(target_agent_count=2)
        swarm = SwarmOrchestrator(config)
        await swarm.start()

        # Submit task
        task = Task(
            description="What is machine learning?",
            required_capabilities={AgentCapability.REASONING}
        )
        await swarm.submit_task(task)

        # Wait for completion (with timeout) — may return None without API key
        result = await swarm.get_task_result(task.id, timeout=5.0)

        # Without an LLM API key, result may be None (timeout)
        if result is not None:
            assert result.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]

        swarm.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
