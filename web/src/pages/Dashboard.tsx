import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  Users,
  CheckCircle,
  Clock,
  TrendingUp,
  Cpu,
  Brain,
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from './ui/Card';
import { api } from '../utils/api';

const mockMetricsData = [
  { time: '00:00', tasks: 12, agents: 5 },
  { time: '04:00', tasks: 18, agents: 5 },
  { time: '08:00', tasks: 45, agents: 7 },
  { time: '12:00', tasks: 78, agents: 8 },
  { time: '16:00', tasks: 92, agents: 10 },
  { time: '20:00', tasks: 65, agents: 10 },
  { time: '23:59', tasks: 34, agents: 10 },
];

export function Dashboard() {
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

  const stats = [
    {
      title: 'Active Agents',
      value: status?.population || 0,
      change: '+2 this hour',
      icon: Users,
      trend: 'up',
    },
    {
      title: 'Tasks Completed',
      value: status?.completed_tasks || 0,
      change: '+12 today',
      icon: CheckCircle,
      trend: 'up',
    },
    {
      title: 'Pending Tasks',
      value: status?.pending_tasks || 0,
      change: 'Processing',
      icon: Clock,
      trend: 'neutral',
    },
    {
      title: 'Avg Task Time',
      value: '2.4s',
      change: '-15% vs yesterday',
      icon: Activity,
      trend: 'down',
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
                      stat.trend === 'down' && 'text-emerald-400',
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
                <AreaChart data={mockMetricsData}>
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
                <LineChart data={mockMetricsData}>
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

      {/* System Health */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-emerald-500" />
            System Health
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">Memory Usage</span>
                <span className="text-sm font-medium text-white">64%</span>
              </div>
              <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                <div className="h-full w-64 bg-emerald-500 rounded-full" />
              </div>
            </div>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">CPU Usage</span>
                <span className="text-sm font-medium text-white">42%</span>
              </div>
              <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                <div className="h-full w-42 bg-emerald-500 rounded-full" />
              </div>
            </div>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">API Latency</span>
                <span className="text-sm font-medium text-white">24ms</span>
              </div>
              <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                <div className="h-full w-24 bg-emerald-500 rounded-full" />
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function cn(...classes: (string | boolean | undefined)[]) {
  return classes.filter(Boolean).join(' ');
}
