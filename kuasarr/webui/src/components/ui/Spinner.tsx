import { forwardRef } from 'react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export interface SpinnerProps extends React.HTMLAttributes<HTMLDivElement> {
  size?: 'sm' | 'md' | 'lg' | 'xl';
  variant?: 'primary' | 'secondary' | 'white';
}

const Spinner = forwardRef<HTMLDivElement, SpinnerProps>(
  ({ className, size = 'md', variant = 'primary', ...props }, ref) => {
    const sizes = {
      sm: 'h-4 w-4 border-2',
      md: 'h-6 w-6 border-2',
      lg: 'h-8 w-8 border-[3px]',
      xl: 'h-12 w-12 border-4',
    };

    const variants = {
      primary: 'border-kuasarr-primary/30 border-t-kuasarr-primary',
      secondary: 'border-kuasarr-secondary/30 border-t-kuasarr-secondary',
      white: 'border-white/30 border-t-white',
    };

    return (
      <div
        ref={ref}
        className={cn(
          'inline-block rounded-full animate-spin',
          sizes[size],
          variants[variant],
          className
        )}
        {...props}
      />
    );
  }
);

Spinner.displayName = 'Spinner';

export { Spinner };
