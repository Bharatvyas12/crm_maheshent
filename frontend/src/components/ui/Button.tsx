'use client';

import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';
import { Spinner } from './Spinner';

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost' | 'link';
type Size = 'sm' | 'md' | 'lg' | 'action';

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-primary text-primary-fg hover:opacity-90 border border-transparent',
  secondary: 'bg-surface text-content border border-surface-border hover:bg-surface-muted',
  danger: 'bg-danger text-white hover:opacity-90 border border-transparent',
  ghost: 'bg-transparent text-content border border-transparent hover:bg-surface-muted',
  link: 'bg-transparent text-primary underline-offset-4 hover:underline border border-transparent px-0'
};

const SIZES: Record<Size, string> = {
  sm: 'h-9 px-3 text-sm',
  md: 'min-h-touch px-4 text-sm',
  lg: 'min-h-action px-5 text-base',
  action: 'min-h-action w-full px-5 text-base font-semibold'
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  /** Announce the in-flight state to assistive technology. */
  loadingLabel?: string;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = 'primary', size = 'md', loading = false, loadingLabel = 'Working', disabled, children, type = 'button', ...props },
  ref
) {
  const isDisabled = disabled || loading;
  return (
    <button
      ref={ref}
      type={type}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors',
        'disabled:cursor-not-allowed disabled:opacity-60',
        VARIANTS[variant],
        variant === 'link' ? '' : SIZES[size],
        className
      )}
      {...props}
    >
      {loading ? <Spinner label={loadingLabel} /> : null}
      {children}
    </button>
  );
});