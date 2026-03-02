"""Middleware pipeline hooks around runtime turn execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, List

from novus.monitoring import METRICS


@dataclass
class RuntimeHookContext:
    session_id: str
    turn: int
    payload: dict[str, Any]


Hook = Callable[[RuntimeHookContext], Awaitable[None]]


class RuntimeMiddleware:
    def __init__(self):
        self.before_infer_hooks: List[Hook] = []
        self.after_infer_hooks: List[Hook] = []
        self.after_tool_hooks: List[Hook] = []

    def on_before_infer(self, hook: Hook) -> None:
        self.before_infer_hooks.append(hook)

    def on_after_infer(self, hook: Hook) -> None:
        self.after_infer_hooks.append(hook)

    def on_after_tool(self, hook: Hook) -> None:
        self.after_tool_hooks.append(hook)

    async def run_before_infer(self, ctx: RuntimeHookContext) -> None:
        for hook in self.before_infer_hooks:
            await hook(ctx)

    async def run_after_infer(self, ctx: RuntimeHookContext) -> None:
        for hook in self.after_infer_hooks:
            await hook(ctx)

    async def run_after_tool(self, ctx: RuntimeHookContext) -> None:
        for hook in self.after_tool_hooks:
            await hook(ctx)


class OTelLikeRuntimeObserver:
    """Best-effort OTEL semantic convention adapter."""

    async def before_infer(self, ctx: RuntimeHookContext) -> None:
        METRICS.record_runtime_span("agent.infer.start", status="ok")

    async def after_infer(self, ctx: RuntimeHookContext) -> None:
        METRICS.record_runtime_span("agent.infer.end", status="ok")

    async def after_tool(self, ctx: RuntimeHookContext) -> None:
        status = "ok"
        payload = ctx.payload or {}
        if "error" in str(payload.get("result", "")).lower():
            status = "error"
        METRICS.record_runtime_span("agent.tool", status=status)


def with_default_observer(middleware: RuntimeMiddleware) -> RuntimeMiddleware:
    observer = OTelLikeRuntimeObserver()
    middleware.on_before_infer(observer.before_infer)
    middleware.on_after_infer(observer.after_infer)
    middleware.on_after_tool(observer.after_tool)
    return middleware
