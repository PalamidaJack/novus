import { useQuery } from '@tanstack/react-query';
import {
  Shield,
  ShieldCheck,
  ShieldAlert,
  Loader2,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { api } from '../utils/api';
import { cn } from '../utils/cn';
import type { GuardrailsConfig } from '../types';

const severityColors: Record<string, { dot: string; text: string; bg: string }> = {
  low: { dot: 'bg-gray-400', text: 'text-gray-400', bg: 'bg-gray-500/10' },
  medium: { dot: 'bg-yellow-400', text: 'text-yellow-400', bg: 'bg-yellow-500/10' },
  high: { dot: 'bg-orange-400', text: 'text-orange-400', bg: 'bg-orange-500/10' },
  critical: { dot: 'bg-red-400', text: 'text-red-400', bg: 'bg-red-500/10' },
};

export function Guardrails() {
  const { data, isLoading } = useQuery<GuardrailsConfig>({
    queryKey: ['guardrails-config'],
    queryFn: () => api.get('/config/guardrails').then((r) => r.data),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
      </div>
    );
  }

  const stats = data?.stats;
  const rules = data?.rules || [];

  const rulesByType: Record<string, typeof rules> = {};
  rules.forEach((r) => {
    const t = r.type || 'custom';
    if (!rulesByType[t]) rulesByType[t] = [];
    rulesByType[t].push(r);
  });

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Guardrails</h1>
        <p className="mt-2 text-gray-400">Safety rules, content moderation, and policy enforcement</p>
      </div>

      {/* Overview Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card>
          <CardContent className="p-6 text-center">
            <Shield className="h-8 w-8 text-emerald-500 mx-auto" />
            <p className="text-sm text-gray-400 mt-2">Total Rules</p>
            <p className="text-3xl font-bold text-white mt-1">{stats?.total_rules ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-6 text-center">
            <ShieldCheck className="h-8 w-8 text-emerald-500 mx-auto" />
            <p className="text-sm text-gray-400 mt-2">Enabled</p>
            <p className="text-3xl font-bold text-emerald-400 mt-1">{stats?.enabled_rules ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-6 text-center">
            <ShieldAlert className="h-8 w-8 text-yellow-500 mx-auto" />
            <p className="text-sm text-gray-400 mt-2">Disabled</p>
            <p className="text-3xl font-bold text-yellow-400 mt-1">
              {(stats?.total_rules ?? 0) - (stats?.enabled_rules ?? 0)}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* By-Type Breakdown */}
      {stats?.rules_by_type && Object.keys(stats.rules_by_type).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Rules by Type</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-3">
              {Object.entries(stats.rules_by_type).map(([type, count]) => (
                <div key={type} className="px-4 py-2 bg-gray-800/50 rounded-lg">
                  <span className="text-sm text-gray-400">{type}</span>
                  <span className="ml-2 text-sm font-bold text-white">{count as number}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Rule Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {rules.map((rule) => {
          const sev = severityColors[rule.severity] || severityColors.medium;
          return (
            <Card key={rule.name} className={cn(
              'transition-all',
              !rule.enabled && 'opacity-50'
            )}>
              <CardContent className="p-5">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div className={cn('h-2.5 w-2.5 rounded-full', rule.enabled ? 'bg-emerald-500' : 'bg-gray-600')} />
                    <h3 className="text-sm font-semibold text-white">{rule.name}</h3>
                  </div>
                  <Badge variant={rule.enabled ? 'default' : 'secondary'} className="text-xs">
                    {rule.enabled ? 'Active' : 'Inactive'}
                  </Badge>
                </div>

                <div className="flex items-center gap-2 mb-3">
                  <Badge variant="outline" className="text-xs">{rule.type}</Badge>
                  <span className={cn('text-xs font-medium capitalize', sev.text)}>{rule.severity}</span>
                </div>

                <div className="flex items-center justify-between pt-3 border-t border-gray-800">
                  <span className="text-xs text-gray-400">Action</span>
                  <Badge
                    variant="outline"
                    className={cn(
                      'text-xs capitalize',
                      rule.action === 'block' && 'border-red-500/30 text-red-400',
                      rule.action === 'warn' && 'border-yellow-500/30 text-yellow-400',
                      rule.action === 'redact' && 'border-purple-500/30 text-purple-400',
                      rule.action === 'truncate' && 'border-blue-500/30 text-blue-400',
                    )}
                  >
                    {rule.action}
                  </Badge>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {rules.length === 0 && (
        <Card>
          <CardContent className="p-12 text-center">
            <Shield className="h-12 w-12 text-gray-600 mx-auto" />
            <p className="mt-4 text-gray-500">No guardrail rules configured</p>
            <p className="mt-1 text-sm text-gray-600">Rules will appear here when the guardrails engine initializes with default policies.</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
