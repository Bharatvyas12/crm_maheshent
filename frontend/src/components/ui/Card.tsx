import type { HTMLAttributes, ReactNode } from 'react';
import { cn } from '@/lib/utils';

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('rounded-card border border-surface-border bg-surface shadow-sm', className)} {...props} />;
}

export function CardHeader({ className, children, action }: { className?: string; children: ReactNode; action?: ReactNode }) {
  return (
    <div className={cn('flex items-start justify-between gap-3 border-b border-surface-border px-4 py-3', className)}>
      <div className="min-w-0">{children}</div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

export function CardTitle({ className, children, as: Tag = 'h2' }: { className?: string; children: ReactNode; as?: 'h1' | 'h2' | 'h3' }) {
  return <Tag className={cn('truncate text-base font-semibold text-content', className)}>{children}</Tag>;
}

export function CardBody({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('px-4 py-4', className)} {...props} />;
}

export function CardFooter({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('flex flex-wrap items-center gap-2 border-t border-surface-border px-4 py-3', className)} {...props} />;
}