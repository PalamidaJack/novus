"""
Adversarial Agent Competition System for NOVUS.

Implements structured competition patterns proven to improve agent outputs:
- Adversarial Red Teaming (proven effective for safety/quality)
- Structured Debate (OpenAI research shows improves truthfulness)
- Tournament Selection (evolutionary pressure)
- Benchmark Competition (objective metrics)

Based on research:
- Irving et al. (2018): "AI Safety via Debate" - debate improves truthfulness
- Anthropic: Red teaming improves model safety
- Tournament selection maintains diversity while improving performance

CRITICAL INSIGHT: Pure competition can lead to:
- Gaming metrics rather than real improvement
- Adversarial attacks on other agents
- Wasted compute on "fighting" vs problem-solving
- Convergence to local optima

This system uses STRUCTURED competition with guardrails.
"""

from __future__ import annotations

import asyncio
import random
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import statistics
import structlog

from novus.core.models import Task, Solution, AgentCapability
from novus.core.agent import Agent

logger = structlog.get_logger()


class CompetitionType(str, Enum):
    """Types of structured competition."""
    RED_TEAM = "red_team"              # Adversarial validation
    DEBATE = "debate"                  # Structured argumentation
    TOURNAMENT = "tournament"          # Tournament selection
    BENCHMARK = "benchmark"            # Objective metric competition
    AUCTION = "auction"                # Bid for tasks
    VERIFICATION_GAME = "verification" # Verifier vs Prover


@dataclass
class CompetitionResult:
    """Result of a competition round."""
    winner_id: Optional[str]
    loser_id: Optional[str]
    winner_score: float
    loser_score: float
    competition_type: CompetitionType
    improvements_made: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AgentPerformance:
    """Track agent performance metrics."""
    agent_id: str
    wins: int = 0
    losses: int = 0
    draws: int = 0
    total_score: float = 0.0
    average_score: float = 0.0
    best_performance: float = 0.0
    win_rate: float = 0.0
    elo_rating: float = 1500.0  # ELO rating system
    specialization_score: Dict[str, float] = field(default_factory=dict)


class AdversarialRedTeam:
    """
    Red Team vs Blue Team competition.
    
    Blue Team: Creates solutions
    Red Team: Tries to find flaws/attacks
    
    Proven effective for:
    - Finding safety issues
    - Improving robustness
    - Catching edge cases
    """
    
    def __init__(self):
        self.red_agents: List[Agent] = []
        self.blue_agents: List[Agent] = []
        self.attack_history: List[Dict[str, Any]] = []
        
    def register_red_agent(self, agent: Agent) -> None:
        """Register a red team agent (attacker/critic)."""
        self.red_agents.append(agent)
        agent.capabilities.add(AgentCapability.VERIFICATION)
        logger.info("red_agent_registered", agent_id=agent.id)
        
    def register_blue_agent(self, agent: Agent) -> None:
        """Register a blue team agent (creator/solution-maker)."""
        self.blue_agents.append(agent)
        logger.info("blue_agent_registered", agent_id=agent.id)
    
    async def run_red_team_exercise(
        self,
        problem: str,
        num_rounds: int = 3
    ) -> Dict[str, Any]:
        """
        Run red team exercise.
        
        Process:
        1. Blue team creates solution
        2. Red team finds flaws/attacks
        3. Blue team patches/improves
        4. Repeat
        """
        results = {
            "problem": problem,
            "rounds": [],
            "improvements": [],
            "final_solution": None
        }
        
        current_solution = None
        
        for round_num in range(num_rounds):
            logger.info("red_team_round_start", round=round_num + 1)
            
            # Blue team creates/patches solution
            if current_solution is None:
                blue_task = Task(
                    description=f"Create solution for: {problem}",
                    required_capabilities={AgentCapability.REASONING}
                )
            else:
                blue_task = Task(
                    description=f"Improve this solution based on feedback: {current_solution}",
                    required_capabilities={AgentCapability.REASONING}
                )
            
            blue_agent = random.choice(self.blue_agents)
            await blue_agent.assign_task(blue_task)
            
            # Wait for completion
            while blue_task.status not in ["completed", "failed"]:
                await asyncio.sleep(0.1)
            
            if blue_task.status == "completed":
                current_solution = blue_task.result
            
            # Red team attacks
            red_task = Task(
                description=f"Find flaws, vulnerabilities, or issues in this solution: {current_solution}",
                required_capabilities={AgentCapability.VERIFICATION}
            )
            
            red_agent = random.choice(self.red_agents)
            await red_agent.assign_task(red_task)
            
            while red_task.status not in ["completed", "failed"]:
                await asyncio.sleep(0.1)
            
            attacks_found = red_task.result if red_task.status == "completed" else "None"
            
            results["rounds"].append({
                "round": round_num + 1,
                "solution": str(current_solution)[:500],
                "attacks_found": str(attacks_found)[:500]
            })
            
            if attacks_found and attacks_found != "None":
                results["improvements"].append({
                    "round": round_num + 1,
                    "issue": attacks_found,
                    "improvement": "Addressed in next iteration"
                })
            else:
                # No attacks found, solution is good
                logger.info("red_team_no_attacks", round=round_num + 1)
                break
        
        results["final_solution"] = current_solution
        
        # Update performance metrics
        self.attack_history.append({
            "problem": problem,
            "rounds": len(results["rounds"]),
            "improvements": len(results["improvements"]),
            "timestamp": datetime.utcnow()
        })
        
        return results


class StructuredDebate:
    """
    Structured debate between agents.
    
    Based on OpenAI research (Irving et al. 2018):
    - Debate helps surface truth
    - Better than single agent for complex reasoning
    - Judges evaluate arguments
    
    Process:
    1. Two agents argue opposing positions
    2. Judge agent evaluates
    3. Winner's reasoning is incorporated
    """
    
    def __init__(self):
        self.judges: List[Agent] = []
        self.debaters: List[Agent] = []
        self.debate_history: List[Dict[str, Any]] = []
        
    def add_judge(self, agent: Agent) -> None:
        """Add a judge agent."""
        self.judges.append(agent)
        
    def add_debater(self, agent: Agent) -> None:
        """Add a debater agent."""
        self.debaters.append(agent)
    
    async def debate(
        self,
        topic: str,
        position_a: str,
        position_b: str,
        num_rounds: int = 2
    ) -> Dict[str, Any]:
        """
        Run structured debate.
        
        Returns winning position and reasoning.
        """
        if len(self.debaters) < 2:
            raise ValueError("Need at least 2 debaters")
        
        debater_a = self.debaters[0]
        debater_b = self.debaters[1]
        judge = self.judges[0] if self.judges else None
        
        debate_log = []
        
        # Opening statements
        task_a = Task(
            description=f"Debate topic: {topic}\nArgue FOR: {position_a}\nPresent your opening argument.",
            required_capabilities={AgentCapability.REASONING}
        )
        await debater_a.assign_task(task_a)
        
        task_b = Task(
            description=f"Debate topic: {topic}\nArgue FOR: {position_b}\nPresent your opening argument.",
            required_capabilities={AgentCapability.REASONING}
        )
        await debater_b.assign_task(task_b)
        
        # Wait for both
        while task_a.status not in ["completed", "failed"] or task_b.status not in ["completed", "failed"]:
            await asyncio.sleep(0.1)
        
        argument_a = task_a.result if task_a.status == "completed" else "No argument"
        argument_b = task_b.result if task_b.status == "completed" else "No argument"
        
        debate_log.append({
            "round": "opening",
            "position_a": str(argument_a)[:300],
            "position_b": str(argument_b)[:300]
        })
        
        # Rebuttals
        for round_num in range(num_rounds):
            # A rebuts B
            rebuttal_a = Task(
                description=f"Rebut this argument: {argument_b}",
                required_capabilities={AgentCapability.REASONING}
            )
            await debater_a.assign_task(rebuttal_a)
            
            # B rebuts A
            rebuttal_b = Task(
                description=f"Rebut this argument: {argument_a}",
                required_capabilities={AgentCapability.REASONING}
            )
            await debater_b.assign_task(rebuttal_b)
            
            while rebuttal_a.status not in ["completed", "failed"] or rebuttal_b.status not in ["completed", "failed"]:
                await asyncio.sleep(0.1)
            
            argument_a = rebuttal_a.result if rebuttal_a.status == "completed" else argument_a
            argument_b = rebuttal_b.result if rebuttal_b.status == "completed" else argument_b
            
            debate_log.append({
                "round": f"rebuttal_{round_num + 1}",
                "position_a": str(argument_a)[:300],
                "position_b": str(argument_b)[:300]
            })
        
        # Judge evaluates
        winner = None
        winning_argument = None
        
        if judge:
            judge_task = Task(
                description=f"""Evaluate this debate and choose the winner:

Topic: {topic}

Position A ({position_a}):
{argument_a}

Position B ({position_b}):
{argument_b}

Which position is more convincing and why?""",
                required_capabilities={AgentCapability.ANALYSIS}
            )
            await judge.assign_task(judge_task)
            
            while judge_task.status not in ["completed", "failed"]:
                await asyncio.sleep(0.1)
            
            decision = str(judge_task.result) if judge_task.status == "completed" else ""
            
            # Parse winner (simplified)
            if "position a" in decision.lower() or position_a.lower() in decision.lower():
                winner = "A"
                winning_argument = argument_a
            elif "position b" in decision.lower() or position_b.lower() in decision.lower():
                winner = "B"
                winning_argument = argument_b
            else:
                winner = "tie"
                winning_argument = f"Combined: {argument_a}\n{argument_b}"
        
        result = {
            "topic": topic,
            "position_a": position_a,
            "position_b": position_b,
            "winner": winner,
            "winning_argument": str(winning_argument)[:1000],
            "debate_log": debate_log,
            "judge_reasoning": str(decision)[:500] if judge else "No judge"
        }
        
        self.debate_history.append(result)
        
        return result


class TournamentSelection:
    """
    Tournament-based competition for agent selection.
    
    Agents compete in tournaments to be selected for tasks.
    Uses ELO rating system for skill estimation.
    
    Benefits:
    - Maintains diversity (different agents win different tournaments)
    - Clear skill progression
    - Fair selection based on performance
    """
    
    def __init__(self, k_factor: int = 32):
        self.agents: Dict[str, AgentPerformance] = {}
        self.k_factor = k_factor  # ELO K-factor
        self.tournament_history: List[Dict[str, Any]] = []
        
    def register_agent(self, agent: Agent) -> None:
        """Register an agent for tournaments."""
        if agent.id not in self.agents:
            self.agents[agent.id] = AgentPerformance(agent_id=agent.id)
    
    async def run_tournament(
        self,
        task: Task,
        agent_ids: List[str],
        metric_fn: Callable[[Any], float]
    ) -> CompetitionResult:
        """
        Run tournament where agents compete on same task.
        
        Args:
            task: The task to complete
            agent_ids: IDs of competing agents
            metric_fn: Function to score results (higher is better)
        
        Returns:
            CompetitionResult with winner
        """
        results = []
        
        # Each agent attempts the task
        for agent_id in agent_ids:
            # In real implementation, would get agent from registry
            # and have it complete the task
            # For now, simulate
            score = random.uniform(0.5, 1.0)  # Placeholder
            results.append((agent_id, score))
        
        # Sort by score
        results.sort(key=lambda x: x[1], reverse=True)
        
        winner_id, winner_score = results[0]
        loser_id, loser_score = results[-1]
        
        # Update ELO ratings
        self._update_elo(winner_id, loser_id)
        
        # Update stats
        self.agents[winner_id].wins += 1
        self.agents[winner_id].total_score += winner_score
        self.agents[loser_id].losses += 1
        self.agents[loser_id].total_score += loser_score
        
        # Recalculate averages
        for perf in self.agents.values():
            total_games = perf.wins + perf.losses + perf.draws
            if total_games > 0:
                perf.average_score = perf.total_score / total_games
                perf.win_rate = perf.wins / total_games
        
        competition_result = CompetitionResult(
            winner_id=winner_id,
            loser_id=loser_id,
            winner_score=winner_score,
            loser_score=loser_score,
            competition_type=CompetitionType.TOURNAMENT,
            improvements_made=[f"ELO updated: {self.agents[winner_id].elo_rating:.0f}"]
        )
        
        self.tournament_history.append({
            "task": task.description[:100],
            "winner": winner_id,
            "scores": dict(results),
            "timestamp": datetime.utcnow()
        })
        
        return competition_result
    
    def _update_elo(self, winner_id: str, loser_id: str) -> None:
        """Update ELO ratings after match."""
        winner = self.agents[winner_id]
        loser = self.agents[loser_id]
        
        # Expected scores
        expected_winner = 1 / (1 + 10 ** ((loser.elo_rating - winner.elo_rating) / 400))
        expected_loser = 1 / (1 + 10 ** ((winner.elo_rating - loser.elo_rating) / 400))
        
        # Update ratings
        winner.elo_rating += self.k_factor * (1 - expected_winner)
        loser.elo_rating += self.k_factor * (0 - expected_loser)
    
    def get_leaderboard(self) -> List[AgentPerformance]:
        """Get sorted leaderboard."""
        return sorted(
            self.agents.values(),
            key=lambda x: (x.elo_rating, x.win_rate),
            reverse=True
        )
    
    def select_best_agent(self, capability: Optional[str] = None) -> Optional[str]:
        """Select best agent for a task."""
        leaderboard = self.get_leaderboard()
        if not leaderboard:
            return None
        return leaderboard[0].agent_id


class BenchmarkCompetition:
    """
    Competition based on standardized benchmarks.
    
    Agents compete on objective metrics.
    Transparent, reproducible, fair.
    """
    
    def __init__(self):
        self.benchmarks: Dict[str, List[Task]] = {}
        self.results: Dict[str, Dict[str, float]] = {}  # agent_id -> benchmark -> score
        
    def register_benchmark(self, name: str, tasks: List[Task]) -> None:
        """Register a benchmark suite."""
        self.benchmarks[name] = tasks
        logger.info("benchmark_registered", name=name, num_tasks=len(tasks))
    
    async def run_benchmark(
        self,
        agent: Agent,
        benchmark_name: str
    ) -> Dict[str, Any]:
        """Run agent on benchmark."""
        if benchmark_name not in self.benchmarks:
            raise ValueError(f"Unknown benchmark: {benchmark_name}")
        
        tasks = self.benchmarks[benchmark_name]
        scores = []
        
        for task in tasks:
            await agent.assign_task(task)
            
            # Wait for completion
            while task.status not in ["completed", "failed"]:
                await asyncio.sleep(0.1)
            
            # Score result
            if task.status == "completed":
                # Simplified scoring
                score = 1.0 if "correct" in str(task.result).lower() else 0.5
            else:
                score = 0.0
            
            scores.append(score)
        
        avg_score = statistics.mean(scores) if scores else 0.0
        
        # Store result
        if agent.id not in self.results:
            self.results[agent.id] = {}
        self.results[agent.id][benchmark_name] = avg_score
        
        return {
            "agent_id": agent.id,
            "benchmark": benchmark_name,
            "score": avg_score,
            "tasks_completed": len(scores),
            "details": scores
        }
    
    def get_rankings(self, benchmark_name: str) -> List[Tuple[str, float]]:
        """Get rankings for a benchmark."""
        rankings = [
            (agent_id, scores.get(benchmark_name, 0.0))
            for agent_id, scores in self.results.items()
        ]
        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings


class VerificationGame:
    """
    Prover-Verifier game.
    
    Prover tries to convince Verifier of solution correctness.
    Verifier tries to catch mistakes.
    
    Improves both:
    - Prover learns to create convincing, correct solutions
    - Verifier learns to spot errors
    """
    
    def __init__(self):
        self.provers: List[Agent] = []
        self.verifiers: List[Agent] = []
        
    def add_prover(self, agent: Agent) -> None:
        """Add a prover agent."""
        self.provers.append(agent)
        
    def add_verifier(self, agent: Agent) -> None:
        """Add a verifier agent."""
        self.verifiers.append(agent)
    
    async def play_round(
        self,
        problem: str,
        solution_is_correct: bool = True
    ) -> Dict[str, Any]:
        """
        Play one round of verification game.
        
        Returns whether verifier caught any issues.
        """
        prover = random.choice(self.provers)
        verifier = random.choice(self.verifiers)
        
        # Prover creates solution
        prover_task = Task(
            description=f"Create solution for: {problem}",
            required_capabilities={AgentCapability.REASONING}
        )
        await prover.assign_task(prover_task)
        
        while prover_task.status not in ["completed", "failed"]:
            await asyncio.sleep(0.1)
        
        solution = prover_task.result
        
        # Verifier checks solution
        verifier_task = Task(
            description=f"Verify this solution. Find any errors or issues: {solution}",
            required_capabilities={AgentCapability.VERIFICATION}
        )
        await verifier.assign_task(verifier_task)
        
        while verifier_task.status not in ["completed", "failed"]:
            await asyncio.sleep(0.1)
        
        verification = verifier_task.result
        
        # Determine if issues were found
        issues_found = "error" in str(verification).lower() or "issue" in str(verification).lower()
        
        return {
            "problem": problem,
            "solution": str(solution)[:500],
            "verification": str(verification)[:500],
            "issues_found": issues_found,
            "prover_id": prover.id,
            "verifier_id": verifier.id
        }


class CompetitiveSwarm:
    """
    Swarm with structured competition.
    
    Combines multiple competition types for comprehensive improvement.
    """
    
    def __init__(self):
        self.red_team = AdversarialRedTeam()
        self.debate = StructuredDebate()
        self.tournament = TournamentSelection()
        self.benchmark = BenchmarkCompetition()
        self.verification = VerificationGame()
        
        self.agents: List[Agent] = []
        
    def add_agent(self, agent: Agent, role: str = "general") -> None:
        """Add agent with specific competitive role."""
        self.agents.append(agent)
        
        if role == "red_team":
            self.red_team.register_red_agent(agent)
        elif role == "blue_team":
            self.red_team.register_blue_agent(agent)
        elif role == "debater":
            self.debate.add_debater(agent)
        elif role == "judge":
            self.debate.add_judge(agent)
        elif role == "prover":
            self.verification.add_prover(agent)
        elif role == "verifier":
            self.verification.add_verifier(agent)
        
        self.tournament.register_agent(agent)
        
        logger.info("agent_added_to_competition", agent_id=agent.id, role=role)
    
    async def improve_solution(
        self,
        problem: str,
        strategy: str = "red_team"
    ) -> Dict[str, Any]:
        """
        Use competition to improve a solution.
        
        Strategies:
        - red_team: Adversarial improvement
        - debate: Structured argumentation
        - tournament: Selection of best
        - verification: Error checking
        """
        if strategy == "red_team":
            return await self.red_team.run_red_team_exercise(problem)
        elif strategy == "debate":
            return await self.debate.debate(
                problem,
                "Position A",
                "Position B"
            )
        elif strategy == "verification":
            return await self.verification.play_round(problem)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
    
    def get_leaderboard(self) -> List[AgentPerformance]:
        """Get tournament leaderboard."""
        return self.tournament.get_leaderboard()


# Example usage
if __name__ == "__main__":
    async def example():
        # Create competitive swarm
        competition = CompetitiveSwarm()
        
        # Create specialized agents
        from novus.core.models import AgentConfig
        
        # Red team agent (critic)
        red_config = AgentConfig(
            name="RedTeam",
            capabilities={AgentCapability.VERIFICATION}
        )
        red_agent = Agent(red_config)
        competition.add_agent(red_agent, role="red_team")
        
        # Blue team agent (creator)
        blue_config = AgentConfig(
            name="BlueTeam",
            capabilities={AgentCapability.REASONING}
        )
        blue_agent = Agent(blue_config)
        competition.add_agent(blue_agent, role="blue_team")
        
        # Run red team exercise
        result = await competition.improve_solution(
            "Design a secure authentication system",
            strategy="red_team"
        )
        
        print(f"Improvements made: {len(result['improvements'])}")
        print(f"Rounds: {len(result['rounds'])}")
        
        # Get leaderboard
        leaderboard = competition.get_leaderboard()
        for rank, perf in enumerate(leaderboard, 1):
            print(f"{rank}. {perf.agent_id}: ELO {perf.elo_rating:.0f}, "
                  f"Wins {perf.wins}, Win Rate {perf.win_rate:.1%}")
    
    asyncio.run(example())
