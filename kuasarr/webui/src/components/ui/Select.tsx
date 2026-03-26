import { forwardRef } from 'react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { ChevronDown, AlertCircle } from 'lucide-react';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'onChange'> {
  label?: string;
  error?: string;
  helperText?: string;
  options: SelectOption[];
  placeholder?: string;
  onChange?: (value: string) => void;
}

const Select = forwardRef<HTMLSelectElement, SelectProps>(
  (
    {
      className,
      label,
      error,
      helperText,
      options,
      placeholder,
      onChange,
      ...props
    },
    ref
  ) => {
    const selectBaseStyles =
      'w-full appearance-none bg-bg-tertiary border rounded-lg text-text-primary transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-kuasarr-primary/50 disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer';

    const selectStateStyles = error
      ? 'border-kuasarr-error focus:border-kuasarr-error'
      : 'border-bg-tertiary hover:border-kuasarr-primary/50 focus:border-kuasarr-primary';

    const selectSizeStyles = 'h-10 px-4 pr-10 py-2 text-sm';

    const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
      onChange?.(e.target.value);
    };

    return (
      <div className={cn('w-full', className)}>
        {label && (
          <label className="block text-sm font-medium text-text-primary mb-1.5">
            {label}
            {props.required && <span className="text-kuasarr-error ml-1">*</span>}
          </label>
        )}
        <div className="relative">
          <select
            ref={ref}
            className={cn(selectBaseStyles, selectStateStyles, selectSizeStyles)}
            onChange={handleChange}
            {...props}
          >
            {placeholder && (
              <option value="" disabled>
                {placeholder}
              </option>
            )}
            {options.map((option) => (
              <option
                key={option.value}
                value={option.value}
                disabled={option.disabled}
                className="bg-bg-secondary"
              >
                {option.label}
              </option>
            ))}
          </select>
          <div className="absolute right-3 top-1/2 -translate-y-1/2 text-text-secondary pointer-events-none">
            <ChevronDown className="h-4 w-4" />
          </div>
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

Select.displayName = 'Select';

export { Select };
