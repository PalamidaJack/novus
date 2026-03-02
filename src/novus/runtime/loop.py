"""Recursive runtime loop implementing next-gen agent execution patterns."""

from __future__ import annotations

import asyncio
import json
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional

import structlog

from novus.execution.environment import ExecutionEnvironment
from novus.runtime.context import ContextCompressor, LayeredMemoryManager
from novus.runtime.interrupts import InterruptQueue
from novus.runtime.middleware import RuntimeHookContext, RuntimeMiddleware, with_default_observer
from novus.runtime.policy import RuntimePolicyEngine
from novus.runtime.router import RuntimeModelRouter
from novus.runtime.artifacts import RunArtifactLogger, RunEvent, now_iso
from novus.runtime.state import RuntimeState
from novus.runtime.subagents import SubagentDispatcher, SubagentTask
from novus.runtime.tools import ToolRegistry

logger = structlog.get_logger()


class RecursiveAgentRuntime:
    """Simple loop with strong context/state management."""

    def __init__(
        self,
        llm_caller,
        execution_env: Optional[ExecutionEnvironment] = None,
        state_dir: Optional[Path] = None,
        router: Optional[RuntimeModelRouter] = None,
        middleware: Optional[RuntimeMiddleware] = None,
        interrupts: Optional[InterruptQueue] = None,
        max_parallel_tools: int = 3,
        policy_engine: Optional[RuntimePolicyEngine] = None,
        artifact_logger: Optional[RunArtifactLogger] = None,
    ):
        self.llm_caller = llm_caller
        self.execution_env = execution_env or ExecutionEnvironment()
        self.state_dir = Path(state_dir or Path.home() / ".novus" / "sessions")
        self.router = router or RuntimeModelRouter()
        self.middleware = with_default_observer(middleware or RuntimeMiddleware())
        self.interrupts = interrupts or InterruptQueue()
        self.memory = LayeredMemoryManager()
        self.compressor = ContextCompressor()
        self.max_turns = 16
        self.max_parallel_tools = max(1, max_parallel_tools)
        self.policy_engine = policy_engine or RuntimePolicyEngine()
        self.artifact_logger = artifact_logger or RunArtifactLogger()
        self.last_session_id: Optional[str] = None

        self.subagents = SubagentDispatcher(worker=self._run_subagent)
        self.tool_registry = ToolRegistry()

    async def run(self, prompt: str, task_type: str = "reason") -> Any:
        state = RuntimeState(original_request=prompt)
        state.ensure_plan(prompt)
        self.last_session_id = state.session_id
        self._log_event(
            state.session_id,
            0,
            "start",
            {
                "prompt": prompt,
                "task_type": task_type,
                "thread_id": state.thread_id,
                "checkpoint_id": state.checkpoint_id,
            },
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are NOVUS runtime. You MUST reply in JSON using this protocol:\n"
                    "{\"type\":\"tool_call\",\"tool\":\"search_web|execute_code|subagent_scan\",\"args\":{...}}\n"
                    "or {\"type\":\"final\",\"answer\":\"...\"}.\n"
                    "If you receive PROTOCOL ERROR or TOOL VALIDATION ERROR, fix and retry.\n"
                    f"Allowed tools: {', '.join(self.tool_registry.list_tools())}."
                ),
            },
            {"role": "system", "content": self.memory.build_context()},
            {"role": "system", "content": state.to_prompt_block()},
            {"role": "user", "content": prompt},
        ]

        result = await self._loop(messages=messages, state=state, turn=0, task_type=task_type)
        state.dump(self.state_dir / f"{state.session_id}.json")
        self._log_event(state.session_id, 9999, "end", {"result": str(result)[:4000]})
        return result

    async def _loop(self, messages: list[dict], state: RuntimeState, turn: int, task_type: str) -> Any:
        state.rotate_checkpoint()
        if turn >= self.max_turns:
            self._log_event(state.session_id, turn, "error_max_turns", {"message": "Reached max turns"})
            return "Reached max turns"

        messages, compaction = self.compressor.maybe_compact(messages)
        if compaction:
            state.append_decision(f"Context compacted: dropped {compaction.dropped_messages} messages")
            self._log_event(
                state.session_id,
                turn,
                "compaction",
                {"dropped_messages": compaction.dropped_messages, "summary": compaction.summary[:1000]},
            )

        interrupt = await self.interrupts.pop_nowait()
        if interrupt:
            messages.append(
                {
                    "role": "system",
                    "content": f"USER INTERJECTION ({interrupt.timestamp}): {interrupt.content}. Update plan accordingly.",
                }
            )

        route = self.router.select(task_type=task_type, complexity_hint="high" if turn < 2 else "medium")

        before_ctx = RuntimeHookContext(
            session_id=state.session_id,
            turn=turn,
            payload={"model": route.model, "tier": route.tier, "reason": route.reason},
        )
        await self.middleware.run_before_infer(before_ctx)

        response = await self.llm_caller(prompt=self._to_prompt(messages), model=route.model)
        self._log_event(
            state.session_id,
            turn,
            "infer",
            {"model": route.model, "tier": route.tier, "response": str(response)[:2000]},
        )
        if str(response).startswith("[Error: LLM call failed"):
            self._log_event(state.session_id, turn, "error_llm", {"response": str(response)})
            return str(response)

        await self.middleware.run_after_infer(
            RuntimeHookContext(
                session_id=state.session_id,
                turn=turn,
                payload={"response": str(response)[:3000]},
            )
        )

        messages.append({"role": "assistant", "content": str(response)})

        payload = self._extract_json_payload(str(response))
        if payload is None:
            self._log_event(state.session_id, turn, "error_protocol", {"response": str(response)[:1500]})
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "PROTOCOL ERROR: response must be JSON with either "
                        '{"type":"tool_call","tool":"...","args":{...}} or {"type":"final","answer":"..."}.'
                    ),
                }
            )
            return await self._loop(messages=messages, state=state, turn=turn + 1, task_type=task_type)

        tool_calls = self._extract_tool_calls(payload)
        if not tool_calls:
            final_answer = self._extract_final_answer(payload, str(response))
            if state.plan:
                state.set_completed(state.plan[-1].id, notes="Finalized")
            self._log_event(state.session_id, turn, "final", {"answer": str(final_answer)[:2000]})
            return final_answer

        validated_calls = []
        validation_errors = []
        for i, (tool_name, args) in enumerate(tool_calls):
            validation = self.tool_registry.validate(tool_name, args)
            if not validation.valid:
                validation_errors.append(
                    {
                        "index": i,
                        "tool": tool_name,
                        "details": validation.error,
                        "expected_schema": validation.schema,
                    }
                )
                continue
            validated_calls.append((i, tool_name, validation.normalized_args))

        if validation_errors:
            validation_result = {"error": "TOOL_VALIDATION_ERROR", "issues": validation_errors}
            state.add_tool_event("multi_tool_validation", {"count": len(tool_calls)}, validation_result)
            self._log_event(state.session_id, turn, "error_tool_validation", validation_result)
            messages.append(
                {
                    "role": "system",
                    "content": f"TOOL VALIDATION ERROR: {json.dumps(validation_result, default=str)[:4000]}",
                }
            )
            messages.append({"role": "system", "content": state.to_prompt_block()})
            return await self._loop(messages=messages, state=state, turn=turn + 1, task_type=task_type)

        policy_violations = []
        for idx, tool_name, normalized_args in validated_calls:
            decision = self.policy_engine.evaluate(tool_name, normalized_args)
            if not decision.allowed:
                policy_violations.append(
                    {
                        "index": idx,
                        "tool": tool_name,
                        "risk": decision.risk,
                        "action": decision.action,
                        "reason": decision.reason,
                    }
                )

        if policy_violations:
            violation_result = {"error": "POLICY_VIOLATION", "issues": policy_violations}
            state.add_tool_event("policy_violation", {"count": len(policy_violations)}, violation_result)
            self._log_event(state.session_id, turn, "error_policy", violation_result)
            messages.append(
                {
                    "role": "system",
                    "content": f"POLICY ERROR: {json.dumps(violation_result, default=str)[:4000]}",
                }
            )
            messages.append({"role": "system", "content": state.to_prompt_block()})
            return await self._loop(messages=messages, state=state, turn=turn + 1, task_type=task_type)

        tool_results = await self._execute_tool_calls(validated_calls, state=state)
        self._log_event(state.session_id, turn, "multi_tool_result", {"results": tool_results})
        for entry in tool_results:
            state.add_tool_event(entry["tool"], entry["args"], entry["result"])
            await self.middleware.run_after_tool(
                RuntimeHookContext(
                    session_id=state.session_id,
                    turn=turn,
                    payload={
                        "tool": entry["tool"],
                        "args": entry["args"],
                        "result": str(entry["result"])[:3000],
                    },
                )
            )

        messages.append(
            {
                "role": "system",
                "content": f"TOOL RESULT: {json.dumps(tool_results, default=str)[:4000]}",
            }
        )

        messages.append({"role": "system", "content": state.to_prompt_block()})
        return await self._loop(messages=messages, state=state, turn=turn + 1, task_type=task_type)

    def _to_prompt(self, messages: list[dict]) -> str:
        return "\n\n".join(f"[{m['role'].upper()}]\n{m['content']}" for m in messages if m.get("content"))

    def _extract_tool_calls(self, payload: Dict[str, Any]) -> list[tuple[str, Dict[str, Any]]]:
        calls: list[tuple[str, Dict[str, Any]]] = []
        if payload.get("type") == "tool_call":
            tool = payload.get("tool")
            args = payload.get("args", {})
            if isinstance(tool, str) and isinstance(args, dict):
                calls.append((tool, args))
        if isinstance(payload.get("tool_calls"), list):
            for item in payload["tool_calls"]:
                if not isinstance(item, dict):
                    continue
                tool = item.get("tool")
                args = item.get("args", {})
                if isinstance(tool, str) and isinstance(args, dict):
                    calls.append((tool, args))
        return calls

    def _extract_final_answer(self, payload: Dict[str, Any], text: str) -> str:
        if payload and payload.get("type") == "final" and isinstance(payload.get("answer"), str):
            return payload["answer"]
        return text

    def _extract_json_payload(self, text: str) -> Optional[Dict[str, Any]]:
        # First try strict JSON body.
        raw = text.strip()
        if raw.startswith("{") and raw.endswith("}"):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        # Fallback: attempt to parse first object-like block.
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = raw[start : end + 1]
            try:
                parsed = json.loads(snippet)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return None
        return None

    async def _execute_tool(self, name: str, args: Dict[str, Any]) -> Any:
        if name == "search_web":
            query = args.get("query", "")
            return await self.execution_env.search_web(query, num_results=args.get("num_results", 5))

        if name == "execute_code":
            code = args.get("code", "")
            lang = args.get("language", "python")
            result = await self.execution_env.execute_code(code, language=lang)
            return {
                "success": result.success,
                "output": result.output,
                "error": result.error,
                "execution_time_ms": result.execution_time_ms,
            }

        if name == "subagent_scan":
            prompts = args.get("prompts", [])
            tasks = [SubagentTask(name=f"scan_{i}", prompt=p) for i, p in enumerate(prompts)]
            results = await self.subagents.dispatch_many(tasks, depth=0)
            return [r.__dict__ for r in results]

        if name == "call_hosted_tool":
            endpoint = args.get("endpoint", "")
            payload = args.get("payload", {})
            method = args.get("method", "POST")
            return await self.execution_env.call_hosted_tool(endpoint=endpoint, payload=payload, method=method)

        return {"error": f"Unknown tool: {name}"}

    async def _execute_tool_calls(
        self,
        calls: list[tuple[int, str, Dict[str, Any]]],
        state: Optional[RuntimeState] = None,
    ) -> list[Dict[str, Any]]:
        sem = asyncio.Semaphore(self.max_parallel_tools)

        async def _run(index: int, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
            if state is not None:
                cached = state.get_cached_tool_result(tool, args)
                if cached is not None:
                    return {
                        "index": index,
                        "tool": tool,
                        "args": args,
                        "result": cached,
                        "idempotent_cache_hit": True,
                    }
            async with sem:
                result = await self._execute_tool(tool, args)
                if state is not None:
                    state.cache_tool_result(tool, args, result)
                return {"index": index, "tool": tool, "args": args, "result": result, "idempotent_cache_hit": False}

        results = await asyncio.gather(*[_run(i, t, a) for i, t, a in calls])
        # Deterministic order by original tool-call index.
        results.sort(key=lambda r: r["index"])
        return results

    def _log_event(self, session_id: str, turn: int, event_type: str, payload: Dict[str, Any]) -> None:
        trace_id = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]
        self.artifact_logger.write(
            RunEvent(
                event_type=event_type,
                session_id=session_id,
                turn=turn,
                timestamp=now_iso(),
                payload={"trace_id": trace_id, "group_id": session_id, **payload},
            )
        )

    async def _run_subagent(self, prompt: str) -> str:
        # lightweight subagent route
        route = self.router.select(task_type="classify", complexity_hint="low")
        response = await self.llm_caller(prompt=prompt, model=route.model)
        return f"summary: {str(response)[:1200]}"
