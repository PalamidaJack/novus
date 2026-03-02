"""
Streaming response support for NOVUS.

Implements Server-Sent Events (SSE) for real-time agent responses.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, Optional, Dict, Any, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
import structlog

logger = structlog.get_logger()


@dataclass
class StreamEvent:
    """Base class for streaming events."""
    event_type: str
    timestamp: float
    data: Dict[str, Any]
    
    def to_sse(self) -> str:
        """Convert to Server-Sent Event format."""
        return f"event: {self.event_type}\ndata: {json.dumps(self.data)}\n\n"


@dataclass  
class StreamChunk(StreamEvent):
    """A chunk of streamed content."""
    content: str
    agent_id: Optional[str] = None
    
    def __post_init__(self):
        if not self.event_type:
            self.event_type = "chunk"
        self.data = {
            "content": self.content,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp
        }


@dataclass
class StreamThought(StreamEvent):
    """Agent's reasoning/thought process."""
    thought: str
    agent_id: str
    
    def __post_init__(self):
        self.event_type = "thought"
        self.data = {
            "thought": self.thought,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp
        }


@dataclass
class StreamToolCall(StreamEvent):
    """Tool execution event."""
    tool_name: str
    arguments: Dict[str, Any]
    agent_id: str
    
    def __post_init__(self):
        self.event_type = "tool_call"
        self.data = {
            "tool": self.tool_name,
            "arguments": self.arguments,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp
        }


@dataclass
class StreamToolResult(StreamEvent):
    """Tool execution result."""
    tool_name: str
    result: Any
    agent_id: str
    
    def __post_init__(self):
        self.event_type = "tool_result"
        self.data = {
            "tool": self.tool_name,
            "result": str(self.result)[:1000],  # Limit size
            "agent_id": self.agent_id,
            "timestamp": self.timestamp
        }


@dataclass
class StreamComplete(StreamEvent):
    """Stream completion event."""
    final_answer: str
    metrics: Dict[str, Any]
    
    def __post_init__(self):
        self.event_type = "complete"
        self.data = {
            "answer": self.final_answer,
            "metrics": self.metrics,
            "timestamp": self.timestamp
        }


@dataclass
class StreamError(StreamEvent):
    """Error event."""
    error: str
    
    def __post_init__(self):
        self.event_type = "error"
        self.data = {
            "error": self.error,
            "timestamp": self.timestamp
        }


class StreamingAgent:
    """
    Agent with streaming response capabilities.
    
    Provides real-time visibility into:
    - Token generation
    - Thought process
    - Tool calls
    - Progress updates
    """
    
    def __init__(self, agent_id: str, name: str):
        self.agent_id = agent_id
        self.name = name
        self._observers: list[Callable[[StreamEvent], None]] = []
        
    def add_observer(self, callback: Callable[[StreamEvent], None]) -> None:
        """Add an observer for stream events."""
        self._observers.append(callback)
        
    def remove_observer(self, callback: Callable[[StreamEvent], None]) -> None:
        """Remove an observer."""
        self._observers.remove(callback)
        
    async def _emit(self, event: StreamEvent) -> None:
        """Emit event to all observers."""
        for observer in self._observers:
            try:
                if asyncio.iscoroutinefunction(observer):
                    await observer(event)
                else:
                    observer(event)
            except Exception as e:
                logger.error("observer_error", error=str(e))
    
    async def stream_think(
        self,
        prompt: str,
        stream_reasoning: bool = True
    ) -> AsyncIterator[StreamEvent]:
        """
        Process a prompt with streaming output.
        
        Yields:
            StreamEvent objects for real-time updates
        """
        start_time = datetime.utcnow().timestamp()
        
        try:
            # Emit thinking event
            thought_event = StreamThought(
                thought=f"Analyzing: {prompt[:100]}...",
                agent_id=self.agent_id,
                timestamp=start_time
            )
            await self._emit(thought_event)
            yield thought_event
            
            # Simulate streaming response (in production, this would come from LLM)
            words = [
                "I'll", "help", "you", "with", "that.", "Let", "me",
                "analyze", "the", "problem", "and", "provide", "a",
                "comprehensive", "solution.", "\n\n",
                "Based", "on", "my", "analysis,", "here", "are", "the",
                "key", "findings", "and", "recommendations..."
            ]
            
            accumulated = ""
            for word in words:
                await asyncio.sleep(0.05)  # Simulate generation speed
                accumulated += word + " "
                
                chunk = StreamChunk(
                    content=word + " ",
                    agent_id=self.agent_id,
                    timestamp=datetime.utcnow().timestamp()
                )
                await self._emit(chunk)
                yield chunk
            
            # Emit completion
            complete = StreamComplete(
                final_answer=accumulated.strip(),
                metrics={
                    "tokens_generated": len(words),
                    "time_seconds": datetime.utcnow().timestamp() - start_time,
                    "agent_name": self.name
                },
                timestamp=datetime.utcnow().timestamp()
            )
            await self._emit(complete)
            yield complete
            
        except Exception as e:
            error = StreamError(
                error=str(e),
                timestamp=datetime.utcnow().timestamp()
            )
            await self._emit(error)
            yield error
    
    async def stream_with_tools(
        self,
        prompt: str,
        tools: list[Dict[str, Any]]
    ) -> AsyncIterator[StreamEvent]:
        """
        Stream with tool execution visibility.
        """
        # Initial thought
        yield StreamThought(
            thought="I need to use tools to answer this",
            agent_id=self.agent_id,
            timestamp=datetime.utcnow().timestamp()
        )
        
        # Show tool selection
        for tool in tools:
            tool_call = StreamToolCall(
                tool_name=tool["name"],
                arguments=tool.get("arguments", {}),
                agent_id=self.agent_id,
                timestamp=datetime.utcnow().timestamp()
            )
            yield tool_call
            
            # Simulate execution
            await asyncio.sleep(0.5)
            
            tool_result = StreamToolResult(
                tool_name=tool["name"],
                result=f"Result from {tool['name']}",
                agent_id=self.agent_id,
                timestamp=datetime.utcnow().timestamp()
            )
            yield tool_result
        
        # Final response
        yield StreamComplete(
            final_answer="Based on the tool results...",
            metrics={"tools_used": len(tools)},
            timestamp=datetime.utcnow().timestamp()
        )


class StreamingSwarm:
    """
    Swarm with streaming capabilities for multi-agent collaboration.
    """
    
    def __init__(self):
        self.agents: Dict[str, StreamingAgent] = {}
        
    def add_agent(self, agent: StreamingAgent) -> None:
        """Add an agent to the swarm."""
        self.agents[agent.agent_id] = agent
        
    async def stream_collaborative_solve(
        self,
        problem: str,
        agent_ids: list[str]
    ) -> AsyncIterator[StreamEvent]:
        """
        Stream multi-agent collaborative problem solving.
        
        Shows inter-agent communication and consensus building.
        """
        yield StreamEvent(
            event_type="collaboration_start",
            timestamp=datetime.utcnow().timestamp(),
            data={
                "problem": problem,
                "agents": agent_ids,
                "message": f"Starting collaboration with {len(agent_ids)} agents"
            }
        )
        
        # Each agent contributes
        for agent_id in agent_ids:
            agent = self.agents.get(agent_id)
            if not agent:
                continue
                
            yield StreamEvent(
                event_type="agent_contribution",
                timestamp=datetime.utcnow().timestamp(),
                data={
                    "agent_id": agent_id,
                    "agent_name": agent.name,
                    "message": f"{agent.name} is analyzing..."
                }
            )
            
            # Stream agent's contribution
            async for event in agent.stream_think(problem):
                yield event
        
        # Consensus
        yield StreamEvent(
            event_type="consensus",
            timestamp=datetime.utcnow().timestamp(),
            data={
                "agents_reached_consensus": True,
                "confidence": 0.85
            }
        )
        
        yield StreamComplete(
            final_answer="Collaborative solution reached",
            metrics={"agents_participated": len(agent_ids)},
            timestamp=datetime.utcnow().timestamp()
        )


# FastAPI integration helper
async def stream_to_sse(
    event_iterator: AsyncIterator[StreamEvent]
) -> AsyncIterator[str]:
    """
    Convert stream events to SSE format for FastAPI.
    
    Usage:
        @app.get("/stream")
        async def stream():
            agent = StreamingAgent("1", "Assistant")
            return StreamingResponse(
                stream_to_sse(agent.stream_think("Hello")),
                media_type="text/event-stream"
            )
    """
    async for event in event_iterator:
        yield event.to_sse()
