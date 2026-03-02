# NOVUS Next-Gen Improvement Roadmap

Date: 2026-03-02
Status: In progress

## Goal

Implement the full improvement set identified from 2026 ecosystem research:

1. MCP auth/spec hardening
2. MCP transport hardening
3. A2A interoperability
4. Hosted tool backends
5. Background execution mode
6. Durable execution contract
7. Standardized observability
8. Trace grading and regression gates
9. Benchmark expansion hooks
10. OWASP/NIST aligned security controls
11. Prompt/context caching
12. Computer-use sandbox mode

## Execution Plan

### Phase 1: Protocol + Interop

- Upgrade MCP server to modern protocol metadata and auth checks.
- Add Streamable HTTP origin policy enforcement.
- Add A2A module:
  - Agent Card generation
  - JSON-RPC style task handler
  - Discovery endpoint integration

### Phase 2: Runtime Reliability

- Add durable checkpoint IDs and thread IDs in runtime state.
- Add idempotency keys for side-effecting tool calls.
- Add background run manager with enqueue/poll/cancel APIs.
- Add hosted tool route stubs and deterministic replay metadata.

### Phase 3: Observability + Eval

- Add OpenTelemetry-compatible trace envelope fields.
- Emit span-like events for infer/tool/handoff/policy/guardrail.
- Add trace grading in readiness pipeline and CLI command.
- Add benchmark case extensibility for SWE-style tasks.

### Phase 4: Security + Cost

- Add GenAI risk category guardrails:
  - prompt injection
  - insecure output handling
  - excessive agency
  - sensitive data disclosure
- Add risk scoring updates in runtime policy engine.
- Add prompt cache support for static context prefixes.
- Add strict sandbox mode for computer-use actions.

### Phase 5: Verification + Documentation

- Add/extend tests for each new subsystem.
- Update README and onboarding with new CLI/API usage.
- Run full test suite and readiness gates.

## Definition of Done

- All subsystems compile and test successfully.
- New APIs are documented and exercised in tests.
- Readiness output includes trace-grade result and benchmark expansion hooks.
- Runtime exports include enough metadata for deterministic replay checks.
