import type { ReactNode } from 'react';

export function PageHeader({
  title,
  description,
  actions,
  testId
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  testId?: string;
}) {
  return (
    <header data-testid={testId} className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold text-content">{title}</h1>
        {description ? <p className="mt-1 text-sm text-content-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}