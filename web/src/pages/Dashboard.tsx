import { useRef, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  Users,
  CheckCircle,
  Clock,
  Brain,
  Cpu,
  Zap,
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { ProgressBar } from '../components/ui/ProgressBar';
import { api } from '../utils/api';
import { cn } from '../utils/cn';
import { useWebSocket } from '../hooks/useWebSocket';
import type { SwarmStatus } from '../types';

const MAX_CHART_POINTS = 20;

interface ChartPoint {
  time: string;
  tasks: number;
  agents: number;
}

export function Dashboard() {
  const chartBuffer = useRef<ChartPoint[]>([]);
  const eventLog = useRef<{ type: string; detail: string; ts: number }[]>([]);

  const { data: status, isLoading } = useQuery<SwarmStatus>({
    queryKey: ['swarm-status'],
    queryFn: () => api.get('/swarm/status').then((r) => r.data),
  });

  const { data: memStats } = useQuery({
    queryKey: ['memory-stats'],
    queryFn: () => api.get('/memory/stats').then((r) => r.data),
  });

  const { lastMessage } = useWebSocket();

  // Track WebSocket events for the activity feed
  useEffect(() => {
    if (!lastMessage) return;
    eventLog.current = [
      { type: lastMessage.type, detail: JSON.stringify(lastMessage.data).slice(0, 80), ts: lastMessage.timestamp },
      ...eventLog.current,
    ].slice(0, 10);
  }, [lastMessage]);

  // Build ring-buffer time series from polling
  useEffect(() => {
    if (!status) return;
    const now = new Date();
    const timeStr = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;
    chartBuffer.current = [
      ...chartBuffer.current,
      { time: timeStr, tasks: status.completed_tasks, agents: status.population },
    ].slice(-MAX_CHART_POINTS);
  }, [status]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500" />
      </div>
    );
  }

  const chartData = chartBuffer.current.length > 1
    ? chartBuffer.current
    : [{ time: 'now', tasks: status?.completed_tasks || 0, agents: status?.population || 0 }];

  const totalMemEntries = memStats?.total_entries ?? 0;
  const memMax = 10000;
  const memPct = memMax > 0 ? (totalMemEntries / memMax) * 100 : 0;
  const agentLoad = status ? (status.active_tasks / Math.max(status.population, 1)) * 100 : 0;
  const pendingRatio = status ? (status.pending_tasks / Math.max(status.completed_tasks + status.pending_tasks, 1)) * 100 : 0;

  const stats = [
    {
      title: 'Active Agents',
      value: status?.population || 0,
      change: `${status?.active_tasks || 0} busy`,
      icon: Users,
      trend: 'up' as const,
    },
    {
      title: 'Tasks Completed',
      value: status?.completed_tasks || 0,
      change: `Gen ${status?.generation || 0}`,
      icon: CheckCircle,
      trend: 'up' as const,
    },
    {
      title: 'Pending Tasks',
      value: status?.pending_tasks || 0,
      change: status?.pending_tasks ? 'Processing' : 'Idle',
      icon: Clock,
      trend: 'neutral' as const,
    },
    {
      title: 'Active Tasks',
      value: status?.active_tasks || 0,
      change: `${status?.population || 0} agents online`,
      icon: Activity,
      trend: 'neutral' as const,
    },
  ];

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white">Dashboard</h1>
        <p className="mt-2 text-gray-400">
          Real-time overview of your NOVUS swarm
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.title}>
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-400">{stat.title}</p>
                    <p className="mt-2 text-3xl font-bold text-white">{stat.value}</p>
                    <p className={cn(
                      'mt-1 text-sm',
                      stat.trend === 'up' && 'text-emerald-400',
                      stat.trend === 'up' && 'text-emerald-400',
                      stat.trend === 'neutral' && 'text-gray-400'
                    )}>
                      {stat.change}
                    </p>
                  </div>
                  <div className="p-3 bg-gray-800 rounded-lg">
                    <Icon className="h-6 w-6 text-emerald-500" />
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-emerald-500" />
              Task Processing
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="colorTasks" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis dataKey="time" stroke="#9ca3af" />
                  <YAxis stroke="#9ca3af" />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#1f2937', border: 'none' }}
                    labelStyle={{ color: '#9ca3af' }}
                  />
                  <Area
                    type="monotone"
                    dataKey="tasks"
                    stroke="#10b981"
                    fillOpacity={1}
                    fill="url(#colorTasks)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Cpu className="h-5 w-5 text-emerald-500" />
              Agent Population
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis dataKey="time" stroke="#9ca3af" />
                  <YAxis stroke="#9ca3af" />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#1f2937', border: 'none' }}
                    labelStyle={{ color: '#9ca3af' }}
                  />
                  <Line
                    type="monotone"
                    dataKey="agents"
                    stroke="#10b981"
                    strokeWidth={2}
                    dot={{ fill: '#10b981' }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* System Health */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Brain className="h-5 w-5 text-emerald-500" />
              System Health
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-6">
              <ProgressBar
                label="Memory Usage"
                value={memPct}
                color={memPct > 80 ? 'red' : memPct > 60 ? 'yellow' : 'emerald'}
              />
              <ProgressBar
                label="Agent Load"
                value={agentLoad}
                color={agentLoad > 80 ? 'red' : agentLoad > 50 ? 'yellow' : 'emerald'}
              />
              <ProgressBar
                label="Pending Backlog"
                value={pendingRatio}
                color={pendingRatio > 50 ? 'red' : pendingRatio > 25 ? 'yellow' : 'emerald'}
              />
            </div>
          </CardContent>
        </Card>

        {/* Recent Activity */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="h-5 w-5 text-emerald-500" />
              Recent Activity
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3 max-h-64 overflow-y-auto">
              {eventLog.current.length === 0 ? (
                <p className="text-sm text-gray-500 text-center py-4">Waiting for events...</p>
              ) : (
                eventLog.current.map((evt, i) => (
                  <div key={`${evt.ts}-${i}`} className="flex items-start gap-3 p-2 rounded-lg bg-gray-800/50">
                    <div className="h-2 w-2 mt-1.5 rounded-full bg-emerald-500 shrink-0" />
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-gray-300 truncate">{evt.type}</p>
                      <p className="text-xs text-gray-500 truncate">{evt.detail}</p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
