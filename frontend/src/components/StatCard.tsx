import type { ReactNode } from 'react';
import Link from 'next/link';
import { Card, CardBody } from '@/components/ui/Card';
import { cn } from '@/lib/utils';

/**
 * Dashboard KPI card. Every card links to the filtered list that produced the number
 * (docs/07_UI_SPEC.md section 7.1).
 */
export function StatCard({
  label,
  value,
  hint,
  href,
  tone = 'neutral',
  loading
}: {
  label: string;
  value: number | string | null;
  hint?: string;
  href?: string;
  tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'info';
  loading?: boolean;
}) {
  const tones = {
    neutral: 'text-content',
    success: 'text-success',
    warning: 'text-warning',
    danger: 'text-danger',
    info: 'text-info'
  } as const;

  const body: ReactNode = (
    <CardBody className="flex flex-col gap-1">
      <p className="text-xs font-medium uppercase tracking-wide text-content-muted">{label}</p>
      <p className={cn('text-2xl font-semibold', tones[tone])} data-testid={`stat-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
        {loading ? '\u2013' : value === null || value === undefined ? '\u2013' : value}
      </p>
      {hint ? <p className="text-xs text-content-muted">{hint}</p> : null}
    </CardBody>
  );

  if (href) {
    return (
      <Link href={href} className="block rounded-card transition-shadow hover:shadow-md focus-visible:outline-2 focus-visible:outline-primary">
        <Card>{body}</Card>
      </Link>
    );
  }
  return <Card>{body}</Card>;
}