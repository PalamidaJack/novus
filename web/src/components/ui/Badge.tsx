import { forwardRef } from 'react';
import { cn } from '../../utils/cn';

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'secondary' | 'outline' | 'destructive';
}

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant = 'default', ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={cn(
          'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors',
          {
            'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20': variant === 'default',
            'bg-gray-800 text-gray-300': variant === 'secondary',
            'border border-gray-700 text-gray-300': variant === 'outline',
            'bg-red-500/10 text-red-400 border border-red-500/20': variant === 'destructive',
          },
          className
        )}
        {...props}
      />
    );
  }
);
Badge.displayName = 'Badge';
