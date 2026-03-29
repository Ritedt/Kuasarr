import { forwardRef } from 'react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { AlertCircle } from 'lucide-react';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    { className, label, error, helperText, leftIcon, rightIcon, ...props },
    ref
  ) => {
    const inputBaseStyles =
      'w-full bg-bg-tertiary border rounded-lg text-text-primary placeholder:text-text-secondary/50 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-kuasarr-primary/50 disabled:cursor-not-allowed disabled:opacity-50';

    const inputStateStyles = error
      ? 'border-kuasarr-error focus:border-kuasarr-error'
      : 'border-bg-tertiary hover:border-kuasarr-primary/50 focus:border-kuasarr-primary';

    const inputPaddingStyles =
      leftIcon && rightIcon
        ? 'pl-10 pr-10'
        : leftIcon
        ? 'pl-10 pr-4'
        : rightIcon
        ? 'pl-4 pr-10'
        : 'px-4';

    const inputSizeStyles = 'h-10 py-2 text-sm';

    return (
      <div className={cn('w-full', className)}>
        {label && (
          <label className="block text-sm font-medium text-text-primary mb-1.5">
            {label}
            {props.required && <span className="text-kuasarr-error ml-1">*</span>}
          </label>
        )}
        <div className="relative">
          {leftIcon && (
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary pointer-events-none">
              {leftIcon}
            </div>
          )}
          <input
            ref={ref}
            className={cn(
              inputBaseStyles,
              inputStateStyles,
              inputPaddingStyles,
              inputSizeStyles
            )}
            {...props}
          />
          {rightIcon && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2 text-text-secondary">
              {rightIcon}
            </div>
          )}
        </div>
        {error && (
          <div className="flex items-center gap-1.5 mt-1.5 text-kuasarr-error text-sm">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}
        {helperText && !error && (
          <p className="mt-1.5 text-sm text-text-secondary">{helperText}</p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';

export { Input };
