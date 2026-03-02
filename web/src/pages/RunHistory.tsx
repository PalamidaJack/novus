import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  History,
  ChevronDown,
  ChevronRight,
  Download,
  ShieldCheck,
  Loader2,
  FileText,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { ProgressBar } from '../components/ui/ProgressBar';
import { api } from '../utils/api';
import { cn } from '../utils/cn';
import { toast } from 'sonner';
import type { RunSummary } from '../types';

export function RunHistory() {
  const [expandedSession, setExpandedSession] = useState<string | null>(null);
  const [summaries, setSummaries] = useState<Record<string, RunSummary>>({});
  const [traceGrades, setTraceGrades] = useState<Record<string, any>>({});

  const { data: sessions, isLoading } = useQuery<string[]>({
    queryKey: ['runs'],
    queryFn: () => api.get('/runs').then((r) => r.data),
  });

  const summaryMutation = useMutation({
    mutationFn: (sessionId: string) =>
      api.get(`/runs/${sessionId}/summary`).then((r) => r.data),
    onSuccess: (data) => setSummaries((prev) => ({ ...prev, [data.session_id]: data })),
  });

  const exportMutation = useMutation({
    mutationFn: (sessionId: string) => api.post(`/runs/${sessionId}/export`),
    onSuccess: () => toast.success('Run exported'),
    onError: () => toast.error('Export failed'),
  });

  const verifyMutation = useMutation({
    mutationFn: (sessionId: string) => api.post(`/runs/${sessionId}/verify`),
    onSuccess: (resp) => toast.success(resp.data.ok ? 'Verification passed' : 'Verification failed'),
    onError: () => toast.error('Verification failed'),
  });

  const gradeMutation = useMutation({
    mutationFn: (sessionId: string) =>
      api.get(`/runs/${sessionId}/trace-grade`).then((r) => r.data),
    onSuccess: (data) => setTraceGrades((prev) => ({ ...prev, [data.session_id]: data })),
  });

  const handleExpand = (sessionId: string) => {
    if (expandedSession === sessionId) {
      setExpandedSession(null);
      return;
    }
    setExpandedSession(sessionId);
    if (!summaries[sessionId]) {
      summaryMutation.mutate(sessionId);
    }
    if (!traceGrades[sessionId]) {
      gradeMutation.mutate(sessionId);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
      </div>
    );
  }

  const sessionList = sessions || [];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Run History</h1>
        <p className="mt-2 text-gray-400">Browse, replay, export, and verify past run sessions</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <History className="h-5 w-5 text-emerald-500" />
            Sessions ({sessionList.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {sessionList.map((sessionId) => {
              const isExpanded = expandedSession === sessionId;
              const summary = summaries[sessionId];
              const grade = traceGrades[sessionId];

              return (
                <div key={sessionId} className="p-4 bg-gray-800/50 rounded-lg">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <button
                        onClick={() => handleExpand(sessionId)}
                        className="text-gray-400 hover:text-white"
                      >
                        {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                      </button>
                      <FileText className="h-4 w-4 text-gray-400" />
                      <span className="text-sm font-mono text-white truncate">{sessionId}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button variant="ghost" size="sm" onClick={() => exportMutation.mutate(sessionId)}>
                        <Download className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => verifyMutation.mutate(sessionId)}>
                        <ShieldCheck className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="mt-3 ml-7 p-4 bg-gray-900 rounded-lg space-y-4">
                      {summaryMutation.isPending && !summary ? (
                        <div className="flex items-center gap-2 text-gray-400 text-sm">
                          <Loader2 className="h-4 w-4 animate-spin" /> Loading summary...
                        </div>
                      ) : summary ? (
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                          <div>
                            <p className="text-gray-400">Events</p>
                            <p className="text-white font-bold">{summary.total_events}</p>
                          </div>
                          <div>
                            <p className="text-gray-400">Turns</p>
                            <p className="text-white font-bold">{summary.turns}</p>
                          </div>
                          <div>
                            <p className="text-gray-400">Tool Calls</p>
                            <p className="text-white font-bold">{summary.tool_calls}</p>
                          </div>
                          <div>
                            <p className="text-gray-400">Errors</p>
                            <p className={cn('font-bold', summary.errors > 0 ? 'text-red-400' : 'text-emerald-400')}>{summary.errors}</p>
                          </div>
                          {summary.final_answer && (
                            <div className="col-span-full">
                              <p className="text-gray-400">Final Answer</p>
                              <p className="text-white text-xs mt-1 bg-gray-800 p-2 rounded">{summary.final_answer}</p>
                            </div>
                          )}
                        </div>
                      ) : null}

                      {grade && (
                        <div className="pt-3 border-t border-gray-800">
                          <div className="flex items-center gap-3 mb-2">
                            <span className="text-sm text-gray-400">Trace Grade</span>
                            <Badge variant={grade.passed ? 'default' : 'destructive'}>
                              {grade.passed ? 'Passed' : 'Failed'}
                            </Badge>
                          </div>
                          <ProgressBar
                            value={grade.score}
                            max={grade.max_score}
                            color={grade.passed ? 'emerald' : 'red'}
                          />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}

            {sessionList.length === 0 && (
              <div className="text-center py-12 text-gray-500">No run sessions found</div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
