import { useEffect, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { LoaderCircle } from 'lucide-react';

interface PrimaryActionButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'onClick'> {
  icon: ReactNode;
  onAction?: () => void | Promise<void>;
  beforeActionDelayMs?: number;
  afterActionDelayMs?: number;
  iconClassName?: string;
  labelClassName?: string;
  spinnerClassName?: string;
}

const delay = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

export function PrimaryActionButton({
  icon,
  children,
  disabled,
  className = '',
  onAction,
  beforeActionDelayMs = 140,
  afterActionDelayMs = 520,
  iconClassName = '',
  labelClassName = '',
  spinnerClassName = '',
  type = 'button',
  ...props
}: PrimaryActionButtonProps) {
  const [isLoading, setIsLoading] = useState(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const handleClick = async () => {
    if (disabled || isLoading) {
      return;
    }

    setIsLoading(true);

    try {
      if (beforeActionDelayMs > 0) {
        await delay(beforeActionDelayMs);
      }

      await onAction?.();

      if (afterActionDelayMs > 0) {
        await delay(afterActionDelayMs);
      }
    } finally {
      if (mountedRef.current) {
        setIsLoading(false);
      }
    }
  };

  return (
    <button
      {...props}
      type={type}
      disabled={disabled || isLoading}
      aria-busy={isLoading}
      data-loading={isLoading ? 'true' : 'false'}
      onClick={() => void handleClick()}
      className={`app-primary-action relative grid grid-cols-[16px_minmax(0,1fr)_16px] items-center gap-3 overflow-hidden ${className}`}
    >
      <span className={`flex h-4 w-4 items-center justify-center ${iconClassName}`}>
        {isLoading ? <LoaderCircle className={`h-4 w-4 animate-spin ${spinnerClassName || iconClassName}`} /> : icon}
      </span>
      <span className={`min-w-0 text-center ${labelClassName}`}>{children}</span>
      <span className="h-4 w-4 opacity-0" aria-hidden="true" />
    </button>
  );
}
