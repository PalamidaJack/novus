import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  Globe,
  Play,
  Loader2,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { api } from '../utils/api';
import type { WorldModelStats, PlanResponse } from '../types';

export function WorldModel() {
  const [initialState, setInitialState] = useState('{\n  \n}');
  const [goalState, setGoalState] = useState('{\n  \n}');
  const [maxSteps, setMaxSteps] = useState(10);
  const [planResult, setPlanResult] = useState<PlanResponse | null>(null);
  const [jsonError, setJsonError] = useState('');

  const { data: stats, isLoading: statsLoading } = useQuery<WorldModelStats>({
    queryKey: ['world-model-stats'],
    queryFn: () => api.get('/world-model/stats').then((r) => r.data),
  });

  const planMutation = useMutation({
    mutationFn: (data: { initial_state: any; goal_state: any; max_plan_length: number }) =>
      api.post('/world-model/plan', data).then((r) => r.data),
    onSuccess: (data) => setPlanResult(data),
  });

  const handlePlan = () => {
    setJsonError('');
    try {
      const initial = JSON.parse(initialState);
      const goal = JSON.parse(goalState);
      planMutation.mutate({ initial_state: initial, goal_state: goal, max_plan_length: maxSteps });
    } catch {
      setJsonError('Invalid JSON in initial or goal state');
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">World Model</h1>
        <p className="mt-2 text-gray-400">JEPA-inspired world model for planning and simulation</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {[
          { label: 'States', value: stats?.total_states ?? 0 },
          { label: 'Transitions', value: stats?.total_transitions ?? 0 },
          { label: 'Rules', value: stats?.rules_count ?? 0 },
        ].map((stat) => (
          <Card key={stat.label}>
            <CardContent className="p-6 text-center">
              <p className="text-sm text-gray-400">{stat.label}</p>
              <p className="text-3xl font-bold text-white mt-2">
                {statsLoading ? '...' : stat.value}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Planning Form */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Globe className="h-5 w-5 text-emerald-500" />
            Plan Generation
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Initial State (JSON)</label>
              <textarea
                value={initialState}
                onChange={(e) => setInitialState(e.target.value)}
                rows={6}
                className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white font-mono text-sm focus:outline-none focus:border-emerald-500 resize-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Goal State (JSON)</label>
              <textarea
                value={goalState}
                onChange={(e) => setGoalState(e.target.value)}
                rows={6}
                className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white font-mono text-sm focus:outline-none focus:border-emerald-500 resize-none"
              />
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Max Steps</label>
              <input
                type="number"
                value={maxSteps}
                onChange={(e) => setMaxSteps(Number(e.target.value))}
                min={1}
                max={50}
                className="w-24 px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-emerald-500"
              />
            </div>
            <div className="flex-1" />
            <Button
              onClick={handlePlan}
              disabled={planMutation.isPending}
              className="flex items-center gap-2"
            >
              {planMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              Generate Plan
            </Button>
          </div>

          {jsonError && (
            <p className="text-sm text-red-400">{jsonError}</p>
          )}
          {planMutation.isError && (
            <p className="text-sm text-red-400">Planning failed. Check your inputs.</p>
          )}
        </CardContent>
      </Card>

      {/* Plan Results */}
      {planResult && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>Plan Result</span>
              <Badge variant={planResult.best_score > 0.5 ? 'default' : 'destructive'}>
                Score: {planResult.best_score.toFixed(2)}
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {/* Steps Timeline */}
            <div className="space-y-0">
              {planResult.best_plan.map((step, i) => (
                <div key={i} className="flex items-start gap-4">
                  <div className="flex flex-col items-center">
                    <div className="h-8 w-8 rounded-full bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 text-sm font-bold">
                      {i + 1}
                    </div>
                    {i < planResult.best_plan.length - 1 && (
                      <div className="w-px h-8 bg-gray-700" />
                    )}
                  </div>
                  <div className="pb-6 flex-1">
                    <p className="text-sm font-medium text-white">
                      {step.action || JSON.stringify(step)}
                    </p>
                    {Object.entries(step).filter(([k]) => k !== 'action').length > 0 && (
                      <pre className="mt-1 text-xs text-gray-400 bg-gray-800/50 p-2 rounded">
                        {JSON.stringify(Object.fromEntries(Object.entries(step).filter(([k]) => k !== 'action')), null, 2)}
                      </pre>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {planResult.alternatives.length > 0 && (
              <div className="mt-4 pt-4 border-t border-gray-800">
                <p className="text-sm text-gray-400 mb-2">
                  {planResult.alternatives.length} alternative plan(s) available
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
