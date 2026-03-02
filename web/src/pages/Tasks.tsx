import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ListTodo,
  CheckCircle,
  Clock,
  XCircle,
  Loader2,
  Filter,
} from 'lucide-react';
import { format } from 'date-fns';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { api } from '../utils/api';

const statusIcons = {
  pending: Clock,
  running: Loader2,
  completed: CheckCircle,
  failed: XCircle,
};

const statusColors = {
  pending: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
  running: 'bg-blue-500/10 text-blue-400 border-blue-500/20 animate-pulse',
  completed: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  failed: 'bg-red-500/10 text-red-400 border-red-500/20',
};

export function Tasks() {
  const [filter, setFilter] = useState('all');
  
  const { data: tasks, isLoading } = useQuery({
    queryKey: ['tasks'],
    queryFn: () => api.get('/tasks').then((r) => r.data),
    refetchInterval: 2000,
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
    : taskList.filter((t: any) => t.status === filter);

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
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {['pending', 'running', 'completed', 'failed'].map((status) => (
          <Card key={status} className="cursor-pointer" onClick={() => setFilter(status)}>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-400 capitalize">{status}</p>
                  <p className="text-2xl font-bold text-white">
                    {taskList.filter((t: any) => t.status === status).length}
                  </p>
                </div>
                {(() => {
                  const Icon = statusIcons[status as keyof typeof statusIcons];
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
          <div className="space-y-4">
            {filteredTasks.map((task: any) => (
              <div
                key={task.id}
                className="p-4 bg-gray-800/50 rounded-lg hover:bg-gray-800 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <p className="font-medium text-white">{task.description}</p>
                    <div className="mt-2 flex items-center gap-4 text-sm text-gray-400">
                      <span>ID: {task.id.slice(0, 8)}</span>
                      <span>
                        Created: {format(new Date(task.created_at), 'HH:mm:ss')}
                      </span>
                      {task.assigned_agent_id && (
                        <span>Agent: {task.assigned_agent_id.slice(0, 8)}</span>
                      )}
                    </div>
                  </div>
                  <Badge
                    variant="outline"
                    className={statusColors[task.status as keyof typeof statusColors]}
                  >
                    {task.status}
                  </Badge>
                </div>
              </div>
            ))}
            
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

function cn(...classes: (string | boolean | undefined)[]) {
  return classes.filter(Boolean).join(' ');
}
