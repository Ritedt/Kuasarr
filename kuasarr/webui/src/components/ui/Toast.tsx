import { useEffect, useState, forwardRef } from 'react';
import { createPortal } from 'react-dom';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { X, CheckCircle, AlertCircle, AlertTriangle, Info } from 'lucide-react';
import { Button } from './Button';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type ToastVariant = 'success' | 'error' | 'warning' | 'info';

interface ToastProps {
  id: string;
  variant?: ToastVariant;
  title?: string;
  message: string;
  duration?: number;
  onClose: (id: string) => void;
  action?: {
    label: string;
    onClick: () => void;
  };
}

const Toast = forwardRef<HTMLDivElement, ToastProps>(
  (
    { id, variant = 'info', title, message, duration = 5000, onClose, action },
    ref
  ) => {
    const [progress, setProgress] = useState(100);
    const [isPaused, setIsPaused] = useState(false);

    useEffect(() => {
      if (duration <= 0 || isPaused) return;

      const startTime = Date.now();
      const endTime = startTime + duration;

      const updateProgress = () => {
        const now = Date.now();
        const remaining = Math.max(0, endTime - now);
        const newProgress = (remaining / duration) * 100;

        setProgress(newProgress);

        if (remaining > 0) {
          requestAnimationFrame(updateProgress);
        } else {
          onClose(id);
        }
      };

      const animationFrame = requestAnimationFrame(updateProgress);
      return () => cancelAnimationFrame(animationFrame);
    }, [id, duration, isPaused, onClose]);

    const icons = {
      success: <CheckCircle className="h-5 w-5 text-kuasarr-success" />,
      error: <AlertCircle className="h-5 w-5 text-kuasarr-error" />,
      warning: <AlertTriangle className="h-5 w-5 text-kuasarr-warning" />,
      info: <Info className="h-5 w-5 text-kuasarr-secondary" />,
    };

    const progressColors = {
      success: 'bg-kuasarr-success',
      error: 'bg-kuasarr-error',
      warning: 'bg-kuasarr-warning',
      info: 'bg-kuasarr-secondary',
    };

    return (
      <div
        ref={ref}
        className="relative w-full max-w-sm bg-bg-secondary rounded-xl shadow-lg shadow-black/30 border border-bg-tertiary overflow-hidden animate-slide-up"
        onMouseEnter={() => setIsPaused(true)}
        onMouseLeave={() => setIsPaused(false)}
        role="alert"
        aria-live="polite"
      >
        <div className="flex items-start gap-3 p-4">
          <div className="shrink-0 mt-0.5">{icons[variant]}</div>
          <div className="flex-1 min-w-0">
            {title && (
              <h4 className="text-sm font-semibold text-text-primary">{title}</h4>
            )}
            <p className={cn('text-sm text-text-secondary', title && 'mt-0.5')}>
              {message}
            </p>
            {action && (
              <Button
                variant="ghost"
                size="sm"
                onClick={action.onClick}
                className="mt-2 -ml-2 h-auto py-1 text-kuasarr-primary-light hover:text-kuasarr-primary"
              >
                {action.label}
              </Button>
            )}
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onClose(id)}
            className="shrink-0 -mr-2 -mt-2 h-auto py-1"
            aria-label="Close notification"
          >
            <X className="h-4 w-4 text-text-secondary hover:text-text-primary" />
          </Button>
        </div>

        {duration > 0 && (
          <div className="absolute bottom-0 left-0 right-0 h-1 bg-bg-tertiary">
            <div
              className={cn('h-full transition-all ease-linear', progressColors[variant])}
              style={{ width: `${progress}%` }}
            />
          </div>
        )}
      </div>
    );
  }
);

Toast.displayName = 'Toast';

interface ToastContainerProps {
  toasts: Array<{
    id: string;
    variant?: ToastVariant;
    title?: string;
    message: string;
    duration?: number;
    action?: {
      label: string;
      onClick: () => void;
    };
  }>;
  onClose: (id: string) => void;
  position?: 'top-right' | 'top-left' | 'bottom-right' | 'bottom-left' | 'top-center' | 'bottom-center';
}

const ToastContainer = ({
  toasts,
  onClose,
  position = 'bottom-right',
}: ToastContainerProps) => {
  const positions = {
    'top-right': 'top-4 right-4',
    'top-left': 'top-4 left-4',
    'bottom-right': 'bottom-4 right-4',
    'bottom-left': 'bottom-4 left-4',
    'top-center': 'top-4 left-1/2 -translate-x-1/2',
    'bottom-center': 'bottom-4 left-1/2 -translate-x-1/2',
  };

  if (toasts.length === 0) return null;

  return createPortal(
    <div
      className={cn(
        'fixed z-50 flex flex-col gap-3 w-full max-w-sm pointer-events-none',
        positions[position]
      )}
    >
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto">
          <Toast
            id={toast.id}
            variant={toast.variant}
            title={toast.title}
            message={toast.message}
            duration={toast.duration}
            onClose={onClose}
            action={toast.action}
          />
        </div>
      ))}
    </div>,
    document.body
  );
};

export { Toast, ToastContainer, type ToastVariant, type ToastProps, type ToastContainerProps };
