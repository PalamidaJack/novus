// Shared TypeScript interfaces for the NOVUS dashboard

export interface Agent {
  id: string;
  agent_id?: string;
  name: string;
  status: string;
  active_tasks: number;
  fitness: number;
  capabilities?: string[];
}

export interface TaskItem {
  task_id: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  created_at: string;
  completed_at?: string;
  assigned_agent_id?: string;
  result?: any;
  error?: string;
}

export interface SwarmStatus {
  population: number;
  generation: number;
  pending_tasks: number;
  active_tasks: number;
  completed_tasks: number;
  agents: Agent[];
}

export interface SwarmConfig {
  target_agent_count: number;
  enable_evolution: boolean;
  mutation_rate: number;
  consensus_threshold: number;
  selection_pressure: number;
}

export interface ExecutionConfig {
  sandbox_profile: 'standard' | 'restricted' | 'permissive';
  timeout_seconds: number;
  enable_network: boolean;
  enable_computer_use: boolean;
}

export interface GuardrailRule {
  name: string;
  type: string;
  enabled: boolean;
  action: 'block' | 'warn' | 'truncate' | 'redact';
  severity: 'low' | 'medium' | 'high' | 'critical';
}

export interface GuardrailsConfig {
  stats: {
    total_rules: number;
    enabled_rules: number;
    rules_by_type: Record<string, number>;
  };
  rules: GuardrailRule[];
}

export interface MemoryStats {
  total_entries: number;
  episodic: number;
  semantic: number;
  procedural: number;
  embeddings: number;
  tags: number;
}

export interface MemorySearchResult {
  content: string;
  memory_type: string;
  relevance_score: number;
  retrieval_method: string;
  created_at: string | null;
}

export interface BackgroundRun {
  task_id: string;
  status: string;
  created_at: string;
  updated_at: string;
  result?: string;
  error?: string;
  session_id?: string;
}

export interface RunSummary {
  session_id: string;
  total_events: number;
  turns: number;
  tool_calls: number;
  errors: number;
  final_answer?: string;
}

export interface EvalResultItem {
  test: string;
  passed: boolean;
  score: number;
  latency_ms: number;
}

export interface EvalResponse {
  suite: string;
  total_tests: number;
  passed: number;
  results: EvalResultItem[];
}

export interface BenchmarkItem {
  case_name: string;
  category: string;
  passed: boolean;
  latency_ms: number;
}

export interface BenchmarkResponse {
  pass_rate: number;
  total: number;
  results: BenchmarkItem[];
}

export interface WorldModelStats {
  total_states: number;
  total_transitions: number;
  rules_count: number;
  [key: string]: any;
}

export interface PlanStep {
  action: string;
  [key: string]: any;
}

export interface PlanResponse {
  best_plan: PlanStep[];
  best_score: number;
  alternatives: any[];
}
