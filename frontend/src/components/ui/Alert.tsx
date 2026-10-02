import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

type Tone = 'info' | 'success' | 'warning' | 'danger';

const TONES: Record<Tone, string> = {
  info: 'border-info/40 bg-info-soft text-content',
  success: 'border-success/40 bg-success-soft text-content',
  warning: 'border-warning/40 bg-warning-soft text-content',
  danger: 'border-danger/40 bg-danger-soft text-content'
};

const ICONS: Record<Tone, string> = { info: 'i', success: 'v', warning: '!', danger: 'x' };

export function Alert({
  tone = 'info',
  title,
  children,
  nextStep,
  actions,
  className,
  testId
}: {
  tone?: Tone;
  title: ReactNode;
  children?: ReactNode;
  nextStep?: ReactNode;
  actions?: ReactNode;
  className?: string;
  testId?: string;
}) {
  const role = tone === 'danger' ? 'alert' : 'status';
  return (
    <div role={role} data-testid={testId} className={cn('rounded-md border px-3 py-3 text-sm', TONES[tone], className)}>
      <div className="flex items-start gap-2">
        <span
          aria-hidden="true"
          className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-current text-xs font-bold"
        >
          {ICONS[tone]}
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-semibold">{title}</p>
          {children ? <div className="mt-1 text-content-muted">{children}</div> : null}
          {nextStep ? <p className="mt-1 font-medium">{nextStep}</p> : null}
          {actions ? <div className="mt-3 flex flex-wrap gap-2">{actions}</div> : null}
        </div>
      </div>
    </div>
  );
}