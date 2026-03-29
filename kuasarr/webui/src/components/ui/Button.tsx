import { forwardRef } from 'react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { Loader2 } from 'lucide-react';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant = 'primary',
      size = 'md',
      loading = false,
      leftIcon,
      rightIcon,
      children,
      disabled,
      ...props
    },
    ref
  ) => {
    const baseStyles =
      'inline-flex items-center justify-center gap-2 font-medium transition-all duration-200 cursor-pointer rounded-lg focus:outline-none focus:ring-2 focus:ring-kuasarr-primary/50 disabled:cursor-not-allowed disabled:opacity-50';

    const variants = {
      primary:
        'bg-kuasarr-primary text-white hover:bg-kuasarr-primary/90 active:bg-kuasarr-primary/80 shadow-lg shadow-kuasarr-primary/25',
      secondary:
        'bg-kuasarr-secondary text-white hover:bg-kuasarr-secondary/90 active:bg-kuasarr-secondary/80 shadow-lg shadow-kuasarr-secondary/25',
      ghost:
        'bg-transparent text-text-secondary hover:bg-bg-tertiary hover:text-text-primary active:bg-bg-tertiary/80',
    };

    const sizes = {
      sm: 'h-8 px-3 text-sm',
      md: 'h-10 px-4 text-sm',
      lg: 'h-12 px-6 text-base',
    };

    return (
      <button
        ref={ref}
        className={cn(baseStyles, variants[variant], sizes[size], className)}
        disabled={disabled || loading}
        {...props}
      >
        {loading && <Loader2 className="h-4 w-4 animate-spin" />}
        {!loading && leftIcon}
        {children}
        {!loading && rightIcon}
      </button>
    );
  }
);

Button.displayName = 'Button';

export { Button };
