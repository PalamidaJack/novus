# NOVUS Onboarding System

## Quick Start for New Users

### Interactive CLI Onboarding

```bash
# First time setup
novus onboard
```

### What Gets Configured

1. **Identity** - Who you are, your preferences
2. **System** - Agent capabilities, memory settings
3. **Connections** - API keys, integrations
4. **Safety** - Guardrails, approval settings

---

## Manual Onboarding Flow

### Step 1: Create Identity Files

Create `~/.novus/identity.yaml`:

```yaml
user:
  name: "Your Name"
  email: "your@email.com"
  timezone: "UTC"
  
preferences:
  communication_style: "direct"  # direct, detailed, casual
  code_style: "clean"  # clean, documented, minimal
  risk_tolerance: "medium"  # low, medium, high
  
safety:
  require_approval_for:
    - code_execution
    - network_calls
    - file_deletion
  auto_approve_below_cost: 0.10  # dollars
```

### Step 2: Configure API Keys

```bash
# Set environment variables
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Step 3: Test Setup

```bash
# Run diagnostics
novus doctor

# Swarm smoke test
novus swarm --problem "What is 15 * 23?" --agents 3

# Full local readiness pipeline
novus readiness --output-dir .novus-bench
```

---

## File Structure After Onboarding

```
~/.novus/
├── config.yaml           # Main configuration
├── identity.yaml         # User identity
├── api-keys.yaml         # API credentials (encrypted)
├── knowledge/            # Knowledge bases
│   └── default/
├── logs/                 # Execution logs
├── cache/                # LLM cache
└── sessions/             # Session history
```

---

## First Tasks to Try

### 1. Swarm Reasoning
```bash
novus swarm --problem "Summarize the benefits of Python" --agents 3
```

### 2. Planning
```bash
novus plan --goal '{"done": true}' --initial '{"done": false}'
```

### 3. API Server
```bash
novus start --port 8000
```

### 4. Runtime Artifacts
```bash
novus replay <session_id>
novus export-run <session_id>
novus verify-run <session_id>
```

---

## Verification Checklist

- [ ] Configuration files created
- [ ] API keys configured
- [ ] Swarm smoke test completed
- [ ] Readiness pipeline completed
- [ ] Safety settings reviewed
- [ ] Benchmark artifacts generated

---

## Getting Help

```bash
# General help
novus --help

# Command help
novus swarm --help

# Check status
novus status

# Run diagnostics
novus doctor
```

---

## Next Steps

1. **Explore Features**: Try different agent types
2. **Customize**: Adjust settings for your workflow
3. **Integrate**: Connect to your tools (Slack, GitHub, etc.)
4. **Build**: Create custom agents for your domain
5. **Scale**: Deploy for team use

---

*Welcome to NOVUS. Your agents are ready.*
