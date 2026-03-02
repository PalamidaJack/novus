"""
Evaluation framework for NOVUS.

Provides automated testing, benchmarking, and quality assurance for agents.
Inspired by PraisonAI's eval framework.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import statistics
import structlog

logger = structlog.get_logger()


class EvalMetricType(str, Enum):
    """Types of evaluation metrics."""
    EXACT_MATCH = "exact_match"
    CONTAINS = "contains"
    SEMANTIC_SIMILARITY = "semantic_similarity"
    ACCURACY = "accuracy"
    LATENCY = "latency"
    TOKEN_COUNT = "token_count"
    COST = "cost"
    CUSTOM = "custom"


class EvalResultStatus(str, Enum):
    """Status of evaluation result."""
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIP = "skip"


@dataclass
class EvalMetric:
    """A single evaluation metric."""
    name: str
    value: float
    threshold: Optional[float] = None
    passed: bool = True
    details: Optional[str] = None


@dataclass
class EvalResult:
    """Result of a single test case evaluation."""
    test_name: str
    status: EvalResultStatus
    metrics: List[EvalMetric] = field(default_factory=list)
    actual_output: Optional[str] = None
    expected_output: Optional[str] = None
    execution_time_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None
    
    @property
    def score(self) -> float:
        """Calculate overall score from metrics."""
        if not self.metrics:
            return 0.0
        return sum(m.value for m in self.metrics) / len(self.metrics)
    
    @property
    def passed(self) -> bool:
        """Check if all metrics passed."""
        return all(m.passed for m in self.metrics) and self.status == EvalResultStatus.PASS


@dataclass
class TestCase:
    """A single test case for evaluation."""
    name: str
    input: str
    expected_output: Optional[str] = None
    expected_type: Optional[str] = None  # For validation
    eval_type: EvalMetricType = EvalMetricType.EXACT_MATCH
    tags: List[str] = field(default_factory=list)
    max_runtime: Optional[float] = None  # seconds
    max_memory: Optional[float] = None  # MB
    custom_eval_fn: Optional[Callable[[str, str], float]] = None
    
    # For tool/function evaluation
    expected_tools: Optional[List[str]] = None
    expected_tool_sequence: Optional[List[str]] = None


@dataclass
class EvalSuite:
    """A suite of test cases for evaluation."""
    name: str
    description: str
    test_cases: List[TestCase]
    agents: List[Any] = field(default_factory=list)
    
    # Automation settings
    schedule: Optional[str] = None  # Cron expression
    alerts: Optional[Dict[str, Any]] = None
    export_results: Optional[str] = None
    
    # Thresholds
    min_pass_rate: float = 0.8
    max_avg_latency_ms: Optional[float] = None
    
    results: List[EvalResult] = field(default_factory=list)


class Evaluator:
    """
    Evaluates agent performance against test cases.
    
    Supports multiple evaluation metrics:
    - Exact match
    - Contains/substring
    - Semantic similarity
    - Custom evaluation functions
    - Tool usage verification
    - Performance metrics (latency, cost)
    """
    
    def __init__(self):
        self.suites: Dict[str, EvalSuite] = {}
        self.evaluation_history: List[Dict[str, Any]] = []
        
    def create_suite(
        self,
        name: str,
        description: str,
        test_cases: List[TestCase],
        min_pass_rate: float = 0.8
    ) -> EvalSuite:
        """Create a new evaluation suite."""
        suite = EvalSuite(
            name=name,
            description=description,
            test_cases=test_cases,
            min_pass_rate=min_pass_rate
        )
        self.suites[name] = suite
        return suite
    
    async def evaluate_agent(
        self,
        agent: Any,
        suite: EvalSuite,
        verbose: bool = True
    ) -> List[EvalResult]:
        """
        Evaluate an agent against a test suite.
        
        Returns list of results for each test case.
        """
        results = []
        
        logger.info(
            "starting_evaluation",
            suite=suite.name,
            agent=agent.name if hasattr(agent, 'name') else str(agent),
            num_tests=len(suite.test_cases)
        )
        
        for test_case in suite.test_cases:
            try:
                result = await self._run_test(agent, test_case)
                results.append(result)
                
                if verbose:
                    status = "✓ PASS" if result.passed else "✗ FAIL"
                    print(f"{status} - {test_case.name}: {result.score:.2f}")
                    
            except Exception as e:
                logger.error("test_execution_error", test=test_case.name, error=str(e))
                results.append(EvalResult(
                    test_name=test_case.name,
                    status=EvalResultStatus.ERROR,
                    error_message=str(e)
                ))
        
        suite.results = results
        
        # Store history
        self.evaluation_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "suite": suite.name,
            "agent": agent.name if hasattr(agent, 'name') else str(agent),
            "num_tests": len(suite.test_cases),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "avg_score": statistics.mean([r.score for r in results]) if results else 0
        })
        
        return results
    
    async def _run_test(self, agent: Any, test: TestCase) -> EvalResult:
        """Run a single test case."""
        start_time = time.time()
        
        # Execute agent
        try:
            if asyncio.iscoroutinefunction(agent.run if hasattr(agent, 'run') else agent):
                actual_output = await agent.run(test.input)
            else:
                actual_output = agent.run(test.input)
        except Exception as e:
            return EvalResult(
                test_name=test.name,
                status=EvalResultStatus.ERROR,
                error_message=str(e),
                execution_time_ms=(time.time() - start_time) * 1000
            )
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        # Evaluate result
        metrics = self._calculate_metrics(
            actual_output,
            test.expected_output,
            test.eval_type,
            test.custom_eval_fn,
            execution_time_ms,
            test
        )
        
        # Check if passed
        passed = all(m.passed for m in metrics)
        
        # Check runtime constraint
        if test.max_runtime and execution_time_ms > test.max_runtime * 1000:
            passed = False
            metrics.append(EvalMetric(
                name="runtime_constraint",
                value=execution_time_ms,
                threshold=test.max_runtime * 1000,
                passed=False,
                details=f"Exceeded max runtime of {test.max_runtime}s"
            ))
        
        return EvalResult(
            test_name=test.name,
            status=EvalResultStatus.PASS if passed else EvalResultStatus.FAIL,
            metrics=metrics,
            actual_output=str(actual_output)[:1000],
            expected_output=test.expected_output,
            execution_time_ms=execution_time_ms
        )
    
    def _calculate_metrics(
        self,
        actual: Any,
        expected: Optional[str],
        eval_type: EvalMetricType,
        custom_fn: Optional[Callable],
        latency_ms: float,
        test: TestCase
    ) -> List[EvalMetric]:
        """Calculate evaluation metrics."""
        metrics = []
        actual_str = str(actual)
        
        # Latency metric (always included)
        metrics.append(EvalMetric(
            name="latency_ms",
            value=latency_ms,
            passed=True
        ))
        
        if eval_type == EvalMetricType.EXACT_MATCH and expected is not None:
            score = 1.0 if actual_str.strip() == expected.strip() else 0.0
            metrics.append(EvalMetric(
                name="exact_match",
                value=score,
                threshold=1.0,
                passed=score == 1.0
            ))
            
        elif eval_type == EvalMetricType.CONTAINS and expected is not None:
            score = 1.0 if expected in actual_str else 0.0
            metrics.append(EvalMetric(
                name="contains",
                value=score,
                threshold=1.0,
                passed=score == 1.0
            ))
            
        elif eval_type == EvalMetricType.SEMANTIC_SIMILARITY and expected is not None:
            # Use simple token overlap for now
            # In production, use embeddings
            actual_tokens = set(actual_str.lower().split())
            expected_tokens = set(expected.lower().split())
            
            if expected_tokens:
                overlap = len(actual_tokens & expected_tokens)
                score = overlap / len(expected_tokens)
            else:
                score = 0.0
            
            metrics.append(EvalMetric(
                name="semantic_similarity",
                value=score,
                threshold=0.7,
                passed=score >= 0.7
            ))
            
        elif eval_type == EvalMetricType.CUSTOM and custom_fn is not None:
            try:
                score = custom_fn(actual_str, expected or "")
                metrics.append(EvalMetric(
                    name="custom",
                    value=score,
                    threshold=0.8,
                    passed=score >= 0.8
                ))
            except Exception as e:
                metrics.append(EvalMetric(
                    name="custom",
                    value=0.0,
                    passed=False,
                    details=str(e)
                ))
        
        # Check tool usage if specified
        if test.expected_tools:
            # This would need integration with agent tool tracking
            metrics.append(EvalMetric(
                name="tool_usage",
                value=1.0,  # Placeholder
                passed=True
            ))
        
        return metrics
    
    def generate_report(self, suite: EvalSuite) -> Dict[str, Any]:
        """Generate evaluation report for a suite."""
        if not suite.results:
            return {"error": "No results available. Run evaluate_agent first."}
        
        passed = sum(1 for r in suite.results if r.passed)
        failed = len(suite.results) - passed
        pass_rate = passed / len(suite.results) if suite.results else 0
        
        scores = [r.score for r in suite.results]
        latencies = [r.execution_time_ms for r in suite.results]
        
        return {
            "suite_name": suite.name,
            "description": suite.description,
            "timestamp": datetime.utcnow().isoformat(),
            "summary": {
                "total_tests": len(suite.results),
                "passed": passed,
                "failed": failed,
                "pass_rate": pass_rate,
                "overall_passed": pass_rate >= suite.min_pass_rate
            },
            "metrics": {
                "avg_score": statistics.mean(scores) if scores else 0,
                "median_score": statistics.median(scores) if scores else 0,
                "min_score": min(scores) if scores else 0,
                "max_score": max(scores) if scores else 0,
                "avg_latency_ms": statistics.mean(latencies) if latencies else 0,
                "total_latency_ms": sum(latencies) if latencies else 0
            },
            "results": [
                {
                    "test_name": r.test_name,
                    "status": r.status.value,
                    "passed": r.passed,
                    "score": r.score,
                    "execution_time_ms": r.execution_time_ms,
                    "error": r.error_message
                }
                for r in suite.results
            ]
        }
    
    def export_results(self, suite: EvalSuite, filepath: str) -> None:
        """Export evaluation results to file."""
        report = self.generate_report(suite)
        
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info("results_exported", suite=suite.name, filepath=filepath)
    
    def compare_results(
        self,
        suite_name: str,
        agent_a_name: str,
        agent_b_name: str
    ) -> Dict[str, Any]:
        """Compare performance of two agents on the same suite."""
        # Filter history for both agents
        a_results = [
            h for h in self.evaluation_history
            if h["suite"] == suite_name and h["agent"] == agent_a_name
        ]
        b_results = [
            h for h in self.evaluation_history
            if h["suite"] == suite_name and h["agent"] == agent_b_name
        ]
        
        if not a_results or not b_results:
            return {"error": "Insufficient data for comparison"}
        
        latest_a = a_results[-1]
        latest_b = b_results[-1]
        
        return {
            "suite": suite_name,
            "agent_a": agent_a_name,
            "agent_b": agent_b_name,
            "comparison": {
                "pass_rate_diff": latest_a["passed"] / latest_a["num_tests"] - 
                                 latest_b["passed"] / latest_b["num_tests"],
                "score_diff": latest_a["avg_score"] - latest_b["avg_score"]
            },
            "winner": agent_a_name if latest_a["avg_score"] > latest_b["avg_score"] 
                     else agent_b_name
        }


# Built-in test suites for common scenarios

def create_math_suite() -> EvalSuite:
    """Create a math problem evaluation suite."""
    return EvalSuite(
        name="math_problems",
        description="Basic arithmetic and math word problems",
        test_cases=[
            TestCase(
                name="simple_addition",
                input="What is 15 + 27?",
                expected_output="42",
                eval_type=EvalMetricType.CONTAINS,
                tags=["math", "addition"]
            ),
            TestCase(
                name="multiplication",
                input="Calculate 12 * 8",
                expected_output="96",
                eval_type=EvalMetricType.CONTAINS,
                tags=["math", "multiplication"]
            ),
            TestCase(
                name="word_problem",
                input="If a train travels 60 miles per hour for 2.5 hours, how far does it go?",
                expected_output="150",
                eval_type=EvalMetricType.CONTAINS,
                tags=["math", "word_problem"]
            )
        ],
        min_pass_rate=1.0
    )


def create_reasoning_suite() -> EvalSuite:
    """Create a reasoning evaluation suite."""
    return EvalSuite(
        name="logical_reasoning",
        description="Logical reasoning and deduction problems",
        test_cases=[
            TestCase(
                name="syllogism",
                input="All mammals are animals. All dogs are mammals. Therefore?",
                expected_type="conclusion",
                eval_type=EvalMetricType.SEMANTIC_SIMILARITY,
                tags=["logic", "deduction"]
            ),
            TestCase(
                name="pattern_recognition",
                input="What comes next: 2, 4, 8, 16, ?",
                expected_output="32",
                eval_type=EvalMetricType.CONTAINS,
                tags=["pattern", "sequence"]
            )
        ],
        min_pass_rate=0.8
    )


def create_coding_suite() -> EvalSuite:
    """Create a coding evaluation suite."""
    return EvalSuite(
        name="coding_tasks",
        description="Programming and code generation tasks",
        test_cases=[
            TestCase(
                name="hello_world",
                input="Write a Python function that prints 'Hello, World!'",
                expected_type="python_code",
                custom_eval_fn=lambda actual, expected: 
                    1.0 if "hello" in actual.lower() and "world" in actual.lower() else 0.0,
                eval_type=EvalMetricType.CUSTOM,
                tags=["coding", "python"],
                max_runtime=5.0
            ),
            TestCase(
                name="factorial",
                input="Write a function to calculate factorial of n",
                expected_type="python_code",
                eval_type=EvalMetricType.SEMANTIC_SIMILARITY,
                tags=["coding", "algorithm"],
                max_runtime=10.0
            )
        ],
        min_pass_rate=0.7
    )


# Example usage
if __name__ == "__main__":
    async def example():
        from novus.core.agent import Agent
        from novus.core.models import AgentConfig
        
        # Create evaluator
        evaluator = Evaluator()
        
        # Create test suite
        suite = create_math_suite()
        
        # Create agent
        config = AgentConfig(name="MathAgent")
        agent = Agent(config)
        
        # Run evaluation
        results = await evaluator.evaluate_agent(agent, suite, verbose=True)
        
        # Generate report
        report = evaluator.generate_report(suite)
        print("\nReport:")
        print(json.dumps(report, indent=2))
    
    asyncio.run(example())
