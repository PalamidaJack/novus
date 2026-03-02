import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ListTodo,
  CheckCircle,
  Clock,
  XCircle,
  Loader2,
  Filter,
  Plus,
  RotateCcw,
  Ban,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { format } from 'date-fns';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { api } from '../utils/api';
import { cn } from '../utils/cn';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/Dialog';
import { toast } from 'sonner';
import type { TaskItem } from '../types';

const statusIcons: Record<string, any> = {
  pending: Clock,
  running: Loader2,
  completed: CheckCircle,
  failed: XCircle,
};

const statusColors: Record<string, string> = {
  pending: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
  running: 'bg-blue-500/10 text-blue-400 border-blue-500/20 animate-pulse',
  completed: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  failed: 'bg-red-500/10 text-red-400 border-red-500/20',
};

export function Tasks() {
  const [filter, setFilter] = useState('all');
  const [showNewTaskDialog, setShowNewTaskDialog] = useState(false);
  const [expandedTask, setExpandedTask] = useState<string | null>(null);
  const [newTask, setNewTask] = useState({
    description: '',
    priority: 'normal',
    capabilities: ['reasoning'],
    timeout_seconds: 60,
  });
  const queryClient = useQueryClient();

  const { data: tasks, isLoading } = useQuery<TaskItem[]>({
    queryKey: ['tasks'],
    queryFn: () => api.get('/tasks').then((r) => r.data),
    refetchInterval: 2000,
  });

  const createMutation = useMutation({
    mutationFn: (data: typeof newTask) => api.post('/tasks', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      setShowNewTaskDialog(false);
      setNewTask({ description: '', priority: 'normal', capabilities: ['reasoning'], timeout_seconds: 60 });
      toast.success('Task created');
    },
    onError: () => toast.error('Failed to create task'),
  });

  const cancelMutation = useMutation({
    mutationFn: (taskId: string) => api.post(`/tasks/${taskId}/cancel`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      toast.success('Task cancelled');
    },
    onError: () => toast.error('Failed to cancel task'),
  });

  const retryMutation = useMutation({
    mutationFn: (task: TaskItem) =>
      api.post('/tasks', { description: task.description, priority: 'normal', capabilities: ['reasoning'] }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      toast.success('Task retried');
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
      </div>
    );
  }

  const taskList = tasks || [];
  const filteredTasks = filter === 'all'
    ? taskList
    : taskList.filter((t) => t.status === filter);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">Tasks</h1>
          <p className="mt-2 text-gray-400">
            Monitor and manage task execution
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Filter className="h-5 w-5 text-gray-400" />
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="bg-gray-800 border border-gray-700 text-white rounded-lg px-4 py-2"
            >
              <option value="all">All Tasks</option>
              <option value="pending">Pending</option>
              <option value="running">Running</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
            </select>
          </div>
          <Button className="flex items-center gap-2" onClick={() => setShowNewTaskDialog(true)}>
            <Plus className="h-4 w-4" />
            New Task
          </Button>
        </div>
      </div>

      {/* New Task Dialog */}
      <Dialog open={showNewTaskDialog} onOpenChange={setShowNewTaskDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create New Task</DialogTitle>
            <DialogDescription>Submit a new task to the swarm for execution.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Description</label>
              <textarea
                value={newTask.description}
                onChange={(e) => setNewTask({ ...newTask, description: e.target.value })}
                placeholder="Describe the task..."
                rows={3}
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-emerald-500 resize-none"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Priority</label>
                <select
                  value={newTask.priority}
                  onChange={(e) => setNewTask({ ...newTask, priority: e.target.value })}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-emerald-500"
                >
                  <option value="critical">Critical</option>
                  <option value="high">High</option>
                  <option value="normal">Normal</option>
                  <option value="low">Low</option>
                  <option value="background">Background</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Timeout (s)</label>
                <input
                  type="number"
                  value={newTask.timeout_seconds}
                  onChange={(e) => setNewTask({ ...newTask, timeout_seconds: Number(e.target.value) })}
                  min={1}
                  max={300}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-emerald-500"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Capabilities</label>
              <div className="flex flex-wrap gap-2">
                {['reasoning', 'research', 'code', 'creative', 'analysis', 'verification', 'coordination'].map((cap) => (
                  <button
                    key={cap}
                    onClick={() =>
                      setNewTask((prev) => ({
                        ...prev,
                        capabilities: prev.capabilities.includes(cap)
                          ? prev.capabilities.filter((c) => c !== cap)
                          : [...prev.capabilities, cap],
                      }))
                    }
                    className={cn(
                      'px-3 py-1 text-xs rounded-full border transition-colors capitalize',
                      newTask.capabilities.includes(cap)
                        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                        : 'border-gray-700 text-gray-500'
                    )}
                  >
                    {cap}
                  </button>
                ))}
              </div>
            </div>
            <Button
              onClick={() => createMutation.mutate(newTask)}
              disabled={createMutation.isPending || !newTask.description.trim()}
              className="w-full"
            >
              {createMutation.isPending ? 'Creating...' : 'Submit Task'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {(['pending', 'running', 'completed', 'failed'] as const).map((status) => (
          <Card key={status} className="cursor-pointer" onClick={() => setFilter(status)}>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-400 capitalize">{status}</p>
                  <p className="text-2xl font-bold text-white">
                    {taskList.filter((t) => t.status === status).length}
                  </p>
                </div>
                {(() => {
                  const Icon = statusIcons[status];
                  return <Icon className={cn('h-6 w-6', status === 'running' && 'animate-spin')} />;
                })()}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Task List */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ListTodo className="h-5 w-5 text-emerald-500" />
            Task Queue ({filteredTasks.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {filteredTasks.map((task) => {
              const isExpanded = expandedTask === task.task_id;
              return (
                <div
                  key={task.task_id}
                  className="p-4 bg-gray-800/50 rounded-lg hover:bg-gray-800 transition-colors"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setExpandedTask(isExpanded ? null : task.task_id)}
                          className="text-gray-400 hover:text-white"
                        >
                          {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                        </button>
                        <p className="font-medium text-white truncate">{task.description}</p>
                      </div>
                      <div className="mt-2 ml-6 flex items-center gap-4 text-sm text-gray-400">
                        <span>ID: {task.task_id.slice(0, 8)}</span>
                        <span>
                          Created: {format(new Date(task.created_at), 'HH:mm:ss')}
                        </span>
                        {task.assigned_agent_id && (
                          <span>Agent: {task.assigned_agent_id.slice(0, 8)}</span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 ml-4">
                      {(task.status === 'pending' || task.status === 'running') && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => cancelMutation.mutate(task.task_id)}
                          className="text-red-400 hover:text-red-300"
                        >
                          <Ban className="h-4 w-4" />
                        </Button>
                      )}
                      {task.status === 'failed' && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => retryMutation.mutate(task)}
                          className="text-yellow-400 hover:text-yellow-300"
                        >
                          <RotateCcw className="h-4 w-4" />
                        </Button>
                      )}
                      <Badge
                        variant="outline"
                        className={statusColors[task.status]}
                      >
                        {task.status}
                      </Badge>
                    </div>
                  </div>

                  {/* Expanded detail */}
                  {isExpanded && (
                    <div className="mt-3 ml-6 p-3 bg-gray-900 rounded-lg space-y-2 text-sm">
                      <div><span className="text-gray-400">Full ID:</span> <span className="text-white font-mono text-xs">{task.task_id}</span></div>
                      {task.completed_at && (
                        <div><span className="text-gray-400">Completed:</span> <span className="text-white">{format(new Date(task.completed_at), 'HH:mm:ss')}</span></div>
                      )}
                      {task.assigned_agent_id && (
                        <div><span className="text-gray-400">Agent:</span> <span className="text-white font-mono text-xs">{task.assigned_agent_id}</span></div>
                      )}
                      {task.result && (
                        <div>
                          <span className="text-gray-400">Result:</span>
                          <pre className="mt-1 text-xs text-gray-300 bg-gray-800 p-2 rounded overflow-auto max-h-40">
                            {typeof task.result === 'string' ? task.result : JSON.stringify(task.result, null, 2)}
                          </pre>
                        </div>
                      )}
                      {task.error && (
                        <div><span className="text-red-400">Error:</span> <span className="text-red-300">{task.error}</span></div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}

            {filteredTasks.length === 0 && (
              <div className="text-center py-12 text-gray-500">
                No tasks found
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
