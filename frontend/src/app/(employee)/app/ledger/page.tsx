'use client';

import { useState } from 'react';
import { formatBusinessDate, formatMoney, humanize } from '@/lib/format';
import { useMyAdvances, useMyLedger } from '@/features/ledger/hooks';
import { usePermissions } from '@/features/auth/session';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { StatusPill } from '@/components/ui/StatusPill';
import { Badge } from '@/components/ui/Badge';
import { SkeletonList } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { Pagination } from '@/components/ui/Pagination';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { Alert } from '@/components/ui/Alert';

export default function EmployeeLedgerPage() {
  const { can } = usePermissions();
  const [page, setPage] = useState(1);
  const ledger = useMyLedger({ page });
  const advances = useMyAdvances({ page: 1 });

  const summary = ledger.data?.summary ?? null;
  const canSeeSalary = can('salary.read.self');

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">My ledger</h1>
        <p className="text-sm text-content-muted">Salary-related entries the admin has recorded for you.</p>
      </div>

      <Alert
        tone="info"
        title="These figures come from the server."
        nextStep="Ask the admin if an entry looks wrong; ledger rows are corrected by reversal, never edited."
      />

      {summary ? (
        <div className="grid grid-cols-3 gap-3">
          <Card>
            <CardBody>
              <p className="text-xs text-content-muted">Credit</p>
              <p className="text-lg font-semibold text-success">{formatMoney(summary.credit_total)}</p>
            </CardBody>
          </Card>
          <Card>
            <CardBody>
              <p className="text-xs text-content-muted">Debit</p>
              <p className="text-lg font-semibold text-danger">{formatMoney(summary.debit_total)}</p>
            </CardBody>
          </Card>
          <Card>
            <CardBody>
              <p className="text-xs text-content-muted">Net</p>
              <p className="text-lg font-semibold">{formatMoney(summary.net)}</p>
            </CardBody>
          </Card>
        </div>
      ) : null}

      {!canSeeSalary ? (
        <Alert tone="info" title="Payslips are not shown to you." nextStep="Employee access to salary records is a pending client decision." />
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle as="h2">Entries</CardTitle>
        </CardHeader>
        <CardBody>
          {ledger.isLoading ? (
            <SkeletonList rows={4} />
          ) : ledger.error ? (
            <ProblemAlert error={ledger.error} onRetry={() => void ledger.refetch()} />
          ) : (ledger.data?.items.length ?? 0) === 0 ? (
            <EmptyState title="No ledger entries" hint="Advances, deductions and payments appear here." />
          ) : (
            <ul className="space-y-2">
              {ledger.data?.items.map((entry) => (
                <li key={entry.id} className="flex items-start justify-between gap-3 border-b border-surface-border/60 pb-2 text-sm last:border-0">
                  <span className="min-w-0">
                    <span className="font-medium">{humanize(entry.entry_type)}</span>
                    {entry.is_reversed ? <Badge tone="warning" className="ml-2">Reversed</Badge> : null}
                    <span className="block text-xs text-content-muted">
                      {formatBusinessDate(entry.business_date)}
                      {entry.reason ? ` - ${entry.reason}` : ''}
                    </span>
                  </span>
                  <span className={entry.direction === 'CREDIT' ? 'shrink-0 font-medium text-success' : 'shrink-0 font-medium text-danger'}>
                    {entry.direction === 'CREDIT' ? '+' : '-'}
                    {formatMoney(entry.amount, entry.currency)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      {ledger.data ? (
        <Pagination
          page={ledger.data.page}
          pageSize={ledger.data.page_size}
          totalItems={ledger.data.total_items}
          totalPages={ledger.data.total_pages}
          onPageChange={setPage}
        />
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle as="h2">My advances</CardTitle>
        </CardHeader>
        <CardBody>
          {advances.isLoading ? (
            <SkeletonList rows={2} />
          ) : advances.error ? (
            <ProblemAlert error={advances.error} onRetry={() => void advances.refetch()} />
          ) : (advances.data?.items.length ?? 0) === 0 ? (
            <p className="text-sm text-content-muted">No advances recorded.</p>
          ) : (
            <ul className="space-y-2">
              {advances.data?.items.map((advance) => (
                <li key={advance.id} className="flex items-center justify-between gap-3 border-b border-surface-border/60 pb-2 text-sm last:border-0">
                  <span>
                    <span className="font-medium">{formatMoney(advance.amount, advance.currency)}</span>
                    <span className="block text-xs text-content-muted">
                      Issued {formatBusinessDate(advance.issued_on)} - outstanding {formatMoney(advance.outstanding_amount, advance.currency)}
                    </span>
                  </span>
                  <StatusPill value={advance.status} />
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </div>
  );
}