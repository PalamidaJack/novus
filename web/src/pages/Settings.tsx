import { useState, useEffect, useCallback } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  Cpu,
  Save,
  Key,
  Loader2,
  CheckCircle,
  AlertCircle,
  ChevronDown,
  Search,
  Sparkles,
  Shield,
  Terminal,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/Tabs';
import { Slider } from '../components/ui/Slider';
import { Toggle } from '../components/ui/Toggle';
import { api } from '../utils/api';
import { cn } from '../utils/cn';
import { toast } from 'sonner';
import type { SwarmConfig, ExecutionConfig, GuardrailRule } from '../types';

interface Provider {
  id: string;
  name: string;
  url: string;
}

interface ProviderModel {
  id: string;
  name: string;
  context_length: number | null;
}

export function Settings() {
  // Provider state
  const [providers, setProviders] = useState<Provider[]>([]);
  const [selectedProvider, setSelectedProvider] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [models, setModels] = useState<ProviderModel[]>([]);
  const [selectedModel, setSelectedModel] = useState('');
  const [loadingProviders, setLoadingProviders] = useState(true);
  const [loadingModels, setLoadingModels] = useState(false);
  const [modelError, setModelError] = useState('');
  const [modelSearchQuery, setModelSearchQuery] = useState('');
  const [modelsFetched, setModelsFetched] = useState(false);

  // Swarm config state
  const [swarmConfig, setSwarmConfig] = useState<SwarmConfig>({
    target_agent_count: 5,
    enable_evolution: false,
    mutation_rate: 0.1,
    consensus_threshold: 0.75,
    selection_pressure: 0.3,
  });

  // Execution config state
  const [execConfig, setExecConfig] = useState<ExecutionConfig>({
    sandbox_profile: 'standard',
    timeout_seconds: 300,
    enable_network: true,
    enable_computer_use: false,
  });

  // Guardrails state
  const [guardrailRules, setGuardrailRules] = useState<GuardrailRule[]>([]);

  // Fetch providers list on mount
  useEffect(() => {
    api.get('/providers')
      .then((r) => setProviders(r.data.providers))
      .catch(() => {
        setProviders([
          { id: 'openrouter', name: 'OpenRouter', url: 'https://openrouter.ai/api/v1/models' },
          { id: 'openai', name: 'OpenAI', url: 'https://api.openai.com/v1/models' },
          { id: 'kilo', name: 'Kilo Code', url: 'https://api.kilo.ai/api/gateway/models' },
          { id: 'anthropic', name: 'Anthropic', url: 'https://api.anthropic.com/v1/models' },
        ]);
      })
      .finally(() => setLoadingProviders(false));
  }, []);

  // Load swarm config
  useEffect(() => {
    api.get('/config/swarm').then((r) => setSwarmConfig(r.data)).catch(() => {});
  }, []);

  // Load execution config
  useEffect(() => {
    api.get('/config/execution').then((r) => setExecConfig(r.data)).catch(() => {});
  }, []);

  // Load guardrails config
  useEffect(() => {
    api.get('/config/guardrails').then((r) => setGuardrailRules(r.data.rules || [])).catch(() => {});
  }, []);

  // Reset model state when provider changes
  useEffect(() => {
    setModels([]);
    setSelectedModel('');
    setModelError('');
    setModelsFetched(false);
    setModelSearchQuery('');
  }, [selectedProvider]);

  const fetchModels = useCallback(async () => {
    if (!selectedProvider) return;
    setLoadingModels(true);
    setModelError('');
    setModels([]);
    setSelectedModel('');
    setModelsFetched(false);
    try {
      const resp = await api.post('/providers/models', {
        provider: selectedProvider,
        api_key: apiKey,
      });
      setModels(resp.data.models);
      setModelsFetched(true);
      if (resp.data.models.length === 0) {
        setModelError('No models returned by this provider.');
      }
    } catch (err: any) {
      setModelError(err.response?.data?.detail || err.message || 'Failed to fetch models');
    } finally {
      setLoadingModels(false);
    }
  }, [selectedProvider, apiKey]);

  const filteredModels = models.filter((m) => {
    if (!modelSearchQuery) return true;
    const q = modelSearchQuery.toLowerCase();
    return m.id.toLowerCase().includes(q) || m.name.toLowerCase().includes(q);
  });

  const currentProvider = providers.find((p) => p.id === selectedProvider);
  const currentModel = models.find((m) => m.id === selectedModel);

  const saveLlmMutation = useMutation({
    mutationFn: () => api.post('/config/llm', { provider: selectedProvider, api_key: apiKey, model: selectedModel }),
    onSuccess: () => toast.success('LLM config saved'),
    onError: () => toast.error('Failed to save LLM config'),
  });

  const saveSwarmMutation = useMutation({
    mutationFn: (config: SwarmConfig) => api.post('/config/swarm', config),
    onSuccess: () => toast.success('Swarm config saved'),
    onError: () => toast.error('Failed to save swarm config'),
  });

  const saveExecMutation = useMutation({
    mutationFn: (config: ExecutionConfig) => api.post('/config/execution', config),
    onSuccess: () => toast.success('Execution config saved'),
    onError: () => toast.error('Failed to save execution config'),
  });

  const saveGuardrailsMutation = useMutation({
    mutationFn: (rules: GuardrailRule[]) =>
      api.post('/config/guardrails', {
        rules: rules.map((r) => ({ name: r.name, enabled: r.enabled, action: r.action, severity: r.severity })),
      }),
    onSuccess: () => toast.success('Guardrails config saved'),
    onError: () => toast.error('Failed to save guardrails config'),
  });

  const severityColors: Record<string, string> = {
    low: 'text-gray-400',
    medium: 'text-yellow-400',
    high: 'text-orange-400',
    critical: 'text-red-400',
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white">Settings</h1>
        <p className="mt-2 text-gray-400">Configure NOVUS platform settings</p>
      </div>

      <Tabs defaultValue="llm">
        <TabsList>
          <TabsTrigger value="llm">LLM Provider</TabsTrigger>
          <TabsTrigger value="swarm">Swarm Config</TabsTrigger>
          <TabsTrigger value="execution">Execution</TabsTrigger>
          <TabsTrigger value="guardrails">Guardrails</TabsTrigger>
        </TabsList>

        {/* Tab 1: LLM Provider */}
        <TabsContent value="llm">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-emerald-500" />
                LLM Provider
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Provider Selector */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Provider</label>
                {loadingProviders ? (
                  <div className="flex items-center gap-2 text-gray-400 text-sm">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Loading providers...
                  </div>
                ) : (
                  <div className="relative">
                    <select
                      value={selectedProvider}
                      onChange={(e) => setSelectedProvider(e.target.value)}
                      className="w-full appearance-none px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-emerald-500 cursor-pointer"
                    >
                      <option value="">Select a provider...</option>
                      {providers.map((p) => (
                        <option key={p.id} value={p.id}>{p.name}</option>
                      ))}
                    </select>
                    <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 pointer-events-none" />
                  </div>
                )}
                {currentProvider && (
                  <p className="mt-2 text-xs text-gray-500">API: {currentProvider.url}</p>
                )}
              </div>

              {/* API Key */}
              {selectedProvider && (
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    <span className="flex items-center gap-2"><Key className="h-4 w-4" /> API Key</span>
                  </label>
                  <div className="flex gap-3">
                    <div className="flex-1 relative">
                      <input
                        type={showApiKey ? 'text' : 'password'}
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        placeholder={`Enter your ${currentProvider?.name} API key...`}
                        className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500 pr-20"
                      />
                      <button
                        type="button"
                        onClick={() => setShowApiKey(!showApiKey)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 hover:text-white transition-colors"
                      >
                        {showApiKey ? 'Hide' : 'Show'}
                      </button>
                    </div>
                    <Button onClick={fetchModels} disabled={loadingModels} className="flex items-center gap-2 whitespace-nowrap">
                      {loadingModels ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                      Fetch Models
                    </Button>
                  </div>
                </div>
              )}

              {/* Error */}
              {modelError && (
                <div className="flex items-start gap-3 p-4 bg-red-500/10 border border-red-500/20 rounded-lg">
                  <AlertCircle className="h-5 w-5 text-red-400 flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-red-400">{modelError}</p>
                </div>
              )}

              {/* Model Selector */}
              {modelsFetched && models.length > 0 && (
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Model <span className="ml-2 text-xs text-gray-500">({models.length} available)</span>
                  </label>
                  {models.length > 10 && (
                    <div className="relative mb-3">
                      <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                      <input
                        type="text"
                        value={modelSearchQuery}
                        onChange={(e) => setModelSearchQuery(e.target.value)}
                        placeholder="Filter models..."
                        className="w-full pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500 text-sm"
                      />
                    </div>
                  )}
                  <div className="relative">
                    <select
                      value={selectedModel}
                      onChange={(e) => setSelectedModel(e.target.value)}
                      className="w-full appearance-none px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-emerald-500 cursor-pointer"
                    >
                      <option value="">Select a model...</option>
                      {filteredModels.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.name}{m.context_length ? ` (${(m.context_length / 1000).toFixed(0)}k ctx)` : ''}
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 pointer-events-none" />
                  </div>
                  {currentModel && (
                    <div className="mt-3 p-4 bg-gray-800/50 rounded-lg border border-gray-700">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-white">{currentModel.name}</p>
                          <p className="mt-1 text-xs text-gray-400 font-mono">{currentModel.id}</p>
                        </div>
                        <div className="flex items-center gap-2">
                          {currentModel.context_length && (
                            <Badge variant="outline">{(currentModel.context_length / 1000).toFixed(0)}k context</Badge>
                          )}
                          <CheckCircle className="h-5 w-5 text-emerald-500" />
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              <div className="flex justify-end">
                <Button
                  onClick={() => saveLlmMutation.mutate()}
                  disabled={saveLlmMutation.isPending || !selectedProvider}
                  className="flex items-center gap-2"
                >
                  {saveLlmMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  Save LLM Config
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 2: Swarm Config */}
        <TabsContent value="swarm">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Cpu className="h-5 w-5 text-emerald-500" />
                Swarm Configuration
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <Slider
                label="Target Agent Count"
                value={swarmConfig.target_agent_count}
                onChange={(v) => setSwarmConfig({ ...swarmConfig, target_agent_count: v })}
                min={1}
                max={50}
              />
              <Toggle
                label="Enable Evolution"
                description="Allow the swarm to evolve agents over time through selection and mutation"
                checked={swarmConfig.enable_evolution}
                onChange={(v) => setSwarmConfig({ ...swarmConfig, enable_evolution: v })}
              />
              <Slider
                label="Mutation Rate"
                value={swarmConfig.mutation_rate}
                onChange={(v) => setSwarmConfig({ ...swarmConfig, mutation_rate: v })}
                min={0}
                max={1}
                step={0.01}
              />
              <Slider
                label="Consensus Threshold"
                value={swarmConfig.consensus_threshold}
                onChange={(v) => setSwarmConfig({ ...swarmConfig, consensus_threshold: v })}
                min={0}
                max={1}
                step={0.05}
              />
              <Slider
                label="Selection Pressure"
                value={swarmConfig.selection_pressure}
                onChange={(v) => setSwarmConfig({ ...swarmConfig, selection_pressure: v })}
                min={0}
                max={1}
                step={0.05}
                suffix=""
              />
              <div className="flex justify-end">
                <Button
                  onClick={() => saveSwarmMutation.mutate(swarmConfig)}
                  disabled={saveSwarmMutation.isPending}
                  className="flex items-center gap-2"
                >
                  {saveSwarmMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  Save Swarm Config
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 3: Execution */}
        <TabsContent value="execution">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Terminal className="h-5 w-5 text-emerald-500" />
                Execution Environment
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Sandbox Profile</label>
                <div className="relative">
                  <select
                    value={execConfig.sandbox_profile}
                    onChange={(e) => setExecConfig({ ...execConfig, sandbox_profile: e.target.value as any })}
                    className="w-full appearance-none px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-emerald-500 cursor-pointer"
                  >
                    <option value="restricted">Restricted</option>
                    <option value="standard">Standard</option>
                    <option value="permissive">Permissive</option>
                  </select>
                  <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 pointer-events-none" />
                </div>
              </div>
              <Slider
                label="Timeout"
                value={execConfig.timeout_seconds}
                onChange={(v) => setExecConfig({ ...execConfig, timeout_seconds: v })}
                min={10}
                max={3600}
                step={10}
                suffix="s"
              />
              <Toggle
                label="Enable Network Access"
                description="Allow agents to make outbound network requests"
                checked={execConfig.enable_network}
                onChange={(v) => setExecConfig({ ...execConfig, enable_network: v })}
              />
              <Toggle
                label="Enable Computer Use"
                description="Allow agents to control mouse, keyboard, and screenshots"
                checked={execConfig.enable_computer_use}
                onChange={(v) => setExecConfig({ ...execConfig, enable_computer_use: v })}
              />
              <div className="flex justify-end">
                <Button
                  onClick={() => saveExecMutation.mutate(execConfig)}
                  disabled={saveExecMutation.isPending}
                  className="flex items-center gap-2"
                >
                  {saveExecMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  Save Execution Config
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 4: Guardrails */}
        <TabsContent value="guardrails">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Shield className="h-5 w-5 text-emerald-500" />
                Guardrail Rules
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {guardrailRules.length === 0 ? (
                <p className="text-gray-500 text-center py-8">No guardrail rules configured</p>
              ) : (
                guardrailRules.map((rule, i) => (
                  <div key={rule.name} className="p-4 bg-gray-800/50 rounded-lg flex items-center justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <div className={cn(
                          'h-2 w-2 rounded-full',
                          rule.enabled ? 'bg-emerald-500' : 'bg-gray-600'
                        )} />
                        <span className="text-sm font-medium text-white">{rule.name}</span>
                        <Badge variant="outline" className="text-xs">{rule.type}</Badge>
                        <span className={cn('text-xs font-medium', severityColors[rule.severity])}>
                          {rule.severity}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <select
                        value={rule.action}
                        onChange={(e) => {
                          const updated = [...guardrailRules];
                          updated[i] = { ...rule, action: e.target.value as any };
                          setGuardrailRules(updated);
                        }}
                        className="px-2 py-1 bg-gray-700 border border-gray-600 rounded text-white text-xs"
                      >
                        <option value="block">Block</option>
                        <option value="warn">Warn</option>
                        <option value="truncate">Truncate</option>
                        <option value="redact">Redact</option>
                      </select>
                      <button
                        onClick={() => {
                          const updated = [...guardrailRules];
                          updated[i] = { ...rule, enabled: !rule.enabled };
                          setGuardrailRules(updated);
                        }}
                        className={cn(
                          'relative inline-flex h-5 w-9 shrink-0 rounded-full border-2 border-transparent transition-colors',
                          rule.enabled ? 'bg-emerald-500' : 'bg-gray-700'
                        )}
                      >
                        <span className={cn(
                          'pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transform transition-transform',
                          rule.enabled ? 'translate-x-4' : 'translate-x-0'
                        )} />
                      </button>
                    </div>
                  </div>
                ))
              )}
              {guardrailRules.length > 0 && (
                <div className="flex justify-end">
                  <Button
                    onClick={() => saveGuardrailsMutation.mutate(guardrailRules)}
                    disabled={saveGuardrailsMutation.isPending}
                    className="flex items-center gap-2"
                  >
                    {saveGuardrailsMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                    Save Guardrails
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
