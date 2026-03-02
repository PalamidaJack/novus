import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Users,
  Activity,
  Zap,
  Brain,
  Code,
  Search,
  Sparkles,
  CheckCircle,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { api } from '../utils/api';
import { cn } from '../utils/cn';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/Dialog';
import { toast } from 'sonner';
import type { SwarmStatus, SwarmConfig } from '../types';

const capabilityIcons: Record<string, any> = {
  reasoning: Brain,
  research: Search,
  code: Code,
  creative: Sparkles,
  analysis: Activity,
  verification: CheckCircle,
  coordination: Users,
};

const capabilityColors: Record<string, string> = {
  reasoning: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  research: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
  code: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  creative: 'bg-pink-500/10 text-pink-400 border-pink-500/20',
  analysis: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
  verification: 'bg-red-500/10 text-red-400 border-red-500/20',
  coordination: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
};

const ALL_CAPABILITIES = ['reasoning', 'research', 'code', 'creative', 'analysis', 'verification', 'coordination'];

export function Agents() {
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [showSpawnDialog, setShowSpawnDialog] = useState(false);
  const [spawnName, setSpawnName] = useState('NewAgent');
  const [spawnCaps, setSpawnCaps] = useState<string[]>(['reasoning']);
  const queryClient = useQueryClient();

  const { data: status, isLoading } = useQuery<SwarmStatus>({
    queryKey: ['swarm-status'],
    queryFn: () => api.get('/swarm/status').then((r) => r.data),
  });

  const { data: swarmConfig } = useQuery<SwarmConfig>({
    queryKey: ['swarm-config'],
    queryFn: () => api.get('/config/swarm').then((r) => r.data),
  });

  const spawnMutation = useMutation({
    mutationFn: (data: { name: string; capabilities: string[] }) =>
      api.post('/swarm/spawn', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['swarm-status'] });
      setShowSpawnDialog(false);
      setSpawnName('NewAgent');
      setSpawnCaps(['reasoning']);
      toast.success('Agent spawned successfully');
    },
    onError: () => toast.error('Failed to spawn agent'),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500" />
      </div>
    );
  }

  const agents = (status?.agents || []).map((info: any) => ({
    id: info.agent_id || info.id,
    ...info,
  }));

  const selected = selectedAgent ? agents.find((a: any) => a.id === selectedAgent) : null;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">Agents</h1>
          <p className="mt-2 text-gray-400">
            Manage and monitor your agent swarm
          </p>
        </div>
        <Button className="flex items-center gap-2" onClick={() => setShowSpawnDialog(true)}>
          <Zap className="h-4 w-4" />
          Spawn Agent
        </Button>
      </div>

      {/* Spawn Dialog */}
      <Dialog open={showSpawnDialog} onOpenChange={setShowSpawnDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Spawn New Agent</DialogTitle>
            <DialogDescription>Configure and deploy a new agent into the swarm.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Agent Name</label>
              <input
                type="text"
                value={spawnName}
                onChange={(e) => setSpawnName(e.target.value)}
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-emerald-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Capabilities</label>
              <div className="flex flex-wrap gap-2">
                {ALL_CAPABILITIES.map((cap) => (
                  <button
                    key={cap}
                    onClick={() =>
                      setSpawnCaps((prev) =>
                        prev.includes(cap) ? prev.filter((c) => c !== cap) : [...prev, cap]
                      )
                    }
                    className={cn(
                      'px-3 py-1.5 text-xs rounded-full border transition-colors capitalize',
                      spawnCaps.includes(cap)
                        ? capabilityColors[cap]
                        : 'border-gray-700 text-gray-500'
                    )}
                  >
                    {cap}
                  </button>
                ))}
              </div>
            </div>
            <Button
              onClick={() => spawnMutation.mutate({ name: spawnName, capabilities: spawnCaps })}
              disabled={spawnMutation.isPending || !spawnName.trim() || spawnCaps.length === 0}
              className="w-full"
            >
              {spawnMutation.isPending ? 'Spawning...' : 'Spawn Agent'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Agent Grid */}
        <div className={cn('space-y-6', selected ? 'lg:col-span-2' : 'lg:col-span-3')}>
          <div className={cn('grid gap-6', selected ? 'grid-cols-1 md:grid-cols-2' : 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3')}>
            <AnimatePresence>
              {agents.map((agent: any, index: number) => (
                <motion.div
                  key={agent.id}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.05 }}
                >
                  <AgentCard
                    agent={agent}
                    isSelected={selectedAgent === agent.id}
                    onClick={() => setSelectedAgent(selectedAgent === agent.id ? null : agent.id)}
                  />
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>

        {/* Agent Detail Panel */}
        {selected && (
          <Card className="lg:col-span-1">
            <CardHeader>
              <CardTitle>Agent Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <p className="text-sm text-gray-400">Name</p>
                <p className="text-white font-medium">{selected.name}</p>
              </div>
              <div>
                <p className="text-sm text-gray-400">Full ID</p>
                <p className="text-white font-mono text-xs break-all">{selected.id}</p>
              </div>
              <div>
                <p className="text-sm text-gray-400">Status</p>
                <Badge variant={selected.status === 'busy' ? 'default' : 'secondary'} className="mt-1">
                  {selected.status}
                </Badge>
              </div>
              <div>
                <p className="text-sm text-gray-400">Capabilities</p>
                <div className="flex flex-wrap gap-1 mt-1">
                  {(selected.capabilities || ['reasoning']).map((cap: string) => (
                    <Badge key={cap} variant="outline" className={cn('capitalize text-xs', capabilityColors[cap])}>
                      {cap}
                    </Badge>
                  ))}
                </div>
              </div>
              <div>
                <p className="text-sm text-gray-400">Active Tasks</p>
                <p className="text-white">{selected.active_tasks}</p>
              </div>
              <div>
                <p className="text-sm text-gray-400">Fitness Score</p>
                <p className={cn(
                  'text-2xl font-bold',
                  selected.fitness > 0.7 ? 'text-emerald-400' :
                  selected.fitness > 0.4 ? 'text-yellow-400' : 'text-red-400'
                )}>
                  {selected.fitness.toFixed(3)}
                </p>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Evolution Status */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5 text-emerald-500" />
            Evolution Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div className="text-center p-4 bg-gray-800/50 rounded-lg">
              <p className="text-sm text-gray-400">Generation</p>
              <p className="text-3xl font-bold text-white mt-1">
                {status?.generation || 0}
              </p>
            </div>
            <div className="text-center p-4 bg-gray-800/50 rounded-lg">
              <p className="text-sm text-gray-400">Population</p>
              <p className="text-3xl font-bold text-white mt-1">
                {status?.population || 0}
              </p>
            </div>
            <div className="text-center p-4 bg-gray-800/50 rounded-lg">
              <p className="text-sm text-gray-400">Avg Fitness</p>
              <p className="text-3xl font-bold text-emerald-400 mt-1">
                {(agents.reduce((acc: number, a: any) => acc + (a.fitness || 0), 0) / Math.max(agents.length, 1)).toFixed(2)}
              </p>
            </div>
            <div className="text-center p-4 bg-gray-800/50 rounded-lg">
              <p className="text-sm text-gray-400">Selection Pressure</p>
              <p className="text-3xl font-bold text-white mt-1">
                {((swarmConfig?.selection_pressure ?? 0.3) * 100).toFixed(0)}%
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

interface AgentCardProps {
  agent: {
    id: string;
    name: string;
    status: string;
    active_tasks: number;
    fitness: number;
    capabilities?: string[];
  };
  isSelected: boolean;
  onClick: () => void;
}

function AgentCard({ agent, isSelected, onClick }: AgentCardProps) {
  const isActive = agent.status === 'busy';
  const capabilities = agent.capabilities || ['reasoning', 'analysis'];

  return (
    <Card
      className={cn(
        'cursor-pointer transition-all duration-200 hover:border-emerald-500/50',
        isSelected && 'border-emerald-500 ring-1 ring-emerald-500'
      )}
      onClick={onClick}
    >
      <CardContent className="p-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="relative">
              <div className="h-12 w-12 rounded-full bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center">
                <span className="text-lg font-bold text-white">
                  {agent.name.charAt(0).toUpperCase()}
                </span>
              </div>
              <div
                className={cn(
                  'absolute -bottom-1 -right-1 h-4 w-4 rounded-full border-2 border-gray-900',
                  isActive ? 'bg-emerald-500 animate-pulse' : 'bg-gray-500'
                )}
              />
            </div>
            <div>
              <h3 className="font-semibold text-white">{agent.name}</h3>
              <p className="text-sm text-gray-400">{agent.id.slice(0, 8)}...</p>
            </div>
          </div>
          <Badge
            variant={isActive ? 'default' : 'secondary'}
            className={cn(
              isActive && 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
            )}
          >
            {agent.status}
          </Badge>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {capabilities.slice(0, 3).map((cap) => {
            const Icon = capabilityIcons[cap] || Brain;
            return (
              <Badge
                key={cap}
                variant="outline"
                className={cn(
                  'capitalize',
                  capabilityColors[cap]
                )}
              >
                <Icon className="h-3 w-3 mr-1" />
                {cap}
              </Badge>
            );
          })}
        </div>

        <div className="mt-4 pt-4 border-t border-gray-800">
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2 text-gray-400">
              <Activity className="h-4 w-4" />
              <span>{agent.active_tasks} active tasks</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-gray-400">Fitness:</span>
              <span className={cn(
                'font-medium',
                agent.fitness > 0.7 ? 'text-emerald-400' :
                agent.fitness > 0.4 ? 'text-yellow-400' :
                'text-red-400'
              )}>
                {agent.fitness.toFixed(2)}
              </span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
