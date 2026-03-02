"""
Agent composition - Agent as Tool pattern.

Allows agents to be used as tools by other agents.
Inspired by OpenAI Agents SDK.
"""

from __future__ import annotations

import asyncio
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
import structlog

from novus.core.models import Task, AgentCapability

logger = structlog.get_logger()


@dataclass
class AgentTool:
    """
    Wraps an agent as a callable tool.
    
    Enables agent composition - one agent can use another as a tool.
    """
    agent_id: str
    agent_name: str
    description: str
    input_schema: Dict[str, Any]
    _agent: Any = None
    
    def __init__(self, agent: Any, description: str = "", input_schema: Optional[Dict[str, Any]] = None):
        self._agent = agent
        self.agent_id = agent.id
        self.agent_name = agent.name
        self.description = description or f"Agent: {agent.name}"
        self.input_schema = input_schema or {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Query for the agent"}
            },
            "required": ["query"]
        }
    
    async def execute(self, **kwargs) -> Any:
        """Execute the agent as a tool."""
        query = kwargs.get("query", kwargs.get("input", str(kwargs)))
        
        # Create a task for the agent
        task = Task(
            description=query,
            required_capabilities={AgentCapability.REASONING}
        )
        
        # Submit and wait for result
        await self._agent.assign_task(task)
        
        # Wait for completion
        while task.status not in ["completed", "failed"]:
            await asyncio.sleep(0.1)
        
        if task.status == "completed":
            return task.result
        else:
            return {"error": task.result.get("error", "Unknown error")}
    
    def to_schema(self) -> Dict[str, Any]:
        """Convert to tool schema."""
        return {
            "name": self.agent_id,
            "description": self.description,
            "parameters": self.input_schema
        }


class AgentComposition:
    """
    Manages agent composition and tool creation.
    
    Allows:
    - Agents using other agents as tools
    - Hierarchical agent structures
    - Tool marketplaces
    """
    
    def __init__(self):
        self._agents: Dict[str, Any] = {}
        self._tools: Dict[str, AgentTool] = {}
        self._compositions: Dict[str, List[AgentTool]] = {}
        
    def register_agent(self, agent: Any) -> None:
        """Register an agent for composition."""
        self._agents[agent.id] = agent
        logger.info("agent_registered_for_composition", agent_id=agent.id)
    
    def create_tool_from_agent(
        self,
        agent_id: str,
        description: str = "",
        input_schema: Optional[Dict[str, Any]] = None
    ) -> Optional[AgentTool]:
        """Create a tool from an existing agent."""
        agent = self._agents.get(agent_id)
        if not agent:
            logger.warning("agent_not_found", agent_id=agent_id)
            return None
        
        tool = AgentTool(agent, description, input_schema)
        self._tools[agent_id] = tool
        
        logger.info("agent_as_tool_created", agent_id=agent_id)
        return tool
    
    def get_tool(self, tool_name: str) -> Optional[AgentTool]:
        """Get a tool by name."""
        return self._tools.get(tool_name)
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools."""
        return [tool.to_schema() for tool in self._tools.values()]
    
    def compose_agents(
        self,
        composer_agent_id: str,
        tool_agent_ids: List[str]
    ) -> List[AgentTool]:
        """Compose multiple agents as tools for a parent agent."""
        tools = []
        
        for agent_id in tool_agent_ids:
            tool = self.create_tool_from_agent(agent_id)
            if tool:
                tools.append(tool)
        
        self._compositions[composer_agent_id] = tools
        
        logger.info("agent_composed", composer=composer_agent_id, tools=len(tools))
        return tools
    
    async def execute_tool(
        self,
        tool_name: str,
        **kwargs
    ) -> Any:
        """Execute a tool by name."""
        tool = self._tools.get(tool_name)
        if not tool:
            raise ValueError(f"Tool not found: {tool_name}")
        
        return await tool.execute(**kwargs)


# Example usage showing hierarchical agents
"""
Example: Research Team with specialized agents

                        ┌─────────────────┐
                        │   CEO Agent     │
                        │  (Orchestrator) │
                        └────────┬────────┘
                                 │
           ┌─────────────────────┼─────────────────────┐
           │                     │                     │
           ▼                     ▼                     ▼
   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
   │ Researcher   │    │ Coder        │    │ Writer       │
   │ (as tool)    │    │ (as tool)    │    │ (as tool)    │
   └──────────────┘    └──────────────┘    └──────────────┘

Usage:
    composition = AgentComposition()
    composition.register_agent(researcher)
    composition.register_agent(coder)
    composition.register_agent(writer)
    
    # CEO agent can now use these as tools
   ceo.add_tools([
        composition.create_tool_from_agent(researcher.id),
        composition.create_tool_from_agent(coder.id),
        composition.create_tool_from_agent(writer.id),
    ])
    
    # CEO can now delegate:
    # "Research X, code it, write about it"
"""


class ToolBuilder:
    """
    Builder for creating complex tool compositions.
    """
    
    def __init__(self):
        self._tools: List[Callable] = []
    
    def add_search(self) -> 'ToolBuilder':
        """Add web search tool."""
        from novus.execution.environment import ExecutionEnvironment
        env = ExecutionEnvironment()
        
        async def search(query: str) -> str:
            results = await env.search_web(query)
            return str(results[:3])
        
        self._tools.append(("search", search))
        return self
    
    def add_code_executor(self) -> 'ToolBuilder':
        """Add code execution tool."""
        from novus.execution.environment import ExecutionEnvironment
        
        async def execute(code: str) -> str:
            env = ExecutionEnvironment()
            result = await env.execute_code(code)
            return result.output if result.success else result.error
        
        self._tools.append(("execute_code", execute))
        return self
    
    def add_agent(self, agent: Any) -> 'ToolBuilder':
        """Add an agent as tool."""
        tool = AgentTool(agent)
        self._tools.append((agent.id, tool.execute))
        return self
    
    def build(self) -> Dict[str, Callable]:
        """Build tool dictionary."""
        return dict(self._tools)
