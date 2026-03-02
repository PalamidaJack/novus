import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Play,
  Square,
  Loader2,
  ChevronDown,
  ChevronRight,
  Plus,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/Dialog';
import { api } from '../utils/api';
import { toast } from 'sonner';
import type { BackgroundRun } from '../types';

const statusColors: Record<string, string> = {
  pending: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
  running: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  completed: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  failed: 'bg-red-500/10 text-red-400 border-red-500/20',
  cancelled: 'bg-gray-500/10 text-gray-400 border-gray-500/20',
};

export function BackgroundRuns() {
  const [showNewDialog, setShowNewDialog] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [expandedRun, setExpandedRun] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data: runs, isLoading } = useQuery<BackgroundRun[]>({
    queryKey: ['background-runs'],
    queryFn: () => api.get('/background-runs').then((r) => r.data),
    refetchInterval: 3000,
  });

  const submitMutation = useMutation({
    mutationFn: (prompt: string) => api.post('/background-runs', { prompt }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['background-runs'] });
      setShowNewDialog(false);
      setPrompt('');
      toast.success('Background run submitted');
    },
    onError: () => toast.error('Failed to submit run'),
  });

  const cancelMutation = useMutation({
    mutationFn: (taskId: string) => api.post(`/background-runs/${taskId}/cancel`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['background-runs'] });
      toast.success('Run cancelled');
    },
    onError: () => toast.error('Failed to cancel run'),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
      </div>
    );
  }

  const runList = runs || [];

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">Background Runs</h1>
          <p className="mt-2 text-gray-400">Long-running agent tasks executing in the background</p>
        </div>
        <Button className="flex items-center gap-2" onClick={() => setShowNewDialog(true)}>
          <Plus className="h-4 w-4" />
          New Run
        </Button>
      </div>

      {/* New Run Dialog */}
      <Dialog open={showNewDialog} onOpenChange={setShowNewDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New Background Run</DialogTitle>
            <DialogDescription>Submit a prompt for background execution by an agent.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Enter your prompt..."
              rows={5}
              className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500 resize-none"
            />
            <Button
              onClick={() => submitMutation.mutate(prompt)}
              disabled={submitMutation.isPending || !prompt.trim()}
              className="w-full"
            >
              {submitMutation.isPending ? 'Submitting...' : 'Submit Run'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Runs List */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Play className="h-5 w-5 text-emerald-500" />
            Runs ({runList.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {runList.map((run) => {
              const isExpanded = expandedRun === run.task_id;
              return (
                <div key={run.task_id} className="p-4 bg-gray-800/50 rounded-lg hover:bg-gray-800 transition-colors">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <button
                        onClick={() => setExpandedRun(isExpanded ? null : run.task_id)}
                        className="text-gray-400 hover:text-white"
                      >
                        {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                      </button>
                      <span className="text-sm font-mono text-gray-400">{run.task_id.slice(0, 8)}</span>
                      <span className="text-sm text-gray-300">{run.created_at}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {(run.status === 'pending' || run.status === 'running') && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => cancelMutation.mutate(run.task_id)}
                          className="text-red-400"
                        >
                          <Square className="h-4 w-4" />
                        </Button>
                      )}
                      <Badge variant="outline" className={statusColors[run.status] || statusColors.pending}>
                        {run.status}
                      </Badge>
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="mt-3 ml-7 p-3 bg-gray-900 rounded-lg space-y-2 text-sm">
                      <div><span className="text-gray-400">ID:</span> <span className="text-white font-mono text-xs">{run.task_id}</span></div>
                      <div><span className="text-gray-400">Created:</span> <span className="text-white">{run.created_at}</span></div>
                      <div><span className="text-gray-400">Updated:</span> <span className="text-white">{run.updated_at}</span></div>
                      {run.session_id && (
                        <div><span className="text-gray-400">Session:</span> <span className="text-white font-mono text-xs">{run.session_id}</span></div>
                      )}
                      {run.result && (
                        <div>
                          <span className="text-gray-400">Result:</span>
                          <pre className="mt-1 text-xs text-gray-300 bg-gray-800 p-2 rounded overflow-auto max-h-40 whitespace-pre-wrap">
                            {run.result}
                          </pre>
                        </div>
                      )}
                      {run.error && (
                        <div><span className="text-red-400">Error:</span> <span className="text-red-300">{run.error}</span></div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}

            {runList.length === 0 && (
              <div className="text-center py-12 text-gray-500">No background runs yet</div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
