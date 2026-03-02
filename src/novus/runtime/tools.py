"""Typed tool protocol registry and validation for runtime tool calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Type

from pydantic import BaseModel, Field, ValidationError


class SearchWebArgs(BaseModel):
    query: str = Field(min_length=1)
    num_results: int = Field(default=5, ge=1, le=20)


class ExecuteCodeArgs(BaseModel):
    code: str = Field(min_length=1)
    language: str = Field(default="python")


class SubagentScanArgs(BaseModel):
    prompts: list[str] = Field(min_length=1, max_length=16)


class HostedToolArgs(BaseModel):
    endpoint: str = Field(min_length=1)
    payload: Dict[str, Any] = Field(default_factory=dict)
    method: str = Field(default="POST")


@dataclass
class ToolValidationResult:
    valid: bool
    normalized_args: Dict[str, Any]
    error: str | None = None
    schema: Dict[str, Any] | None = None


class ToolRegistry:
    """Registry of runtime tool schemas with strict argument validation."""

    def __init__(self):
        self._schemas: Dict[str, Type[BaseModel]] = {
            "search_web": SearchWebArgs,
            "execute_code": ExecuteCodeArgs,
            "subagent_scan": SubagentScanArgs,
            "call_hosted_tool": HostedToolArgs,
        }

    def list_tools(self) -> list[str]:
        return sorted(self._schemas.keys())

    def schema_for(self, tool_name: str) -> Dict[str, Any] | None:
        model = self._schemas.get(tool_name)
        if not model:
            return None
        return model.model_json_schema()

    def validate(self, tool_name: str, args: Dict[str, Any]) -> ToolValidationResult:
        model = self._schemas.get(tool_name)
        if not model:
            return ToolValidationResult(
                valid=False,
                normalized_args=args,
                error=f"Unknown tool: {tool_name}",
                schema={"allowed_tools": self.list_tools()},
            )

        try:
            parsed = model.model_validate(args)
            return ToolValidationResult(valid=True, normalized_args=parsed.model_dump())
        except ValidationError as exc:
            return ToolValidationResult(
                valid=False,
                normalized_args=args,
                error=str(exc),
                schema=model.model_json_schema(),
            )
