import { useState } from 'react';
import {
  Settings2,
  Server,
  Cpu,
  Database,
  Shield,
  Bell,
  Save,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';

export function Settings() {
  const [settings, setSettings] = useState({
    apiPort: '8000',
    maxAgents: '10',
    enableEvolution: false,
    enableMetrics: true,
    logLevel: 'INFO',
    memoryLimit: '1024',
  });

  const handleSave = () => {
    // Save settings logic
    console.log('Saving settings:', settings);
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white">Settings</h1>
        <p className="mt-2 text-gray-400">
          Configure NOVUS platform settings
        </p>
      </div>

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
                onChange={(e) => setSettings({ ...settings, apiPort: e.target.value })}
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-emerald-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Log Level
              </label>
              <select
                value={settings.logLevel}
                onChange={(e) => setSettings({ ...settings, logLevel: e.target.value })}
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
                onChange={(e) => setSettings({ ...settings, maxAgents: e.target.value })}
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-emerald-500"
              />
            </div>
          </div>

          <div className="space-y-4">
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={settings.enableEvolution}
                onChange={(e) => setSettings({ ...settings, enableEvolution: e.target.checked })}
                className="w-5 h-5 rounded border-gray-600 text-emerald-500 focus:ring-emerald-500 bg-gray-800"
              />
              <span className="text-gray-300">Enable Evolutionary Optimization</span>
            </label>
            
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={settings.enableMetrics}
                onChange={(e) => setSettings({ ...settings, enableMetrics: e.target.checked })}
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
              onChange={(e) => setSettings({ ...settings, memoryLimit: e.target.value })}
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
