import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  Brain,
  Database,
  Clock,
  Sparkles,
  Search,
  Zap,
  Loader2,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Tabs, TabsList, TabsTrigger } from '../components/ui/Tabs';
import { api } from '../utils/api';
import { cn } from '../utils/cn';
import type { MemoryStats, MemorySearchResult } from '../types';

const typeColors: Record<string, string> = {
  episodic: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
  semantic: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  procedural: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  generative: 'bg-pink-500/10 text-pink-400 border-pink-500/20',
};

export function Memory() {
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');

  const { data: stats, isLoading: statsLoading } = useQuery<MemoryStats>({
    queryKey: ['memory-stats'],
    queryFn: () => api.get('/memory/stats').then((r) => r.data),
  });

  const searchMutation = useMutation({
    mutationFn: (query: string) =>
      api.post('/memory/search', {
        query,
        memory_types: typeFilter === 'all' ? null : [typeFilter],
        k: 20,
      }).then((r) => r.data),
  });

  const handleSearch = () => {
    if (!searchQuery.trim()) return;
    searchMutation.mutate(searchQuery);
  };

  const statCards = [
    { label: 'Total Entries', value: stats?.total_entries ?? 0, icon: Database, color: 'text-blue-400' },
    { label: 'Episodic', value: stats?.episodic ?? 0, icon: Clock, color: 'text-purple-400' },
    { label: 'Semantic', value: stats?.semantic ?? 0, icon: Brain, color: 'text-emerald-400' },
    { label: 'Procedural', value: stats?.procedural ?? 0, icon: Sparkles, color: 'text-pink-400' },
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
        {statCards.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.label}>
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-gray-400">{stat.label}</p>
                    <p className={cn('mt-2 text-3xl font-bold', stat.color)}>
                      {statsLoading ? '...' : stat.value.toLocaleString()}
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

      {/* Memory Search */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Search className="h-5 w-5 text-emerald-500" />
            Memory Explorer
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Type Filter Tabs */}
          <Tabs value={typeFilter} onValueChange={setTypeFilter}>
            <TabsList>
              <TabsTrigger value="all">All</TabsTrigger>
              <TabsTrigger value="episodic">Episodic</TabsTrigger>
              <TabsTrigger value="semantic">Semantic</TabsTrigger>
              <TabsTrigger value="procedural">Procedural</TabsTrigger>
            </TabsList>
          </Tabs>

          {/* Search Input */}
          <div className="flex gap-4">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="Search memories..."
              className="flex-1 px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500"
            />
            <Button
              onClick={handleSearch}
              disabled={searchMutation.isPending || !searchQuery.trim()}
              className="flex items-center gap-2"
            >
              {searchMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Zap className="h-4 w-4" />
              )}
              Search
            </Button>
          </div>

          {/* Search Results */}
          <div className="space-y-3">
            {searchMutation.data?.results?.map((result: MemorySearchResult, i: number) => (
              <div key={i} className="p-4 bg-gray-800/50 rounded-lg">
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-white">{result.content}</p>
                    <div className="mt-2 flex items-center gap-3">
                      <Badge variant="outline" className={typeColors[result.memory_type] || 'border-gray-700 text-gray-400'}>
                        {result.memory_type}
                      </Badge>
                      <span className="text-xs text-gray-500">
                        via {result.retrieval_method}
                      </span>
                      {result.created_at && (
                        <span className="text-xs text-gray-500">
                          {new Date(result.created_at).toLocaleString()}
                        </span>
                      )}
                    </div>
                  </div>
                  <span className="text-xs text-gray-500 ml-4 shrink-0">
                    Score: {result.relevance_score.toFixed(2)}
                  </span>
                </div>
              </div>
            ))}

            {searchMutation.data?.results?.length === 0 && (
              <div className="text-center py-8 text-gray-500">No memories found</div>
            )}

            {!searchMutation.data && !searchMutation.isPending && (
              <div className="text-center py-8 text-gray-500">
                Enter a search query to explore memories
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
