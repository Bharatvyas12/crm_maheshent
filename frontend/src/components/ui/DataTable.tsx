'use client';

import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { SkeletonList } from './Skeleton';
import { EmptyState } from './EmptyState';

export interface Column<T> {
  key: string;
  header: string;
  /** Allow-list sortable fields only (docs/01_ARCHITECTURE.md section 13.5). */
  sortable?: boolean;
  align?: 'left' | 'right' | 'center';
  className?: string;
  render: (row: T) => ReactNode;
}

export interface DataTableProps<T> {
  columns: Array<Column<T>>;
  rows: T[];
  getRowId: (row: T) => string;
  loading?: boolean;
  error?: ReactNode;
  emptyTitle?: string;
  emptyHint?: string;
  emptyAction?: ReactNode;
  /** Current sort, e.g. "-created_at"; matches the API `sort` parameter. */
  sort?: string;
  onSortChange?: (sort: string) => void;
  onRowClick?: (row: T) => void;
  caption?: string;
  testId?: string;
}

export function DataTable<T>({
  columns,
  rows,
  getRowId,
  loading,
  error,
  emptyTitle = 'Nothing to show',
  emptyHint,
  emptyAction,
  sort,
  onSortChange,
  onRowClick,
  caption,
  testId
}: DataTableProps<T>) {
  if (loading) return <SkeletonList rows={5} />;
  if (error) return <>{error}</>;
  if (rows.length === 0) return <EmptyState title={emptyTitle} hint={emptyHint} action={emptyAction} />;

  function toggleSort(column: Column<T>) {
    if (!column.sortable || !onSortChange) return;
    const current = sort ?? '';
    if (current === column.key) {
      onSortChange(`-${column.key}`);
    } else if (current === `-${column.key}`) {
      onSortChange('');
    } else {
      onSortChange(column.key);
    }
  }

  function ariaSort(column: Column<T>): 'ascending' | 'descending' | 'none' | undefined {
    if (!column.sortable) return undefined;
    if (sort === column.key) return 'ascending';
    if (sort === `-${column.key}`) return 'descending';
    return 'none';
  }

  return (
    <div className="table-scroll" data-testid={testId}>
      <table className="min-w-full border-collapse text-sm">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead>
          <tr className="border-b border-surface-border text-left">
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                aria-sort={ariaSort(column)}
                className={cn(
                  'whitespace-nowrap px-3 py-2 text-xs font-semibold uppercase tracking-wide text-content-muted',
                  column.align === 'right' && 'text-right',
                  column.align === 'center' && 'text-center'
                )}
              >
                {column.sortable && onSortChange ? (
                  <button type="button" onClick={() => toggleSort(column)} className="inline-flex items-center gap-1 hover:text-content">
                    {column.header}
                    <span aria-hidden="true">{sort === column.key ? '\u2191' : sort === `-${column.key}` ? '\u2193' : '\u2195'}</span>
                  </button>
                ) : (
                  column.header
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={getRowId(row)}
              className={cn('border-b border-surface-border/60', onRowClick && 'cursor-pointer hover:bg-surface-muted')}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={cn(
                    'px-3 py-2 align-middle',
                    column.align === 'right' && 'text-right',
                    column.align === 'center' && 'text-center',
                    column.className
                  )}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}