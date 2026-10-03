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
  const safePage = Number.isNaN(Number(page)) || page < 1 ? 1 : Number(page);
  const safePageSize = Number.isNaN(Number(pageSize)) || pageSize < 1 ? 10 : Number(pageSize);
  const safeTotalItems = Number.isNaN(Number(totalItems)) || totalItems < 0 ? 0 : Number(totalItems);
  const safeTotalPages = Number.isNaN(Number(totalPages)) || totalPages < 1 ? 1 : Number(totalPages);

  if (safeTotalItems === 0) return null;
  const start = Math.min((safePage - 1) * safePageSize + 1, safeTotalItems);
  const end = Math.min(safePage * safePageSize, safeTotalItems);
  return (
    <nav data-testid={testId} aria-label="Pagination" className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm">
      <p className="text-content-muted">
        Showing <span className="font-medium text-content">{start}</span>-<span className="font-medium text-content">{end}</span> of{' '}
        <span className="font-medium text-content">{safeTotalItems}</span>
      </p>
      <div className="flex items-center gap-2">
        <Button variant="secondary" size="sm" disabled={safePage <= 1} onClick={() => onPageChange(safePage - 1)}>
          Previous
        </Button>
        <span className="text-content-muted">
          Page {safePage} of {safeTotalPages}
        </span>
        <Button variant="secondary" size="sm" disabled={safePage >= safeTotalPages} onClick={() => onPageChange(safePage + 1)}>
          Next
        </Button>
      </div>
    </nav>
  );
}