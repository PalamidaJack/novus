import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  FlaskConical,
  Gauge,
  Play,
  Loader2,
  CheckCircle,
  XCircle,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { ProgressBar } from '../components/ui/ProgressBar';
import { api } from '../utils/api';
import { cn } from '../utils/cn';
import type { EvalResponse, BenchmarkResponse } from '../types';

export function Evaluations() {
  const [evalResults, setEvalResults] = useState<EvalResponse | null>(null);
  const [benchResults, setBenchResults] = useState<BenchmarkResponse | null>(null);

  const evalMutation = useMutation({
    mutationFn: () => api.post('/eval/run').then((r) => r.data),
    onSuccess: (data) => setEvalResults(data),
  });

  const benchMutation = useMutation({
    mutationFn: () => api.post('/benchmark/run').then((r) => r.data),
    onSuccess: (data) => setBenchResults(data),
  });

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Evaluations</h1>
        <p className="mt-2 text-gray-400">Run evaluation suites and benchmarks against agents</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Eval Suite */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <FlaskConical className="h-5 w-5 text-emerald-500" />
                Evaluation Suite
              </CardTitle>
              <Button
                size="sm"
                onClick={() => evalMutation.mutate()}
                disabled={evalMutation.isPending}
                className="flex items-center gap-2"
              >
                {evalMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                Run
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {evalResults ? (
              <div className="space-y-4">
                {/* Summary */}
                <div className="grid grid-cols-3 gap-4 p-4 bg-gray-800/50 rounded-lg">
                  <div className="text-center">
                    <p className="text-sm text-gray-400">Suite</p>
                    <p className="text-white font-medium">{evalResults.suite}</p>
                  </div>
                  <div className="text-center">
                    <p className="text-sm text-gray-400">Total Tests</p>
                    <p className="text-white font-bold">{evalResults.total_tests}</p>
                  </div>
                  <div className="text-center">
                    <p className="text-sm text-gray-400">Pass Rate</p>
                    <p className={cn(
                      'font-bold',
                      evalResults.passed / evalResults.total_tests > 0.7 ? 'text-emerald-400' : 'text-red-400'
                    )}>
                      {((evalResults.passed / evalResults.total_tests) * 100).toFixed(0)}%
                    </p>
                  </div>
                </div>

                {/* Results Table */}
                <div className="space-y-2">
                  {evalResults.results.map((r) => (
                    <div key={r.test} className="flex items-center justify-between p-3 bg-gray-800/30 rounded-lg">
                      <div className="flex items-center gap-3 flex-1 min-w-0">
                        {r.passed ? (
                          <CheckCircle className="h-4 w-4 text-emerald-400 shrink-0" />
                        ) : (
                          <XCircle className="h-4 w-4 text-red-400 shrink-0" />
                        )}
                        <span className="text-sm text-white truncate">{r.test}</span>
                      </div>
                      <div className="flex items-center gap-4 ml-4">
                        <div className="w-24">
                          <ProgressBar
                            value={r.score * 100}
                            showValue={false}
                            color={r.passed ? 'emerald' : 'red'}
                          />
                        </div>
                        <span className="text-xs text-gray-400 w-16 text-right">{r.latency_ms.toFixed(0)}ms</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="text-center py-12 text-gray-500">
                {evalMutation.isPending ? 'Running evaluation...' : 'Click "Run" to start the evaluation suite'}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Benchmark Suite */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Gauge className="h-5 w-5 text-emerald-500" />
                Benchmark Suite
              </CardTitle>
              <Button
                size="sm"
                onClick={() => benchMutation.mutate()}
                disabled={benchMutation.isPending}
                className="flex items-center gap-2"
              >
                {benchMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                Run
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {benchResults ? (
              <div className="space-y-4">
                {/* Summary */}
                <div className="grid grid-cols-2 gap-4 p-4 bg-gray-800/50 rounded-lg">
                  <div className="text-center">
                    <p className="text-sm text-gray-400">Total Cases</p>
                    <p className="text-white font-bold">{benchResults.total}</p>
                  </div>
                  <div className="text-center">
                    <p className="text-sm text-gray-400">Pass Rate</p>
                    <p className={cn(
                      'font-bold',
                      benchResults.pass_rate > 0.7 ? 'text-emerald-400' : 'text-red-400'
                    )}>
                      {(benchResults.pass_rate * 100).toFixed(0)}%
                    </p>
                  </div>
                </div>

                {/* Results Table */}
                <div className="space-y-2">
                  {benchResults.results.map((r) => (
                    <div key={r.case_name} className="flex items-center justify-between p-3 bg-gray-800/30 rounded-lg">
                      <div className="flex items-center gap-3 flex-1 min-w-0">
                        {r.passed ? (
                          <CheckCircle className="h-4 w-4 text-emerald-400 shrink-0" />
                        ) : (
                          <XCircle className="h-4 w-4 text-red-400 shrink-0" />
                        )}
                        <span className="text-sm text-white truncate">{r.case_name}</span>
                        <Badge variant="secondary" className="text-xs shrink-0">{r.category}</Badge>
                      </div>
                      <span className="text-xs text-gray-400 ml-4">{r.latency_ms.toFixed(0)}ms</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="text-center py-12 text-gray-500">
                {benchMutation.isPending ? 'Running benchmark...' : 'Click "Run" to start the benchmark suite'}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
