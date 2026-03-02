"""
Core Agent implementation for NOVUS.

Agents are the primary actors in the NOVUS system. Each agent has capabilities,
memory, and the ability to execute tasks.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime
from pathlib import Path
import re
import structlog

from novus.core.models import (
    AgentConfig, AgentState, Task, TaskStatus, AgentCapability, Solution
)
from novus.memory.unified import UnifiedMemory
from novus.execution.environment import ExecutionEnvironment
from novus.llm import get_llm_client
from novus.runtime import RecursiveAgentRuntime

logger = structlog.get_logger()


class Agent:
    """
    An autonomous agent in the NOVUS system.
    
    Agents can:
    - Execute tasks using their capabilities
    - Access and update memory
    - Communicate with other agents
    - Learn and improve over time
    """
    
    def __init__(
        self,
        config: AgentConfig,
        memory: Optional[UnifiedMemory] = None,
        execution_env: Optional[ExecutionEnvironment] = None
    ):
        self.config = config
        self.state = AgentState(agent_id=config.id)
        self.memory = memory or UnifiedMemory()
        self.execution_env = execution_env or ExecutionEnvironment()
        
        self._task_queue: asyncio.Queue[Task] = asyncio.Queue()
        self._running = False
        self._task_handlers: Dict[AgentCapability, Callable[[Task], Any]] = {}
        self._runtime = RecursiveAgentRuntime(
            llm_caller=self._runtime_llm_call,
            execution_env=self.execution_env,
        )
        
        self._setup_default_handlers()
        
        logger.info(
            "agent_initialized",
            agent_id=config.id,
            name=config.name,
            capabilities=[c.value for c in config.capabilities]
        )
    
    def _setup_default_handlers(self) -> None:
        """Register default task handlers for each capability."""
        self._task_handlers = {
            AgentCapability.REASONING: self._handle_reasoning,
            AgentCapability.RESEARCH: self._handle_research,
            AgentCapability.CODE: self._handle_code,
            AgentCapability.CREATIVE: self._handle_creative,
            AgentCapability.ANALYSIS: self._handle_analysis,
            AgentCapability.VERIFICATION: self._handle_verification,
            AgentCapability.COORDINATION: self._handle_coordination,
        }
    
    @property
    def id(self) -> str:
        """Agent ID."""
        return self.config.id
    
    @property
    def name(self) -> str:
        """Agent name."""
        return self.config.name
    
    @property
    def capabilities(self) -> set[AgentCapability]:
        """Agent capabilities."""
        return self.config.capabilities
    
    def can_handle(self, task: Task) -> bool:
        """Check if agent can handle a task."""
        return self.config.capabilities >= task.required_capabilities
    
    async def start(self) -> None:
        """Start the agent's main loop."""
        self._running = True
        logger.info("agent_started", agent_id=self.id)
        
        while self._running:
            try:
                task = await asyncio.wait_for(
                    self._task_queue.get(),
                    timeout=1.0
                )
                await self._execute_task(task)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("agent_loop_error", agent_id=self.id, error=str(e))
    
    def stop(self) -> None:
        """Stop the agent."""
        self._running = False
        logger.info("agent_stopped", agent_id=self.id)
    
    async def assign_task(self, task: Task) -> bool:
        """
        Assign a task to this agent.
        
        Returns True if accepted, False if agent cannot handle it.
        """
        if not self.can_handle(task):
            logger.warning(
                "task_rejected_capability_mismatch",
                agent_id=self.id,
                task_id=task.id,
                required=[c.value for c in task.required_capabilities],
                available=[c.value for c in self.capabilities]
            )
            return False
        
        if len(self.state.active_tasks) >= self.config.max_concurrent_tasks:
            logger.warning(
                "task_rejected_at_capacity",
                agent_id=self.id,
                task_id=task.id,
                active_tasks=len(self.state.active_tasks)
            )
            return False
        
        await self._task_queue.put(task)
        task.mark_assigned(self.id)
        self.state.active_tasks.append(task.id)
        
        logger.info("task_assigned", agent_id=self.id, task_id=task.id)
        return True
    
    async def _execute_task(self, task: Task) -> None:
        """Execute a single task."""
        start_time = time.time()
        task.mark_started(self.id)
        self.state.status = "busy"
        self.state.current_task_id = task.id
        
        logger.info("task_started", agent_id=self.id, task_id=task.id)
        
        try:
            # Determine primary capability for this task
            primary_capability = self._select_capability(task)
            handler = self._task_handlers.get(primary_capability)
            
            if handler is None:
                raise ValueError(f"No handler for capability: {primary_capability}")
            
            # Execute with timeout
            result = await asyncio.wait_for(
                handler(task),
                timeout=self.config.timeout_seconds
            )
            
            # Mark success
            task.mark_completed(result)
            self.state.tasks_completed += 1
            
            # Store in memory
            await self.memory.store_experience(
                task=task,
                outcome="success",
                lessons_learned=None
            )
            
            logger.info(
                "task_completed",
                agent_id=self.id,
                task_id=task.id,
                duration_seconds=time.time() - start_time
            )
            
        except asyncio.TimeoutError:
            error_msg = f"Task timed out after {self.config.timeout_seconds}s"
            task.mark_failed(error_msg)
            self.state.tasks_failed += 1
            logger.error("task_timeout", agent_id=self.id, task_id=task.id)
            
        except Exception as e:
            error_msg = str(e)
            task.mark_failed(error_msg)
            self.state.tasks_failed += 1
            
            await self.memory.store_experience(
                task=task,
                outcome="failure",
                lessons_learned=error_msg
            )
            
            logger.error(
                "task_failed",
                agent_id=self.id,
                task_id=task.id,
                error=error_msg
            )
        
        finally:
            # Cleanup
            self.state.total_compute_time += time.time() - start_time
            if task.id in self.state.active_tasks:
                self.state.active_tasks.remove(task.id)
            self.state.current_task_id = None
            self.state.status = "idle" if not self.state.active_tasks else "busy"
    
    def _select_capability(self, task: Task) -> AgentCapability:
        """Select the primary capability for a task."""
        # Priority order for multi-capability tasks
        priority = [
            AgentCapability.REASONING,
            AgentCapability.VERIFICATION,
            AgentCapability.COORDINATION,
            AgentCapability.RESEARCH,
            AgentCapability.CODE,
            AgentCapability.ANALYSIS,
            AgentCapability.CREATIVE,
        ]
        
        for cap in priority:
            if cap in task.required_capabilities and cap in self.capabilities:
                return cap
        
        # Fallback to any matching capability
        return next(iter(task.required_capabilities & self.capabilities))
    
    # Task Handlers
    
    async def _handle_reasoning(self, task: Task) -> Solution:
        """Handle reasoning tasks."""
        # Retrieve relevant context from memory
        context = await self.memory.retrieve_relevant(task.description, k=5)
        
        # Use LLM for reasoning
        prompt = self._build_reasoning_prompt(task, context)
        response = await self._call_llm(prompt)
        
        return Solution(
            task_id=task.id,
            content=response,
            confidence=0.85,
            generated_by=self.id,
            reasoning_trace=prompt
        )
    
    async def _handle_research(self, task: Task) -> Solution:
        """Handle research tasks."""
        # Multi-step research process
        findings = []
        
        # Step 1: Information gathering
        search_results = await self.execution_env.search_web(task.description)
        findings.extend(search_results)
        
        # Step 2: Synthesis
        synthesis = await self._call_llm(
            f"Synthesize these findings about '{task.description}':\n{findings}"
        )
        
        return Solution(
            task_id=task.id,
            content={"synthesis": synthesis, "sources": findings},
            confidence=0.75,
            generated_by=self.id
        )
    
    async def _handle_code(self, task: Task) -> Solution:
        """Handle coding tasks."""
        # Generate code
        code = await self._call_llm(
            f"Write code for: {task.description}\n"
            f"Constraints: {task.constraints}"
        )
        
        # Execute in sandbox
        result = await self.execution_env.execute_code(code)
        
        return Solution(
            task_id=task.id,
            content={"code": code, "execution_result": result},
            confidence=0.9 if result.success else 0.5,
            generated_by=self.id
        )
    
    async def _handle_creative(self, task: Task) -> Solution:
        """Handle creative tasks."""
        # Generate multiple creative options
        options = []
        for _ in range(3):
            option = await self._call_llm(
                f"Creative solution for: {task.description}\n"
                f"Generate a novel, unexpected approach."
            )
            options.append(option)
        
        # Select best or combine
        best = await self._call_llm(
            f"Evaluate these creative options and select/improve the best:\n{options}"
        )
        
        return Solution(
            task_id=task.id,
            content={"options": options, "selected": best},
            confidence=0.7,
            generated_by=self.id
        )
    
    async def _handle_analysis(self, task: Task) -> Solution:
        """Handle analysis tasks."""
        # Structured analysis
        analysis = await self._call_llm(
            f"Analyze: {task.description}\n"
            f"Provide: 1) Key findings 2) Patterns 3) Implications 4) Recommendations"
        )
        
        return Solution(
            task_id=task.id,
            content=analysis,
            confidence=0.8,
            generated_by=self.id
        )
    
    async def _handle_verification(self, task: Task) -> Solution:
        """Handle verification tasks."""
        # Verify a solution or claim
        target = task.constraints.get("target_solution", task.description)
        
        verification = await self._call_llm(
            f"Critically verify this claim/solution: {target}\n"
            f"Look for: errors, assumptions, edge cases, missing information"
        )
        
        return Solution(
            task_id=task.id,
            content=verification,
            confidence=0.75,
            generated_by=self.id
        )
    
    async def _handle_coordination(self, task: Task) -> Solution:
        """Handle coordination tasks."""
        # Coordinate between agents
        plan = await self._call_llm(
            f"Create coordination plan for: {task.description}\n"
            f"Subtasks: {task.subtasks}\n"
            f"Dependencies: {task.dependencies}"
        )
        
        return Solution(
            task_id=task.id,
            content=plan,
            confidence=0.85,
            generated_by=self.id
        )
    
    # Helper methods
    
    def _build_reasoning_prompt(self, task: Task, context: list) -> str:
        """Build a reasoning prompt with context."""
        return f"""You are an expert reasoning agent. Solve this problem step by step.

Task: {task.description}

Relevant context from memory:
{chr(10).join(f"- {c}" for c in context)}

Think through this carefully, considering:
1. What is the core problem?
2. What approaches could work?
3. What are the tradeoffs?
4. What is your final recommendation?

Provide your reasoning and solution."""
    
    async def _call_llm(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None
    ) -> str:
        """Call the LLM backend."""
        try:
            client = get_llm_client(
                provider=getattr(self.config, 'llm_provider', 'openai'),
                model=model or getattr(self.config, 'model_name', None)
            )
            
            return await client.complete(
                prompt=prompt,
                system=system,
                temperature=temperature or self.config.temperature,
                max_tokens=getattr(self.config, 'max_tokens', 1024)
            )
        except Exception as e:
            logger.error("llm_call_failed", agent_id=self.id, error=str(e))
            # Return error message that can be handled by caller
            return f"[Error: LLM call failed - {str(e)}]"

    async def _runtime_llm_call(self, prompt: str, model: Optional[str] = None) -> str:
        """Runtime adapter used by RecursiveAgentRuntime."""
        return await self._call_llm(prompt=prompt, model=model, temperature=self.config.temperature)

    async def run(self, prompt: str) -> str:
        """
        Direct run interface for evaluation/runtime usage.

        Uses the recursive runtime loop and falls back to a small local
        deterministic solver for simple arithmetic when no model is available.
        """
        result = await self._runtime.run(prompt, task_type="reason")
        text = str(result)
        if text.startswith("[Error: LLM call failed") or text == "Reached max turns":
            return self._local_fallback(prompt)
        return text

    def _local_fallback(self, prompt: str) -> str:
        """
        Deterministic fallback for offline environments (tests/CI/dev shells).
        """
        normalized = prompt.lower().strip()
        expr_match = re.search(r"(-?\d+(?:\.\d+)?)\s*([+\-*/])\s*(-?\d+(?:\.\d+)?)", normalized)
        if expr_match:
            a = float(expr_match.group(1))
            op = expr_match.group(2)
            b = float(expr_match.group(3))
            if op == "+":
                value = a + b
            elif op == "-":
                value = a - b
            elif op == "*":
                value = a * b
            else:
                value = a / b if b != 0 else float("inf")
            if value.is_integer():
                return str(int(value))
            return str(value)
        return "Unable to answer without model access"

    def get_last_session_id(self) -> Optional[str]:
        """Return last runtime session id if available."""
        return self._runtime.last_session_id

    def get_last_run_artifact_path(self) -> Optional[Path]:
        """Return JSONL artifact path for last run if available."""
        if not self._runtime.last_session_id:
            return None
        return self._runtime.artifact_logger.run_path(self._runtime.last_session_id)
    
    def get_health(self) -> Dict[str, Any]:
        """Get agent health status."""
        return {
            "agent_id": self.id,
            "status": self.state.status,
            "active_tasks": len(self.state.active_tasks),
            "total_completed": self.state.tasks_completed,
            "total_failed": self.state.tasks_failed,
            "avg_task_time": (
                self.state.total_compute_time / max(1, self.state.tasks_completed)
            ),
            "capabilities": [c.value for c in self.capabilities],
        }
