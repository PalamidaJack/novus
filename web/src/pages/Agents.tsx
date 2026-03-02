import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Users,
  Activity,
  Zap,
  Brain,
  Code,
  Search,
  Sparkles,
  CheckCircle,
  Pause,
  Play,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { api } from '../utils/api';

const capabilityIcons = {
  reasoning: Brain,
  research: Search,
  code: Code,
  creative: Sparkles,
  analysis: Activity,
  verification: CheckCircle,
  coordination: Users,
};

const capabilityColors = {
  reasoning: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  research: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
  code: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  creative: 'bg-pink-500/10 text-pink-400 border-pink-500/20',
  analysis: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
  verification: 'bg-red-500/10 text-red-400 border-red-500/20',
  coordination: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
};

export function Agents() {
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  
  const { data: status, isLoading } = useQuery({
    queryKey: ['swarm-status'],
    queryFn: () => api.get('/swarm/status').then((r) => r.data),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500" />
      </div>
    );
  }

  const agents = Object.entries(status?.agents || {}).map(([id, info]: [string, any]) => ({
    id,
    ...info,
  }));

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
        <Button className="flex items-center gap-2">
          <Zap className="h-4 w-4" />
          Spawn Agent
        </Button>
      </div>

      {/* Agent Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <AnimatePresence>
          {agents.map((agent, index) => (
            <motion.div
              key={agent.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1 }}
            >
              <AgentCard
                agent={agent}
                isSelected={selectedAgent === agent.id}
                onClick={() => setSelectedAgent(agent.id)}
              />
            </motion.div>
          ))}
        </AnimatePresence>
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
                {(agents.reduce((acc, a) => acc + a.fitness, 0) / agents.length || 0).toFixed(2)}
              </p>
            </div>
            <div className="text-center p-4 bg-gray-800/50 rounded-lg">
              <p className="text-sm text-gray-400">Selection Pressure</p>
              <p className="text-3xl font-bold text-white mt-1">30%</p>
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
            const Icon = capabilityIcons[cap as keyof typeof capabilityIcons] || Brain;
            return (
              <Badge
                key={cap}
                variant="outline"
                className={cn(
                  'capitalize',
                  capabilityColors[cap as keyof typeof capabilityColors]
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

function cn(...classes: (string | boolean | undefined)[]) {
  return classes.filter(Boolean).join(' ');
}
