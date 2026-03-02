# NOVUS Onboarding System

## Quick Start for New Users

### Interactive CLI Onboarding

```bash
# First time setup
novus init

# Interactive configuration
novus setup --interactive
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

# Or use novus config
novus config set openai.api_key "sk-..."
```

### Step 3: Initialize Knowledge Base

```bash
# Add documents
novus knowledge add ./docs/
novus knowledge add-url https://docs.example.com

# Verify
novus knowledge list
```

### Step 4: Test Setup

```bash
# Run diagnostics
novus doctor

# Test agent
novus test --agent basic --prompt "Hello, can you help me?"

# Test swarm
novus test --swarm --problem "What is 15 * 23?"
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

### 1. Simple Task
```bash
novus task "Summarize the benefits of Python"
```

### 2. Code Task
```bash
novus code "Write a function to calculate fibonacci"
```

### 3. Research Task
```bash
novus research "Latest developments in quantum computing"
```

### 4. Swarm Task
```bash
novus swarm "Design a database schema for an e-commerce site"
```

---

## Verification Checklist

- [ ] Configuration files created
- [ ] API keys configured
- [ ] At least one agent tested
- [ ] Knowledge base initialized (optional)
- [ ] Safety settings reviewed
- [ ] First successful task completed

---

## Getting Help

```bash
# General help
novus --help

# Command help
novus task --help

# Check status
novus status

# View logs
novus logs --tail 100
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
