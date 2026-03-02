import { Link, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Users,
  ListTodo,
  Brain,
  MessageSquare,
  Settings,
  Zap,
  Globe,
  Play,
  History,
  FlaskConical,
  Shield,
} from 'lucide-react';
import { cn } from '../utils/cn';

interface LayoutProps {
  children: React.ReactNode;
}

const navSections = [
  {
    label: 'Core',
    items: [
      { name: 'Dashboard', href: '/', icon: LayoutDashboard },
      { name: 'Chat', href: '/chat', icon: MessageSquare },
      { name: 'Tasks', href: '/tasks', icon: ListTodo },
      { name: 'Agents', href: '/agents', icon: Users },
    ],
  },
  {
    label: 'Intelligence',
    items: [
      { name: 'Memory', href: '/memory', icon: Brain },
      { name: 'World Model', href: '/world-model', icon: Globe },
    ],
  },
  {
    label: 'Operations',
    items: [
      { name: 'Background Runs', href: '/background-runs', icon: Play },
      { name: 'Run History', href: '/run-history', icon: History },
      { name: 'Evaluations', href: '/evaluations', icon: FlaskConical },
    ],
  },
  {
    label: 'Safety & Config',
    items: [
      { name: 'Guardrails', href: '/guardrails', icon: Shield },
      { name: 'Settings', href: '/settings', icon: Settings },
    ],
  },
];

export function Layout({ children }: LayoutProps) {
  const location = useLocation();

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Sidebar */}
      <div className="fixed inset-y-0 left-0 w-64 bg-gray-900 border-r border-gray-800 flex flex-col">
        <div className="flex h-16 items-center px-6 border-b border-gray-800">
          <Zap className="h-8 w-8 text-emerald-500" />
          <span className="ml-3 text-xl font-bold text-white">NOVUS</span>
        </div>

        <nav className="flex-1 px-4 py-4 space-y-6 overflow-y-auto">
          {navSections.map((section) => (
            <div key={section.label}>
              <p className="px-4 mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">
                {section.label}
              </p>
              <div className="space-y-0.5">
                {section.items.map((item) => {
                  const Icon = item.icon;
                  const isActive = location.pathname === item.href;

                  return (
                    <Link
                      key={item.name}
                      to={item.href}
                      className={cn(
                        'flex items-center px-4 py-2.5 text-sm font-medium rounded-lg transition-colors',
                        isActive
                          ? 'bg-emerald-500/10 text-emerald-400'
                          : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                      )}
                    >
                      <Icon className={cn('h-4 w-4 mr-3', isActive && 'text-emerald-400')} />
                      {item.name}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        <div className="p-4 border-t border-gray-800">
          <div className="flex items-center px-4 py-2">
            <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="ml-2 text-sm text-gray-400">System Online</span>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="pl-64">
        <main className="p-8">
          {children}
        </main>
      </div>
    </div>
  );
}
