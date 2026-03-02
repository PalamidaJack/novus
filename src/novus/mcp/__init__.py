"""
MCP (Model Context Protocol) support for NOVUS.

Implements the emerging standard for agent tool interoperability.
https://modelcontextprotocol.io
"""

from __future__ import annotations

import asyncio
import json
from typing import Dict, List, Optional, Any, Callable, AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
import structlog

logger = structlog.get_logger()


@dataclass
class MCPTool:
    """
    MCP Tool definition.
    
    Standardized tool schema for interoperability.
    """
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema
    handler: Optional[Callable] = None
    
    def to_schema(self) -> Dict[str, Any]:
        """Convert to MCP tool schema."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters
        }
    
    async def execute(self, **kwargs) -> Any:
        """Execute the tool handler."""
        if self.handler is None:
            raise ValueError(f"Tool {self.name} has no handler")
        
        if asyncio.iscoroutinefunction(self.handler):
            return await self.handler(**kwargs)
        return self.handler(**kwargs)


@dataclass
class MCPResource:
    """
    MCP Resource definition.
    
    Resources provide context/data to agents.
    """
    uri: str
    name: str
    description: str
    mime_type: str = "text/plain"
    content_provider: Optional[Callable] = None
    
    async def read(self) -> str:
        """Read resource content."""
        if self.content_provider is None:
            raise ValueError(f"Resource {self.name} has no provider")
        
        if asyncio.iscoroutinefunction(self.content_provider):
            return await self.content_provider()
        return self.content_provider()


@dataclass
class MCPPrompt:
    """
    MCP Prompt template.
    
    Reusable prompt definitions.
    """
    name: str
    description: str
    template: str
    arguments: List[Dict[str, Any]] = field(default_factory=list)
    
    def render(self, **kwargs) -> str:
        """Render prompt with arguments."""
        return self.template.format(**kwargs)


class MCPServer:
    """
    MCP Server implementation.
    
    Exposes NOVUS capabilities via the Model Context Protocol.
    Allows other agents/tools to discover and use NOVUS functionality.
    """
    
    def __init__(self, name: str = "novus-mcp-server", version: str = "0.1.0"):
        self.name = name
        self.version = version
        self.tools: Dict[str, MCPTool] = {}
        self.resources: Dict[str, MCPResource] = {}
        self.prompts: Dict[str, MCPPrompt] = {}
        
        logger.info("mcp_server_initialized", name=name, version=version)
    
    def register_tool(
        self,
        name: str,
        description: str,
        parameters: Optional[Dict[str, Any]] = None,
        handler: Optional[Callable] = None
    ) -> Callable:
        """
        Register a tool with the MCP server.
        
        Can be used as a decorator:
            @server.register_tool("search", "Search the web")
            async def search(query: str) -> str:
                return await web_search(query)
        """
        def decorator(func: Callable) -> Callable:
            tool = MCPTool(
                name=name,
                description=description,
                parameters=parameters or self._infer_parameters(func),
                handler=func
            )
            self.tools[name] = tool
            logger.info("mcp_tool_registered", name=name)
            return func
        
        if handler is not None:
            return decorator(handler)
        return decorator
    
    def register_resource(
        self,
        uri: str,
        name: str,
        description: str,
        mime_type: str = "text/plain",
        provider: Optional[Callable] = None
    ) -> Callable:
        """Register a resource."""
        def decorator(func: Callable) -> Callable:
            resource = MCPResource(
                uri=uri,
                name=name,
                description=description,
                mime_type=mime_type,
                content_provider=func
            )
            self.resources[uri] = resource
            logger.info("mcp_resource_registered", uri=uri)
            return func
        
        if provider is not None:
            return decorator(provider)
        return decorator
    
    def register_prompt(
        self,
        name: str,
        description: str,
        template: str,
        arguments: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """Register a prompt template."""
        prompt = MCPPrompt(
            name=name,
            description=description,
            template=template,
            arguments=arguments or []
        )
        self.prompts[name] = prompt
        logger.info("mcp_prompt_registered", name=name)
    
    def _infer_parameters(self, func: Callable) -> Dict[str, Any]:
        """Infer JSON schema from function signature."""
        import inspect
        sig = inspect.signature(func)
        properties = {}
        required = []
        
        for name, param in sig.parameters.items():
            if param.default == inspect.Parameter.empty:
                required.append(name)
            
            # Infer type from annotation
            param_type = "string"
            if param.annotation == int:
                param_type = "integer"
            elif param.annotation == float:
                param_type = "number"
            elif param.annotation == bool:
                param_type = "boolean"
            elif param.annotation == list or param.annotation == List:
                param_type = "array"
            elif param.annotation == dict or param.annotation == Dict:
                param_type = "object"
            
            properties[name] = {"type": param_type}
        
        return {
            "type": "object",
            "properties": properties,
            "required": required
        }
    
    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming MCP request."""
        method = request.get("method")
        params = request.get("params", {})
        
        if method == "initialize":
            return self._handle_initialize()
        elif method == "tools/list":
            return self._handle_tools_list()
        elif method == "tools/call":
            return await self._handle_tool_call(params)
        elif method == "resources/list":
            return self._handle_resources_list()
        elif method == "resources/read":
            return await self._handle_resource_read(params)
        elif method == "prompts/list":
            return self._handle_prompts_list()
        elif method == "prompts/get":
            return self._handle_prompt_get(params)
        else:
            return {"error": f"Unknown method: {method}"}
    
    def _handle_initialize(self) -> Dict[str, Any]:
        """Handle initialize request."""
        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": self.name,
                "version": self.version
            },
            "capabilities": {
                "tools": {"listChanged": True},
                "resources": {"listChanged": True, "subscribe": True},
                "prompts": {"listChanged": True}
            }
        }
    
    def _handle_tools_list(self) -> Dict[str, Any]:
        """Handle tools/list request."""
        return {
            "tools": [tool.to_schema() for tool in self.tools.values()]
        }
    
    async def _handle_tool_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/call request."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        tool = self.tools.get(tool_name)
        if not tool:
            return {"error": f"Tool not found: {tool_name}"}
        
        try:
            result = await tool.execute(**arguments)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": str(result)
                    }
                ]
            }
        except Exception as e:
            logger.error("mcp_tool_error", tool=tool_name, error=str(e))
            return {"error": str(e)}
    
    def _handle_resources_list(self) -> Dict[str, Any]:
        """Handle resources/list request."""
        return {
            "resources": [
                {
                    "uri": r.uri,
                    "name": r.name,
                    "description": r.description,
                    "mimeType": r.mime_type
                }
                for r in self.resources.values()
            ]
        }
    
    async def _handle_resource_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle resources/read request."""
        uri = params.get("uri")
        resource = self.resources.get(uri)
        
        if not resource:
            return {"error": f"Resource not found: {uri}"}
        
        try:
            content = await resource.read()
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": resource.mime_type,
                        "text": content
                    }
                ]
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _handle_prompts_list(self) -> Dict[str, Any]:
        """Handle prompts/list request."""
        return {
            "prompts": [
                {
                    "name": p.name,
                    "description": p.description,
                    "arguments": p.arguments
                }
                for p in self.prompts.values()
            ]
        }
    
    def _handle_prompt_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle prompts/get request."""
        name = params.get("name")
        arguments = params.get("arguments", {})
        
        prompt = self.prompts.get(name)
        if not prompt:
            return {"error": f"Prompt not found: {name}"}
        
        rendered = prompt.render(**arguments)
        return {
            "description": prompt.description,
            "messages": [
                {
                    "role": "user",
                    "content": {"type": "text", "text": rendered}
                }
            ]
        }


class MCPClient:
    """
    MCP Client for using external MCP servers.
    
    Allows NOVUS agents to use tools from other MCP-compatible systems.
    """
    
    def __init__(self):
        self.servers: Dict[str, MCPServer] = {}
        self.discovered_tools: Dict[str, Dict[str, Any]] = {}
        
    async def connect_to_server(self, server_url: str, name: str) -> bool:
        """
        Connect to an external MCP server.
        
        Args:
            server_url: URL of the MCP server
            name: Alias for this server
        """
        # In production, this would make HTTP/WebSocket connection
        # For now, simulate discovery
        logger.info("mcp_connecting", server=server_url, name=name)
        
        # Simulate tool discovery
        self.discovered_tools[name] = {
            "search": {"description": "Search the web"},
            "calculate": {"description": "Perform calculations"}
        }
        
        return True
    
    async def discover_tools(self, server_name: str) -> List[Dict[str, Any]]:
        """Discover tools from a connected server."""
        tools = self.discovered_tools.get(server_name, {})
        return [
            {"name": name, **info}
            for name, info in tools.items()
        ]
    
    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """Call a tool on a remote MCP server."""
        # In production, this would make RPC call
        logger.info(
            "mcp_tool_call",
            server=server_name,
            tool=tool_name,
            args=arguments
        )
        
        # Simulate execution
        await asyncio.sleep(0.1)
        return f"Result from {server_name}.{tool_name}"
    
    def get_all_tools(self) -> Dict[str, MCPTool]:
        """Get all discovered tools as MCPTool objects."""
        tools = {}
        for server_name, server_tools in self.discovered_tools.items():
            for tool_name, tool_info in server_tools.items():
                full_name = f"{server_name}_{tool_name}"
                tools[full_name] = MCPTool(
                    name=full_name,
                    description=tool_info["description"],
                    parameters={"type": "object", "properties": {}}
                )
        return tools


# Example usage and built-in tools
def create_novus_mcp_server() -> MCPServer:
    """Create a NOVUS MCP server with built-in tools."""
    server = MCPServer(name="novus", version="0.1.0")
    
    @server.register_tool(
        name="web_search",
        description="Search the web for information",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"]
        }
    )
    async def web_search(query: str) -> str:
        """Search the web."""
        # In production, use actual search API
        return f"Search results for: {query}"
    
    @server.register_tool(
        name="execute_code",
        description="Execute Python code safely",
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"},
                "timeout": {"type": "number", "description": "Timeout in seconds"}
            },
            "required": ["code"]
        }
    )
    async def execute_code(code: str, timeout: int = 30) -> str:
        """Execute Python code."""
        from novus.execution.environment import ExecutionEnvironment
        env = ExecutionEnvironment()
        result = await env.execute_code(code)
        return result.output if result.success else result.error
    
    @server.register_tool(
        name="swarm_solve",
        description="Use NOVUS swarm to solve a complex problem",
        parameters={
            "type": "object",
            "properties": {
                "problem": {"type": "string", "description": "Problem description"},
                "num_agents": {"type": "integer", "description": "Number of agents to use"}
            },
            "required": ["problem"]
        }
    )
    async def swarm_solve(problem: str, num_agents: int = 3) -> str:
        """Use swarm intelligence."""
        # This would integrate with the actual swarm
        return f"Swarm solution for: {problem}"
    
    # Register resources
    @server.register_resource(
        uri="docs://novus/overview",
        name="NOVUS Overview",
        description="Overview of the NOVUS platform"
    )
    async def get_overview() -> str:
        return "NOVUS is a next-generation agentic AI platform..."
    
    # Register prompts
    server.register_prompt(
        name="research_assistant",
        description="A prompt for research tasks",
        template="""You are a research assistant helping with: {topic}

Please provide:
1. Key findings
2. Sources
3. Analysis
4. Recommendations

Research topic: {topic}""",
        arguments=[
            {"name": "topic", "description": "Research topic", "required": True}
        ]
    )
    
    return server


# FastAPI integration
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

mcp_router = APIRouter(prefix="/mcp")

# Global server instance
_mcp_server: Optional[MCPServer] = None

def get_mcp_server() -> MCPServer:
    """Get or create MCP server."""
    global _mcp_server
    if _mcp_server is None:
        _mcp_server = create_novus_mcp_server()
    return _mcp_server

@mcp_router.post("/rpc")
async def mcp_rpc(request: Request):
    """MCP JSON-RPC endpoint."""
    try:
        body = await request.json()
        server = get_mcp_server()
        result = await server.handle_request(body)
        return JSONResponse(result)
    except Exception as e:
        logger.error("mcp_rpc_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@mcp_router.get("/tools")
async def list_tools():
    """List available tools."""
    server = get_mcp_server()
    return server._handle_tools_list()

@mcp_router.get("/resources")
async def list_resources():
    """List available resources."""
    server = get_mcp_server()
    return server._handle_resources_list()
