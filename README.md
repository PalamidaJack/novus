# NOVUS: Next-Generation Agentic AI Platform

<p align="center">
  <img src="https://img.shields.io/badge/NOVUS-v0.1.0-emerald?style=for-the-badge" alt="Version"/>
  <img src="https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge" alt="Python"/>
  <img src="https://img.shields.io/badge/Tests-26%2F26%20Passing-green?style=for-the-badge" alt="Tests"/>
</p>

<p align="center">
  <b>A self-organizing, self-improving collective intelligence platform for autonomous innovation.</b>
</p>

---

## 🚀 Quick Start

```bash
# Install
pip install -e .

# Setup (interactive wizard)
novus onboard

# Verify installation
novus doctor

# Quick swarm smoke test
novus swarm --problem "What is 15 * 23?" --agents 3

# Start using
novus start
```

---

## ✨ Features

### Core Capabilities

| Feature | Description | Status |
|---------|-------------|--------|
| **Agent Swarms** | Heterogeneous agents with evolutionary optimization | ✅ |
| **World Model** | JEPA-based simulation for planning | ✅ |
| **Memory** | Three-form + Engram O(1) lookup | ✅ |
| **Streaming** | Real-time SSE responses | ✅ |
| **MCP** | Model Context Protocol support | ✅ |
| **A2A** | Agent-to-Agent discovery + RPC handoff | ✅ |
| **Validation** | Pydantic output schemas | ✅ |
| **Human-in-Loop** | Approval checkpoints | ✅ |
| **Evaluation** | Built-in test framework | ✅ |

### Advanced Capabilities

| Feature | Description | Status |
|---------|-------------|--------|
| **Browser Automation** | Playwright web interaction | ✅ |
| **Agent Composition** | Agent-as-tool pattern | ✅ |
| **Knowledge Base** | RAG with document ingestion | ✅ |
| **Guardrails** | Input/output safety filters | ✅ |
| **Competition** | Adversarial red teaming | ✅ |
| **Debate** | Structured multi-agent argumentation | ✅ |
| **Monitoring** | Prometheus metrics | ✅ |
| **Background Runs** | Async submit/poll/cancel execution mode | ✅ |
| **Trace Grading** | Behavioral trace quality gates | ✅ |
| **Strict Sandbox** | High-risk computer-use gating profile | ✅ |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         NOVUS PLATFORM                           │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   SWARM      │  │   WORLD      │  │   MEMORY    │           │
│  │   LAYER      │  │   MODEL      │  │   LAYER      │           │
│  │              │  │   ENGINE     │  │              │           │
│  │ • Evolution  │  │              │  │ • Episodic   │           │
│  │ • Consensus  │  │ • Physics    │  │ • Semantic   │           │
│  │ • Debate     │  │ • Causal     │  │ • Engram     │           │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘           │
│         └─────────────────┴─────────────────┘                    │
│                                 │                                │
│                        ┌────────▼────────┐                      │
│                        │  META-COGNITIVE │                      │
│                        │     CONTROL      │                      │
│                        └────────┬────────┘                      │
│                                 │                                │
│  ┌─────────────────────────────▼──────────────────────────────┐ │
│  │                    EXECUTION & SAFETY                      │ │
│  │  • Code Execution  • Browser Tools  • Guardrails  • MCP    │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📖 Documentation

- [Quick Start Guide](docs/ONBOARDING.md)
- [API Documentation](docs/api.md)
- [Architecture Overview](docs/architecture.md)
- [Competition System Analysis](docs/competition-analysis.md)
- [Implementation Status](docs/implementation-status.md)

---

## 🎯 Usage Examples

### 1. Basic Agent

```python
from novus.core.agent import Agent
from novus.core.models import AgentConfig, AgentCapability

config = AgentConfig(
    name="Researcher",
    capabilities={AgentCapability.RESEARCH, AgentCapability.ANALYSIS}
)
agent = Agent(config)

# Run task
result = await agent.run("Analyze market trends")
```

### 2. Swarm Intelligence

```python
from novus.swarm.orchestrator import SwarmOrchestrator
from novus.core.models import SwarmConfig

config = SwarmConfig(target_agent_count=5)
swarm = SwarmOrchestrator(config)
await swarm.start()

# Collective solve
solution = await swarm.collective_solve(
    problem="Design a scalable database",
    n_agents=3
)

print(f"Solution: {solution.content}")
print(f"Confidence: {solution.confidence:.2%}")
```

### 3. Streaming Responses

```python
from novus.streaming import StreamingAgent

agent = StreamingAgent("1", "Assistant")
async for event in agent.stream_think("Explain quantum computing"):
    if event.event_type == "chunk":
        print(event.content, end="")  # Real-time tokens
    elif event.event_type == "thought":
        print(f"\n[Thinking: {event.thought}]\n")
```

### 4. Knowledge Base (RAG)

```python
from novus.knowledge import KnowledgeBase

kb = KnowledgeBase(name="docs")

# Add documents
await kb.add_file("./manual.pdf")
await kb.add_url("https://docs.example.com")

# Query
results = await kb.search("How do I reset password?", top_k=5)
context = await kb.get_context("Your query")
```

### 5. Competitive Improvement

```python
from novus.competition import CompetitiveSwarm

competition = CompetitiveSwarm()
competition.add_agent(creator, role="blue_team")
competition.add_agent(critic, role="red_team")

# Use adversarial testing
result = await competition.improve_solution(
    "Design secure authentication",
    strategy="red_team"
)

print(f"Improvements: {len(result['improvements'])}")
```

### 6. Browser Automation

```python
from novus.tools.browser import BrowserToolkit

toolkit = BrowserToolkit()
await toolkit.start()

# Navigate and extract
obs = await toolkit.navigate("https://example.com")
links = await toolkit.extract_links()

await toolkit.click("#submit")
await toolkit.stop()
```

---

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_comprehensive.py -v

# Run with coverage
pytest tests/ --cov=src/novus --cov-report=html

# Run slow tests
pytest tests/ -m slow

# Environment diagnostics
novus doctor

# One-command local readiness pipeline
novus readiness --output-dir .novus-bench

# Optional: run only benchmark gates (skip unit tests)
novus readiness --output-dir .novus-bench --skip-tests

# Emit machine-readable readiness report
novus readiness --output-dir .novus-bench --report-json .novus-bench/readiness_report.json

# Grade latest runtime trace quality
novus trace-grade --min-score 0.7

# Shell wrapper equivalent
./scripts/run_readiness.sh

# Optional: sign exported bundles during readiness
NOVUS_BUNDLE_SIGNING_KEY=your-key ./scripts/run_readiness.sh
```

**Current Status:** 26/26 tests passing ✅

## 📦 Benchmark Artifacts

```bash
# Run default benchmark cases and export reproducible run bundles
novus benchmark-export --output-dir .novus-bench

# Add custom/SWE-style benchmark cases from JSON
novus benchmark-export --output-dir .novus-bench --external-cases ./configs/benchmark_cases.json

# Optional: sign bundle manifests for tamper-evident verification
novus benchmark-export --output-dir .novus-bench --signing-key "$NOVUS_BUNDLE_SIGNING_KEY"

# Compare against baseline and emit CI-friendly markdown summary
novus benchmark-export \
  --output-dir .novus-bench \
  --baseline .github/benchmarks/baseline_snapshot.json \
  --category-thresholds .github/benchmarks/category_thresholds.json \
  --summary-md .novus-bench/summary.md \
  --snapshot-out .novus-bench/current_snapshot.json \
  --max-case-latency-regression-pct 300 \
  --allow-case-pass-failures 0
```

Output includes:
- `.novus-bench/benchmark_report.json`
- `.novus-bench/bundles/<session_id>/manifest.json`
- `.novus-bench/bundles/<session_id>/events.jsonl`

```bash
# Promote a run report to the tracked baseline snapshot
novus benchmark-promote-baseline \
  --source .novus-bench/benchmark_report.json \
  --output .github/benchmarks/baseline_snapshot.json

# Evaluate an existing benchmark report against baseline thresholds
novus benchmark-evaluate \
  --report .novus-bench/benchmark_report.json \
  --baseline .github/benchmarks/baseline_snapshot.json \
  --category-thresholds .github/benchmarks/category_thresholds.json
```

---

## 🐳 Docker

```bash
# Build and run
docker-compose up -d

# Services:
# - NOVUS API: http://localhost:8000
# - Prometheus: http://localhost:9090
# - Redis: localhost:6379

# View logs
docker-compose logs -f novus
```

---

## 📊 API Reference

### Core Endpoints

```http
GET    /                 # Health check
GET    /health           # System status
GET    /metrics          # Prometheus metrics

POST   /tasks            # Submit task
GET    /tasks/{id}       # Get task result

GET    /swarm/status     # Swarm status
POST   /swarm/solve      # Collective solve

GET    /stream/chat      # SSE streaming

GET    /mcp/tools        # List MCP tools
POST   /mcp/rpc          # MCP JSON-RPC
GET    /.well-known/agent-card.json  # A2A discovery card
POST   /a2a/rpc          # A2A task handoff RPC

POST   /background-runs              # Submit background run
GET    /background-runs              # List background runs
GET    /background-runs/{task_id}    # Poll background run
POST   /background-runs/{task_id}/cancel  # Cancel background run

GET    /approvals/pending    # Pending approvals
POST   /approvals/{id}/approve
POST   /approvals/{id}/reject

POST   /eval/run         # Run evaluation
GET    /runs/{session_id}/trace-grade   # Trace quality scoring
```

---

## 🛡️ Safety Features

- **Guardrails** - Input/output filtering
- **Human Approval** - Critical action checkpoints
- **Sandboxed Execution** - Isolated code running
- **PII Detection** - Automatic redaction
- **Rate Limiting** - Prevent abuse

---

## 📈 Monitoring

Built-in Prometheus metrics:

```
novus_tasks_completed_total
novus_task_duration_seconds
novus_agents_total
novus_agent_fitness
novus_memory_entries
novus_api_requests_total
```

---

## 🔬 Research Backing

NOVUS implements proven research patterns:

| Feature | Research Source |
|---------|-----------------|
| Debate | Irving et al. (2018) - "AI Safety via Debate" |
| Red Teaming | Anthropic - Red Teaming Language Models |
| Evolution | ETH Zurich - SOHM Paper |
| Engram Memory | DeepSeek - Conditional Memory via Scalable Lookup |
| Tournament | Goldberg (1989) - Genetic Algorithms |

---

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing`)
5. Open Pull Request

---

## 📜 License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- OpenAI for debate research
- Anthropic for red teaming methods
- DeepSeek for Engram architecture
- ETH Zurich for swarm optimization

---

<p align="center">
  <b>Built with 💚 for the future of AI</b>
</p>

<p align="center">
  <a href="https://github.com/novus-ai/novus">GitHub</a> •
  <a href="https://docs.novus.ai">Documentation</a> •
  <a href="https://discord.gg/novus">Discord</a>
</p>
