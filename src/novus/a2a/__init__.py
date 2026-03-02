"""A2A interoperability primitives (Agent Card + lightweight task RPC)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class A2ACapability:
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]


class AgentCardBuilder:
    """Builds a minimal A2A-style Agent Card for discovery."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        self.capabilities: List[A2ACapability] = []

    def register_capability(
        self,
        name: str,
        description: str,
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.capabilities.append(
            A2ACapability(
                name=name,
                description=description,
                input_schema=input_schema or {"type": "object", "properties": {}},
                output_schema=output_schema or {"type": "object", "properties": {}},
            )
        )

    def build(self) -> Dict[str, Any]:
        return {
            "name": "novus-agent",
            "version": "0.1.0",
            "description": "NOVUS next-generation agent runtime",
            "protocol": "a2a-0.3-lite",
            "url": self.base_url,
            "endpoints": {
                "task_rpc": f"{self.base_url}/a2a/rpc",
                "health": f"{self.base_url}/health",
            },
            "capabilities": [
                {
                    "name": c.name,
                    "description": c.description,
                    "input_schema": c.input_schema,
                    "output_schema": c.output_schema,
                }
                for c in self.capabilities
            ],
            "timestamp": _utcnow_iso(),
        }


class A2ARequest(BaseModel):
    jsonrpc: str = Field(default="2.0")
    id: str | int | None = None
    method: str
    params: Dict[str, Any] = Field(default_factory=dict)


class A2AResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


class A2ABridge:
    """Simple A2A bridge for interoperable task handoff."""

    def __init__(self):
        self._handlers: Dict[str, Any] = {}

    def register_handler(self, method: str, handler: Any) -> None:
        self._handlers[method] = handler

    async def handle(self, req: A2ARequest) -> A2AResponse:
        handler = self._handlers.get(req.method)
        if handler is None:
            return A2AResponse(
                id=req.id,
                error={"code": -32601, "message": f"Method not found: {req.method}"},
            )
        try:
            result = await handler(req.params)
            return A2AResponse(id=req.id, result=result)
        except Exception as exc:
            return A2AResponse(
                id=req.id,
                error={"code": -32000, "message": str(exc)},
            )


a2a_router = APIRouter(prefix="/a2a", tags=["a2a"])
_bridge = A2ABridge()
_card_builder = AgentCardBuilder()
_card_builder.register_capability(
    name="task.run",
    description="Run a task via NOVUS Agent runtime",
    input_schema={
        "type": "object",
        "properties": {"prompt": {"type": "string"}},
        "required": ["prompt"],
    },
    output_schema={
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    },
)


def get_a2a_bridge() -> A2ABridge:
    return _bridge


def get_agent_card(base_url: Optional[str] = None) -> Dict[str, Any]:
    if base_url:
        builder = AgentCardBuilder(base_url=base_url)
        for cap in _card_builder.capabilities:
            builder.register_capability(cap.name, cap.description, cap.input_schema, cap.output_schema)
        return builder.build()
    return _card_builder.build()


@a2a_router.get("/agent-card")
async def a2a_agent_card():
    return get_agent_card()


@a2a_router.get("/.well-known/agent-card.json")
async def a2a_well_known_agent_card():
    return get_agent_card()


@a2a_router.post("/rpc")
async def a2a_rpc(req: A2ARequest):
    if req.jsonrpc != "2.0":
        raise HTTPException(status_code=400, detail="Only JSON-RPC 2.0 is supported")
    return (await _bridge.handle(req)).model_dump(exclude_none=True)

