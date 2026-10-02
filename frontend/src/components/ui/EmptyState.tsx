import type { ReactNode } from 'react';

export function EmptyState({
  title,
  hint,
  action,
  testId
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
  testId?: string;
}) {
  return (
    <div data-testid={testId} className="flex flex-col items-center justify-center gap-2 rounded-card border border-dashed border-surface-border bg-surface px-6 py-10 text-center">
      <p className="text-base font-semibold text-content">{title}</p>
      {hint ? <p className="max-w-sm text-sm text-content-muted">{hint}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}