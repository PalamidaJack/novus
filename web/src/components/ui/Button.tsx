import { forwardRef } from 'react';
import { cn } from '../../utils/cn';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'secondary' | 'ghost' | 'outline';
  size?: 'default' | 'sm' | 'lg';
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'default', size = 'default', ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          'inline-flex items-center justify-center rounded-lg font-medium transition-colors',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500',
          'disabled:pointer-events-none disabled:opacity-50',
          {
            'bg-emerald-500 text-white hover:bg-emerald-600': variant === 'default',
            'bg-gray-800 text-gray-100 hover:bg-gray-700': variant === 'secondary',
            'hover:bg-gray-800 hover:text-gray-100': variant === 'ghost',
            'border border-gray-700 bg-transparent hover:bg-gray-800': variant === 'outline',
            'h-10 px-4 py-2': size === 'default',
            'h-8 px-3 text-sm': size === 'sm',
            'h-12 px-6 text-lg': size === 'lg',
          },
          className
        )}
        {...props}
      />
    );
  }
);
Button.displayName = 'Button';
