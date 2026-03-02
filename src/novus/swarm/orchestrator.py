"""
Swarm Orchestrator for NOVUS.

Manages populations of agents, implements evolutionary optimization,
and enables collective intelligence through swarming behaviors.
"""

from __future__ import annotations

import asyncio
import random
import heapq
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime, timezone
from dataclasses import dataclass, field
import structlog

from novus.core.models import (
    AgentConfig, AgentCapability, Task, TaskStatus, 
    Solution, SwarmConfig, AgentState
)
from novus.core.agent import Agent
from novus.monitoring import METRICS

logger = structlog.get_logger()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class AgentFitness:
    """Fitness metrics for an agent in evolution."""
    agent_id: str
    success_rate: float = 0.0
    avg_quality: float = 0.0
    efficiency: float = 0.0  # tasks per unit time
    diversity_contribution: float = 0.0
    
    @property
    def overall(self) -> float:
        """Overall fitness score."""
        return (
            self.success_rate * 0.4 +
            self.avg_quality * 0.3 +
            self.efficiency * 0.2 +
            self.diversity_contribution * 0.1
        )


class SwarmOrchestrator:
    """
    Orchestrates a swarm of agents for collective problem-solving.
    
    Key features:
    - Dynamic agent pool management
    - Evolutionary optimization (SOHM-inspired)
    - Consensus-based decision making
    - Task routing and load balancing
    """
    
    def __init__(self, config: Optional[SwarmConfig] = None):
        self.config = config or SwarmConfig()
        self.agents: Dict[str, Agent] = {}
        self.agent_fitness: Dict[str, AgentFitness] = {}
        
        # Task management
        self.pending_tasks: asyncio.Queue[Task] = asyncio.Queue()
        self.task_assignments: Dict[str, str] = {}  # task_id -> agent_id
        self.completed_tasks: Dict[str, Task] = {}
        self.all_tasks: Dict[str, Task] = {}
        
        # Evolution state
        self.generation = 0
        self.last_evolution = _utcnow()
        
        # Consensus state
        self.proposals: Dict[str, List[Solution]] = {}
        
        self._running = False
        self._evolution_task: Optional[asyncio.Task] = None
        
        logger.info(
            "swarm_orchestrator_initialized",
            min_agents=self.config.min_agents,
            max_agents=self.config.max_agents
        )
    
    async def start(self) -> None:
        """Start the orchestrator."""
        self._running = True
        
        # Initialize minimum agents
        await self._initialize_population()
        
        # Start evolution loop
        if self.config.enable_evolution:
            self._evolution_task = asyncio.create_task(self._evolution_loop())
        
        # Start task distribution loop
        asyncio.create_task(self._task_distribution_loop())
        
        logger.info("swarm_orchestrator_started", agent_count=len(self.agents))
    
    def stop(self) -> None:
        """Stop the orchestrator."""
        self._running = False
        if self._evolution_task:
            self._evolution_task.cancel()
        
        for agent in self.agents.values():
            agent.stop()
        
        logger.info("swarm_orchestrator_stopped")
    
    async def submit_task(self, task: Task) -> str:
        """
        Submit a task to the swarm.
        
        Returns the task ID for tracking.
        """
        self.all_tasks[task.id] = task
        await self.pending_tasks.put(task)
        
        # Record metrics
        primary_cap = next(iter(task.required_capabilities), AgentCapability.REASONING)
        METRICS.record_task_submitted(
            priority=task.priority.name.lower(),
            capability=primary_cap.value
        )
        METRICS.update_task_queue_size(self.pending_tasks.qsize())
        
        logger.info("task_submitted", task_id=task.id, description=task.description[:50])
        return task.id
    
    async def get_task_result(self, task_id: str, timeout: Optional[float] = None) -> Optional[Task]:
        """Wait for and return task result."""
        start_time = _utcnow()
        
        while True:
            if task_id in self.completed_tasks:
                return self.completed_tasks[task_id]
            
            if timeout:
                elapsed = (_utcnow() - start_time).total_seconds()
                if elapsed > timeout:
                    return None
            
            await asyncio.sleep(0.1)
    
    async def collective_solve(
        self,
        problem: str,
        required_capabilities: Optional[Set[AgentCapability]] = None,
        n_agents: int = 5,
        consensus_threshold: Optional[float] = None
    ) -> Solution:
        """
        Use collective intelligence to solve a problem.
        
        Spawns multiple agents to work on the problem and reaches
        consensus on the best solution.
        """
        threshold = consensus_threshold or self.config.consensus_threshold
        
        # Create task
        task = Task(
            description=problem,
            required_capabilities=required_capabilities or {AgentCapability.REASONING}
        )
        
        # Select diverse agents
        selected_agents = self._select_diverse_agents(n_agents, task)
        
        logger.info(
            "collective_solve_started",
            task_id=task.id,
            n_agents=len(selected_agents)
        )
        
        # Assign to all selected agents
        solutions = []
        for agent in selected_agents:
            task_copy = Task(
                description=problem,
                required_capabilities=task.required_capabilities,
                parent_id=task.id
            )
            accepted = await agent.assign_task(task_copy)
            if accepted:
                solutions.append(self._await_solution(agent, task_copy))
        
        # Wait for all solutions
        results = await asyncio.gather(*solutions, return_exceptions=True)
        valid_solutions = [r for r in results if isinstance(r, Solution)]
        
        # Reach consensus
        best_solution = self._reach_consensus(valid_solutions, threshold)
        
        logger.info(
            "collective_solve_completed",
            task_id=task.id,
            n_solutions=len(valid_solutions),
            confidence=best_solution.confidence if best_solution else 0.0
        )
        
        return best_solution or Solution(
            task_id=task.id,
            content="No consensus reached",
            confidence=0.0,
            generated_by="swarm"
        )
    
    async def _initialize_population(self) -> None:
        """Initialize the agent population."""
        # Create diverse initial agents
        agent_types = [
            {
                "name": "Reasoner-Alpha",
                "capabilities": {AgentCapability.REASONING, AgentCapability.ANALYSIS},
                "temperature": 0.3,
            },
            {
                "name": "Researcher-Beta",
                "capabilities": {AgentCapability.RESEARCH, AgentCapability.ANALYSIS},
                "temperature": 0.5,
            },
            {
                "name": "Coder-Gamma",
                "capabilities": {AgentCapability.CODE, AgentCapability.REASONING},
                "temperature": 0.2,
            },
            {
                "name": "Creative-Delta",
                "capabilities": {AgentCapability.CREATIVE, AgentCapability.REASONING},
                "temperature": 0.8,
            },
            {
                "name": "Verifier-Epsilon",
                "capabilities": {AgentCapability.VERIFICATION, AgentCapability.ANALYSIS},
                "temperature": 0.1,
            },
            {
                "name": "Coordinator-Zeta",
                "capabilities": {AgentCapability.COORDINATION, AgentCapability.REASONING},
                "temperature": 0.4,
            },
        ]
        
        for i in range(self.config.target_agent_count):
            agent_type = agent_types[i % len(agent_types)]
            config = AgentConfig(
                name=f"{agent_type['name']}-{i+1}",
                capabilities=agent_type["capabilities"],
                temperature=agent_type["temperature"],
            )
            
            agent = Agent(config)
            self.agents[agent.id] = agent
            self.agent_fitness[agent.id] = AgentFitness(agent_id=agent.id)
            
            # Start agent
            asyncio.create_task(agent.start())
        
        logger.info("population_initialized", count=len(self.agents))
    
    async def _task_distribution_loop(self) -> None:
        """Main loop for distributing tasks to agents."""
        while self._running:
            try:
                task = await asyncio.wait_for(
                    self.pending_tasks.get(),
                    timeout=1.0
                )
                
                await self._route_task(task)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("task_distribution_error", error=str(e))
    
    async def _route_task(self, task: Task) -> bool:
        """Route a task to the best available agent(s)."""
        # Find capable agents
        capable_agents = [
            agent for agent in self.agents.values()
            if agent.can_handle(task) and len(agent.state.active_tasks) < agent.config.max_concurrent_tasks
        ]
        
        if not capable_agents:
            logger.warning("no_capable_agents", task_id=task.id)
            # Re-queue with delay
            await asyncio.sleep(1)
            await self.pending_tasks.put(task)
            return False
        
        # Score and rank agents
        scored_agents = []
        for agent in capable_agents:
            score = self._score_agent_for_task(agent, task)
            scored_agents.append((score, agent))
        
        # Select best agent
        scored_agents.sort(reverse=True)
        best_agent = scored_agents[0][1]
        
        # Assign task
        accepted = await best_agent.assign_task(task)
        
        if accepted:
            self.task_assignments[task.id] = best_agent.id
            self.all_tasks[task.id] = task
            asyncio.create_task(self._track_task_completion(task))
            logger.info(
                "task_routed",
                task_id=task.id,
                agent_id=best_agent.id,
                score=scored_agents[0][0]
            )
        
        return accepted

    async def _track_task_completion(self, task: Task) -> None:
        """Track completion lifecycle for routed tasks."""
        while task.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            await asyncio.sleep(0.1)

        self.completed_tasks[task.id] = task
        self.task_assignments.pop(task.id, None)
    
    def _score_agent_for_task(self, agent: Agent, task: Task) -> float:
        """Score how well an agent matches a task."""
        scores = []
        
        # Capability match (40%)
        matching_caps = len(agent.capabilities & task.required_capabilities)
        total_caps = len(task.required_capabilities)
        scores.append((matching_caps / total_caps) * 0.4)
        
        # Current load (20%) - prefer less loaded agents
        load = len(agent.state.active_tasks) / agent.config.max_concurrent_tasks
        scores.append((1 - load) * 0.2)
        
        # Historical performance (30%)
        fitness = self.agent_fitness.get(agent.id)
        if fitness:
            scores.append(fitness.overall * 0.3)
        else:
            scores.append(0.15)  # Neutral for new agents
        
        # Response time (10%)
        if agent.state.last_heartbeat:
            seconds_since = (_utcnow() - agent.state.last_heartbeat).total_seconds()
            recency = max(0, 1 - seconds_since / 60)  # 1 minute window
            scores.append(recency * 0.1)
        else:
            scores.append(0.0)
        
        return sum(scores)
    
    def _select_diverse_agents(self, n: int, task: Task) -> List[Agent]:
        """Select a diverse set of agents for collective solving."""
        capable = [a for a in self.agents.values() if a.can_handle(task)]
        
        if len(capable) <= n:
            return capable
        
        # Maximize capability diversity
        selected = []
        remaining = set(a.id for a in capable)
        
        while len(selected) < n and remaining:
            # Score by how much new capability diversity is added
            best_score = -1
            best_agent = None
            
            for agent_id in remaining:
                agent = self.agents[agent_id]
                new_caps = agent.capabilities - set(
                    cap for s in selected for cap in s.capabilities
                )
                score = len(new_caps)
                
                if score > best_score:
                    best_score = score
                    best_agent = agent
            
            if best_agent:
                selected.append(best_agent)
                remaining.remove(best_agent.id)
            else:
                break
        
        return selected
    
    async def _await_solution(self, agent: Agent, task: Task) -> Solution:
        """Wait for an agent to complete a task and return solution."""
        while task.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            await asyncio.sleep(0.1)
        
        if task.status == TaskStatus.COMPLETED and task.result:
            if isinstance(task.result, Solution):
                return task.result
            else:
                return Solution(
                    task_id=task.id,
                    content=task.result,
                    confidence=0.7,
                    generated_by=agent.id
                )
        
        raise ValueError(f"Task failed: {task.result}")
    
    def _reach_consensus(self, solutions: List[Solution], threshold: float) -> Optional[Solution]:
        """Reach consensus among multiple solutions."""
        if not solutions:
            return None
        
        if len(solutions) == 1:
            return solutions[0]
        
        # Group similar solutions
        clusters = self._cluster_solutions(solutions)
        
        # Find largest cluster meeting threshold
        for cluster in sorted(clusters, key=len, reverse=True):
            agreement = len(cluster) / len(solutions)
            if agreement >= threshold:
                # Merge cluster into consensus
                return self._merge_solutions(cluster)
        
        # No consensus - return highest confidence
        return max(solutions, key=lambda s: s.confidence)
    
    def _cluster_solutions(self, solutions: List[Solution]) -> List[List[Solution]]:
        """Cluster solutions by similarity."""
        # Simplified: group by identical content
        clusters: Dict[str, List[Solution]] = {}
        
        for sol in solutions:
            key = str(sol.content)[:100]  # Simple content hash
            if key not in clusters:
                clusters[key] = []
            clusters[key].append(sol)
        
        return list(clusters.values())
    
    def _merge_solutions(self, solutions: List[Solution]) -> Solution:
        """Merge multiple solutions into consensus."""
        # Use solution with highest confidence as base
        best = max(solutions, key=lambda s: s.confidence)
        
        # Average confidence
        avg_confidence = sum(s.confidence for s in solutions) / len(solutions)
        
        return Solution(
            task_id=best.task_id,
            content=best.content,
            confidence=avg_confidence,
            generated_by=f"consensus({len(solutions)})",
            reasoning_trace=f"Consensus of {len(solutions)} agents"
        )
    
    async def _evolution_loop(self) -> None:
        """Periodically evolve the agent population."""
        while self._running:
            await asyncio.sleep(self.config.evolution_interval_seconds)
            
            if not self._running:
                break
            
            try:
                await self._evolve_population()
            except Exception as e:
                logger.error("evolution_error", error=str(e))
    
    async def _evolve_population(self) -> None:
        """Execute one generation of evolution."""
        logger.info("evolution_started", generation=self.generation)
        
        # Update fitness scores
        self._update_fitness_scores()
        
        # Selection: Keep top performers
        sorted_agents = sorted(
            self.agent_fitness.items(),
            key=lambda x: x[1].overall,
            reverse=True
        )
        
        n_keep = int(len(self.agents) * (1 - self.config.selection_pressure))
        keep_ids = {aid for aid, _ in sorted_agents[:n_keep]}
        
        # Remove poor performers
        to_remove = [aid for aid in self.agents if aid not in keep_ids]
        for aid in to_remove:
            if len(self.agents) > self.config.min_agents:
                agent = self.agents.pop(aid)
                agent.stop()
                del self.agent_fitness[aid]
                logger.info("agent_removed", agent_id=aid, reason="low_fitness")
        
        # Crossover and mutation: Create new agents
        n_new = self.config.target_agent_count - len(self.agents)
        for i in range(n_new):
            parents = random.sample(list(self.agents.values()), 2)
            child_config = self._crossover(parents[0].config, parents[1].config)
            child_config = self._mutate(child_config)
            
            child = Agent(child_config)
            self.agents[child.id] = child
            self.agent_fitness[child.id] = AgentFitness(agent_id=child.id)
            asyncio.create_task(child.start())
            
            logger.info("agent_created", agent_id=child.id, generation=self.generation)
        
        self.generation += 1
        self.last_evolution = _utcnow()
        
        logger.info(
            "evolution_completed",
            generation=self.generation,
            population=len(self.agents),
            removed=len(to_remove),
            created=n_new
        )
    
    def _update_fitness_scores(self) -> None:
        """Update fitness scores for all agents."""
        for agent_id, agent in self.agents.items():
            state = agent.state
            
            total_tasks = state.tasks_completed + state.tasks_failed
            if total_tasks == 0:
                continue
            
            fitness = AgentFitness(
                agent_id=agent_id,
                success_rate=state.tasks_completed / total_tasks,
                avg_quality=0.7,  # Would come from solution evaluation
                efficiency=state.tasks_completed / max(1, state.total_compute_time),
                diversity_contribution=0.5  # Would measure capability uniqueness
            )
            
            self.agent_fitness[agent_id] = fitness
    
    def _crossover(self, p1: AgentConfig, p2: AgentConfig) -> AgentConfig:
        """Create child configuration from two parents."""
        child = AgentConfig(
            name=f"Evolved-{self.generation}-{random.randint(1000, 9999)}",
            capabilities=p1.capabilities | p2.capabilities,
            temperature=(p1.temperature + p2.temperature) / 2,
            max_concurrent_tasks=random.choice([p1.max_concurrent_tasks, p2.max_concurrent_tasks]),
        )
        return child
    
    def _mutate(self, config: AgentConfig) -> AgentConfig:
        """Apply random mutations to configuration."""
        if random.random() < self.config.mutation_rate:
            # Mutate temperature
            config.temperature = max(0.0, min(1.0, config.temperature + random.gauss(0, 0.1)))
        
        if random.random() < self.config.mutation_rate:
            # Mutate capabilities
            all_caps = set(AgentCapability)
            if random.random() < 0.5 and config.capabilities:
                config.capabilities.remove(random.choice(list(config.capabilities)))
            else:
                config.capabilities.add(random.choice(list(all_caps - config.capabilities)))
        
        return config
    
    def get_status(self) -> Dict[str, Any]:
        """Get swarm status summary."""
        status = {
            "population": len(self.agents),
            "generation": self.generation,
            "pending_tasks": self.pending_tasks.qsize(),
            "active_tasks": len(self.task_assignments),
            "completed_tasks": len(self.completed_tasks),
            "agents": {
                aid: {
                    "name": a.name,
                    "status": a.state.status,
                    "active_tasks": len(a.state.active_tasks),
                    "fitness": self.agent_fitness.get(aid, AgentFitness(aid)).overall
                }
                for aid, a in self.agents.items()
            }
        }
        
        # Update metrics
        METRICS.update_swarm_generation(self.generation)
        METRICS.update_task_queue_size(self.pending_tasks.qsize())
        
        # Count agents by status
        status_counts = {}
        for agent in self.agents.values():
            s = agent.state.status
            status_counts[s] = status_counts.get(s, 0) + 1
        
        for s, count in status_counts.items():
            METRICS.update_agent_count(s, count)
        
        # Update per-agent metrics
        for aid, agent in self.agents.items():
            fitness = self.agent_fitness.get(aid, AgentFitness(aid))
            METRICS.update_agent_metrics(
                agent_id=aid,
                agent_name=agent.name,
                active_tasks=len(agent.state.active_tasks),
                fitness=fitness.overall
            )
        
        return status
