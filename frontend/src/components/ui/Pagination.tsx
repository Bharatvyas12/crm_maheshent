'use client';

import { Button } from './Button';

export function Pagination({
  page,
  pageSize,
  totalItems,
  totalPages,
  onPageChange,
  testId
}: {
  page: number;
  pageSize: number;
  totalItems: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  testId?: string;
}) {
  if (totalItems === 0) return null;
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, totalItems);
  return (
    <nav data-testid={testId} aria-label="Pagination" className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm">
      <p className="text-content-muted">
        Showing <span className="font-medium text-content">{start}</span>-<span className="font-medium text-content">{end}</span> of{' '}
        <span className="font-medium text-content">{totalItems}</span>
      </p>
      <div className="flex items-center gap-2">
        <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
          Previous
        </Button>
        <span className="text-content-muted">
          Page {page} of {Math.max(totalPages, 1)}
        </span>
        <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>
          Next
        </Button>
      </div>
    </nav>
  );
}