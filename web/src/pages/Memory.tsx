import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Brain,
  Database,
  Clock,
  Sparkles,
  Search,
  Zap,
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';

const mockMemoryData = [
  { time: '00:00', episodic: 120, semantic: 80, procedural: 45 },
  { time: '04:00', episodic: 145, semantic: 85, procedural: 48 },
  { time: '08:00', episodic: 180, semantic: 95, procedural: 52 },
  { time: '12:00', episodic: 220, semantic: 110, procedural: 58 },
  { time: '16:00', episodic: 245, semantic: 125, procedural: 62 },
  { time: '20:00', episodic: 280, semantic: 140, procedural: 68 },
];

export function Memory() {
  const [activeTab, setActiveTab] = useState('overview');

  const stats = [
    { label: 'Total Entries', value: '10,247', icon: Database, color: 'text-blue-400' },
    { label: 'Episodic', value: '5,832', icon: Clock, color: 'text-purple-400' },
    { label: 'Semantic', value: '3,120', icon: Brain, color: 'text-emerald-400' },
    { label: 'Generative', value: '1,295', icon: Sparkles, color: 'text-pink-400' },
  ];

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white">Memory</h1>
        <p className="mt-2 text-gray-400">
          Monitor and explore the unified memory system
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.label}>
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-gray-400">{stat.label}</p>
                    <p className={cn('mt-2 text-3xl font-bold', stat.color)}>
                      {stat.value}
                    </p>
                  </div>
                  <div className="p-3 bg-gray-800 rounded-lg">
                    <Icon className={cn('h-6 w-6', stat.color)} />
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Memory Growth Chart */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-emerald-500" />
            Memory Growth Over Time
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={mockMemoryData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="time" stroke="#9ca3af" />
                <YAxis stroke="#9ca3af" />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1f2937', border: 'none' }}
                  labelStyle={{ color: '#9ca3af' }}
                />
                <Line
                  type="monotone"
                  dataKey="episodic"
                  name="Episodic"
                  stroke="#a855f7"
                  strokeWidth={2}
                />
                <Line
                  type="monotone"
                  dataKey="semantic"
                  name="Semantic"
                  stroke="#10b981"
                  strokeWidth={2}
                />
                <Line
                  type="monotone"
                  dataKey="procedural"
                  name="Procedural"
                  stroke="#3b82f6"
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* Memory Search */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Search className="h-5 w-5 text-emerald-500" />
            Memory Explorer
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-4">
            <input
              type="text"
              placeholder="Search memories..."
              className="flex-1 px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500"
            />
            <button className="px-6 py-3 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg font-medium transition-colors flex items-center gap-2">
              <Zap className="h-4 w-4" />
              Search
            </button>
          </div>

          <div className="mt-6 space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="p-4 bg-gray-800/50 rounded-lg">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm text-white">
                      Task execution experience: Successfully analyzed data from 3 sources...
                    </p>
                    <div className="mt-2 flex items-center gap-3">
                      <Badge variant="outline" className="bg-purple-500/10 text-purple-400 border-purple-500/20">
                        Episodic
                      </Badge>
                      <span className="text-xs text-gray-500">
                        Accessed: 2 hours ago
                      </span>
                    </div>
                  </div>
                  <span className="text-xs text-gray-500">Score: 0.89</span>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function cn(...classes: (string | boolean | undefined)[]) {
  return classes.filter(Boolean).join(' ');
}
