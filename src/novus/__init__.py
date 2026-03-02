"""
NOVUS: Next-Generation Agentic AI Platform

A self-organizing, self-improving collective intelligence platform capable of
autonomous innovation, invention, and creative problem-solving.
"""

__version__ = "0.1.0"
__author__ = "NOVUS Team"

from novus.core.agent import Agent, AgentConfig
from novus.core.models import Task, TaskStatus
from novus.swarm.orchestrator import SwarmOrchestrator
from novus.memory.unified import UnifiedMemory
from novus.llm import LLMClient, get_llm_client
from novus.runtime import RecursiveAgentRuntime
from novus.benchmark import BenchmarkHarness

__all__ = [
    "Agent",
    "AgentConfig",
    "Task",
    "TaskStatus",
    "SwarmOrchestrator",
    "UnifiedMemory",
    "LLMClient",
    "get_llm_client",
    "RecursiveAgentRuntime",
    "BenchmarkHarness",
]
