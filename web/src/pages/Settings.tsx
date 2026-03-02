import { useState, useEffect, useCallback } from 'react';
import {
  Server,
  Cpu,
  Database,
  Save,
  Key,
  Loader2,
  CheckCircle,
  AlertCircle,
  ChevronDown,
  Search,
  Sparkles,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { api } from '../utils/api';

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

function cn(...classes: (string | boolean | undefined)[]) {
  return classes.filter(Boolean).join(' ');
}

export function Settings() {
  const [settings, setSettings] = useState({
    apiPort: '8000',
    maxAgents: '10',
    enableEvolution: false,
    enableMetrics: true,
    logLevel: 'INFO',
    memoryLimit: '1024',
  });

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

  // Fetch providers list on mount
  useEffect(() => {
    api
      .get('/providers')
      .then((r) => {
        setProviders(r.data.providers);
      })
      .catch(() => {
        // Fallback provider list if the backend endpoint isn't available yet
        setProviders([
          { id: 'openrouter', name: 'OpenRouter', url: 'https://openrouter.ai/api/v1/models' },
          { id: 'openai', name: 'OpenAI', url: 'https://api.openai.com/v1/models' },
          { id: 'kilo', name: 'Kilo Code', url: 'https://api.kilo.ai/api/gateway/models' },
          { id: 'anthropic', name: 'Anthropic', url: 'https://api.anthropic.com/v1/models' },
        ]);
      })
      .finally(() => setLoadingProviders(false));
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
      const detail =
        err.response?.data?.detail || err.message || 'Failed to fetch models';
      setModelError(detail);
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

  const handleSave = () => {
    const config = {
      ...settings,
      provider: selectedProvider,
      model: selectedModel,
      // API key intentionally not logged
    };
    console.log('Saving settings:', config);
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white">Settings</h1>
        <p className="mt-2 text-gray-400">Configure NOVUS platform settings</p>
      </div>

      {/* LLM Provider Configuration */}
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
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Provider
            </label>
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
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 pointer-events-none" />
              </div>
            )}
            {currentProvider && (
              <p className="mt-2 text-xs text-gray-500">
                API: {currentProvider.url}
              </p>
            )}
          </div>

          {/* API Key */}
          {selectedProvider && (
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                <span className="flex items-center gap-2">
                  <Key className="h-4 w-4" />
                  API Key
                </span>
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
                <Button
                  onClick={fetchModels}
                  disabled={loadingModels}
                  className="flex items-center gap-2 whitespace-nowrap"
                >
                  {loadingModels ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Search className="h-4 w-4" />
                  )}
                  Fetch Models
                </Button>
              </div>
              <p className="mt-2 text-xs text-gray-500">
                {selectedProvider === 'kilo'
                  ? 'Kilo Code models can be listed without a key, but a key is required for inference.'
                  : 'Your key is sent only to the provider API and is never stored on the server.'}
              </p>
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
                Model
                <span className="ml-2 text-xs text-gray-500">
                  ({models.length} available)
                </span>
              </label>

              {/* Search filter */}
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
                  size={1}
                >
                  <option value="">Select a model...</option>
                  {filteredModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                      {m.context_length
                        ? ` (${(m.context_length / 1000).toFixed(0)}k ctx)`
                        : ''}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 pointer-events-none" />
              </div>

              {/* Selected model details */}
              {currentModel && (
                <div className="mt-3 p-4 bg-gray-800/50 rounded-lg border border-gray-700">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-white">
                        {currentModel.name}
                      </p>
                      <p className="mt-1 text-xs text-gray-400 font-mono">
                        {currentModel.id}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {currentModel.context_length && (
                        <Badge variant="outline">
                          {(currentModel.context_length / 1000).toFixed(0)}k
                          context
                        </Badge>
                      )}
                      <CheckCircle className="h-5 w-5 text-emerald-500" />
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* General Settings */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Server className="h-5 w-5 text-emerald-500" />
            General Settings
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                API Port
              </label>
              <input
                type="text"
                value={settings.apiPort}
                onChange={(e) =>
                  setSettings({ ...settings, apiPort: e.target.value })
                }
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-emerald-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Log Level
              </label>
              <select
                value={settings.logLevel}
                onChange={(e) =>
                  setSettings({ ...settings, logLevel: e.target.value })
                }
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-emerald-500"
              >
                <option>DEBUG</option>
                <option>INFO</option>
                <option>WARNING</option>
                <option>ERROR</option>
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Swarm Settings */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cpu className="h-5 w-5 text-emerald-500" />
            Swarm Configuration
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Maximum Agents
              </label>
              <input
                type="number"
                value={settings.maxAgents}
                onChange={(e) =>
                  setSettings({ ...settings, maxAgents: e.target.value })
                }
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-emerald-500"
              />
            </div>
          </div>

          <div className="space-y-4">
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={settings.enableEvolution}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    enableEvolution: e.target.checked,
                  })
                }
                className="w-5 h-5 rounded border-gray-600 text-emerald-500 focus:ring-emerald-500 bg-gray-800"
              />
              <span className="text-gray-300">
                Enable Evolutionary Optimization
              </span>
            </label>

            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={settings.enableMetrics}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    enableMetrics: e.target.checked,
                  })
                }
                className="w-5 h-5 rounded border-gray-600 text-emerald-500 focus:ring-emerald-500 bg-gray-800"
              />
              <span className="text-gray-300">Enable Prometheus Metrics</span>
            </label>
          </div>
        </CardContent>
      </Card>

      {/* Memory Settings */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Database className="h-5 w-5 text-emerald-500" />
            Memory Configuration
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Memory Limit (MB)
            </label>
            <input
              type="number"
              value={settings.memoryLimit}
              onChange={(e) =>
                setSettings({ ...settings, memoryLimit: e.target.value })
              }
              className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-emerald-500"
            />
            <p className="mt-2 text-sm text-gray-500">
              Maximum memory usage per agent
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Save Button */}
      <div className="flex justify-end">
        <Button
          onClick={handleSave}
          className="flex items-center gap-2 px-6"
        >
          <Save className="h-4 w-4" />
          Save Settings
        </Button>
      </div>
    </div>
  );
}
