import { forwardRef } from 'react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type BadgeVariant = 'default' | 'success' | 'warning' | 'error' | 'info' | 'primary';

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  size?: 'sm' | 'md';
  dot?: boolean;
}

const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant = 'default', size = 'md', dot = false, children, ...props }, ref) => {
    const baseStyles =
      'inline-flex items-center gap-1.5 font-medium rounded-full transition-colors';

    const variants: Record<BadgeVariant, string> = {
      default: 'bg-bg-tertiary text-text-secondary',
      primary: 'bg-kuasarr-primary/20 text-kuasarr-primary-light border border-kuasarr-primary/30',
      success: 'bg-kuasarr-success/20 text-kuasarr-success border border-kuasarr-success/30',
      warning: 'bg-kuasarr-warning/20 text-kuasarr-warning border border-kuasarr-warning/30',
      error: 'bg-kuasarr-error/20 text-kuasarr-error border border-kuasarr-error/30',
      info: 'bg-kuasarr-secondary/20 text-kuasarr-secondary border border-kuasarr-secondary/30',
    };

    const sizes = {
      sm: 'px-2 py-0.5 text-xs',
      md: 'px-2.5 py-1 text-sm',
    };

    const dotColors: Record<BadgeVariant, string> = {
      default: 'bg-text-secondary',
      primary: 'bg-kuasarr-primary-light',
      success: 'bg-kuasarr-success',
      warning: 'bg-kuasarr-warning',
      error: 'bg-kuasarr-error',
      info: 'bg-kuasarr-secondary',
    };

    return (
      <span
        ref={ref}
        className={cn(baseStyles, variants[variant], sizes[size], className)}
        {...props}
      >
        {dot && (
          <span
            className={cn(
              'rounded-full',
              size === 'sm' ? 'h-1.5 w-1.5' : 'h-2 w-2',
              dotColors[variant]
            )}
          />
        )}
        {children}
      </span>
    );
  }
);

Badge.displayName = 'Badge';

export { Badge, type BadgeVariant, type BadgeProps };
