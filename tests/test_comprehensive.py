"""
Comprehensive test suite for NOVUS.

Run with: pytest tests/ -v
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile
import shutil

# Test all core modules
from novus.core.models import (
    Task, TaskStatus, TaskPriority, AgentConfig, AgentCapability,
    Solution, MemoryEntry, MemoryType, SwarmConfig
)
from novus.core.agent import Agent
from novus.swarm.orchestrator import SwarmOrchestrator, AgentFitness
from novus.memory.unified import UnifiedMemory
from novus.execution.environment import ExecutionEnvironment
from novus.world_model.engine import WorldModel, WorldModelPlanner


# Fixtures

@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    tmp = tempfile.mkdtemp()
    yield tmp
    shutil.rmtree(tmp)


@pytest.fixture
def agent_config():
    """Create test agent config."""
    return AgentConfig(
        name="TestAgent",
        capabilities={AgentCapability.REASONING, AgentCapability.CODE},
        temperature=0.5
    )


@pytest.fixture
def basic_task():
    """Create basic test task."""
    return Task(
        description="Test task",
        required_capabilities={AgentCapability.REASONING}
    )


# Core Model Tests

class TestTaskModel:
    """Tests for Task model."""
    
    def test_task_creation(self):
        """Test basic task creation."""
        task = Task(description="Simple test")
        assert task.id is not None
        assert task.description == "Simple test"
        assert task.status == TaskStatus.PENDING
        assert task.priority == TaskPriority.NORMAL
    
    def test_task_lifecycle(self):
        """Test task status transitions."""
        task = Task(description="Lifecycle test")
        
        # Start
        task.mark_started("agent-123")
        assert task.status == TaskStatus.RUNNING
        assert task.assigned_agent_id == "agent-123"
        assert task.started_at is not None
        
        # Complete
        task.mark_completed({"result": "success"})
        assert task.status == TaskStatus.COMPLETED
        assert task.result == {"result": "success"}
        assert task.completed_at is not None
        
        # New task for failure test
        task2 = Task(description="Fail test")
        task2.mark_failed("Something went wrong")
        assert task2.status == TaskStatus.FAILED
        assert "error" in task2.result
    
    def test_task_priority_ordering(self):
        """Test priority enum ordering."""
        assert TaskPriority.CRITICAL < TaskPriority.HIGH
        assert TaskPriority.HIGH < TaskPriority.NORMAL
        assert TaskPriority.NORMAL < TaskPriority.LOW


class TestAgentConfig:
    """Tests for AgentConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = AgentConfig(name="Test")
        assert config.name == "Test"
        assert config.temperature == 0.7
        assert config.max_concurrent_tasks == 5
        assert config.timeout_seconds == 300
    
    def test_capabilities_assignment(self):
        """Test capability assignment."""
        config = AgentConfig(
            name="Specialist",
            capabilities={AgentCapability.RESEARCH, AgentCapability.ANALYSIS}
        )
        assert AgentCapability.RESEARCH in config.capabilities
        assert AgentCapability.ANALYSIS in config.capabilities
        assert AgentCapability.CODE not in config.capabilities


# Agent Tests

@pytest.mark.asyncio
class TestAgent:
    """Tests for Agent class."""
    
    async def test_agent_initialization(self, agent_config):
        """Test agent initialization."""
        agent = Agent(agent_config)
        assert agent.id == agent_config.id
        assert agent.name == "TestAgent"
        assert len(agent.capabilities) == 2
    
    async def test_agent_can_handle(self, agent_config, basic_task):
        """Test capability checking."""
        agent = Agent(agent_config)
        
        # Can handle matching task
        assert agent.can_handle(basic_task) is True
        
        # Cannot handle task requiring missing capability
        hard_task = Task(
            description="Hard task",
            required_capabilities={AgentCapability.CREATIVE}
        )
        assert agent.can_handle(hard_task) is False
    
    async def test_agent_task_assignment(self, agent_config, basic_task):
        """Test task assignment."""
        agent = Agent(agent_config)
        
        # Accept capable task
        accepted = await agent.assign_task(basic_task)
        assert accepted is True
        assert basic_task.id in agent.state.active_tasks
        
        # Reject incapable task
        creative_task = Task(
            description="Creative",
            required_capabilities={AgentCapability.CREATIVE}
        )
        accepted = await agent.assign_task(creative_task)
        assert accepted is False


# Swarm Tests

@pytest.mark.asyncio
class TestSwarmOrchestrator:
    """Tests for SwarmOrchestrator."""
    
    async def test_swarm_initialization(self):
        """Test swarm setup."""
        config = SwarmConfig(target_agent_count=3)
        swarm = SwarmOrchestrator(config)
        
        assert swarm.config == config
        assert len(swarm.agents) == 0
    
    async def test_swarm_start_stop(self):
        """Test swarm lifecycle."""
        config = SwarmConfig(target_agent_count=2)
        swarm = SwarmOrchestrator(config)
        
        await swarm.start()
        assert len(swarm.agents) == 2
        assert swarm._running is True
        
        swarm.stop()
        assert swarm._running is False
    
    async def test_task_submission(self):
        """Test task submission."""
        config = SwarmConfig(target_agent_count=2)
        swarm = SwarmOrchestrator(config)
        await swarm.start()
        
        task = Task(description="Test submission")
        task_id = await swarm.submit_task(task)
        
        assert task_id == task.id
        # Task should be in queue
        
        swarm.stop()
    
    async def test_collective_solve(self):
        """Test collective problem solving."""
        config = SwarmConfig(target_agent_count=3)
        swarm = SwarmOrchestrator(config)
        await swarm.start()
        
        solution = await swarm.collective_solve(
            problem="What is 2+2?",
            n_agents=2
        )
        
        assert solution is not None
        assert solution.generated_by is not None
        assert 0 <= solution.confidence <= 1
        
        swarm.stop()


# Memory Tests

@pytest.mark.asyncio
class TestUnifiedMemory:
    """Tests for UnifiedMemory."""
    
    async def test_memory_initialization(self):
        """Test memory setup."""
        memory = UnifiedMemory(max_entries=100)
        assert memory.max_entries == 100
        assert len(memory.episodic) == 0
    
    async def test_store_and_retrieve(self):
        """Test memory storage and retrieval."""
        memory = UnifiedMemory()
        
        # Store memory
        entry = await memory.store(
            content="Test memory",
            memory_type=MemoryType.EPISODIC,
            metadata={"test": True}
        )
        
        assert entry.id is not None
        assert entry.content == "Test memory"
        
        # Retrieve
        results = await memory.retrieve("Test", k=1)
        assert len(results) > 0
    
    async def test_experience_storage(self):
        """Test storing task experiences."""
        memory = UnifiedMemory()
        
        task = Task(description="Test task")
        task.mark_completed("Success")
        
        entry = await memory.store_experience(
            task=task,
            outcome="success",
            lessons_learned="Test lesson"
        )
        
        assert entry.memory_type == MemoryType.EPISODIC
        assert "Test task" in entry.content


# Execution Tests

@pytest.mark.asyncio
class TestExecutionEnvironment:
    """Tests for ExecutionEnvironment."""
    
    async def test_code_execution(self, temp_dir):
        """Test code execution."""
        env = ExecutionEnvironment(sandbox_dir=temp_dir)
        
        result = await env.execute_code("print('Hello')")
        
        assert result.success is True
        assert "Hello" in result.output
    
    async def test_execution_timeout(self, temp_dir):
        """Test execution timeout."""
        env = ExecutionEnvironment(
            max_execution_time=1,
            sandbox_dir=temp_dir
        )
        
        # Code that runs forever
        result = await env.execute_code("import time; time.sleep(10)")
        
        assert result.success is False
        assert "timeout" in result.error.lower()
    
    async def test_shell_command(self, temp_dir):
        """Test shell command execution."""
        env = ExecutionEnvironment(sandbox_dir=temp_dir)
        
        result = await env.execute_shell("echo test")
        
        assert result.success is True
        assert "test" in result.output


# World Model Tests

@pytest.mark.asyncio
class TestWorldModel:
    """Tests for WorldModel."""
    
    async def test_prediction(self):
        """Test state prediction."""
        model = WorldModel()
        
        initial = {"knowledge": 0.0}
        actions = [
            {"type": "search", "effects": {"knowledge": 0.5}}
        ]
        
        prediction = await model.predict(initial, actions)
        
        assert prediction is not None
        assert len(prediction.predicted_states) == 1
    
    async def test_counterfactual(self):
        """Test counterfactual reasoning."""
        model = WorldModel()
        
        initial = {"value": 0}
        actual = [{"type": "add", "effects": {"value": 1}}]
        hypothetical = [{"type": "add", "effects": {"value": 2}}]
        
        result = await model.simulate_counterfactual(
            initial, actual, hypothetical
        )
        
        assert "actual_outcome" in result
        assert "hypothetical_outcome" in result


# Integration Tests

@pytest.mark.asyncio
class TestIntegration:
    """Integration tests."""
    
    async def test_end_to_end_task(self):
        """Test full task execution flow."""
        from novus.swarm.orchestrator import SwarmOrchestrator
        from novus.core.models import SwarmConfig
        
        # Setup
        config = SwarmConfig(target_agent_count=2)
        swarm = SwarmOrchestrator(config)
        await swarm.start()
        
        # Submit task
        task = Task(
            description="Integration test task",
            required_capabilities={AgentCapability.REASONING}
        )
        await swarm.submit_task(task)
        
        # Wait a bit
        await asyncio.sleep(0.5)
        
        # Cleanup
        swarm.stop()
        
        # Task should have been processed
        assert task.status in [TaskStatus.RUNNING, TaskStatus.COMPLETED, TaskStatus.FAILED]
    
    async def test_agent_memory_integration(self):
        """Test agent with memory."""
        from novus.memory.unified import UnifiedMemory
        
        memory = UnifiedMemory()
        await memory.store(
            content="Important fact",
            memory_type=MemoryType.SEMANTIC
        )
        
        results = await memory.retrieve("fact", k=1)
        assert len(results) > 0


# Performance Tests

@pytest.mark.slow
class TestPerformance:
    """Performance tests (marked as slow)."""
    
    @pytest.mark.asyncio
    async def test_swarm_scaling(self):
        """Test swarm with many agents."""
        from novus.swarm.orchestrator import SwarmOrchestrator
        from novus.core.models import SwarmConfig
        
        config = SwarmConfig(target_agent_count=10)
        swarm = SwarmOrchestrator(config)
        await swarm.start()
        
        assert len(swarm.agents) == 10
        
        swarm.stop()
    
    @pytest.mark.asyncio
    async def test_memory_retrieval_speed(self):
        """Test memory retrieval performance."""
        import time
        from novus.memory.unified import UnifiedMemory
        
        memory = UnifiedMemory()
        
        # Add many memories
        for i in range(100):
            await memory.store(
                content=f"Memory {i}",
                memory_type=MemoryType.EPISODIC
            )
        
        # Time retrieval
        start = time.time()
        results = await memory.retrieve("test", k=5)
        elapsed = time.time() - start
        
        assert elapsed < 1.0  # Should be fast


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
