'use client';

import { useState } from 'react';
import Link from 'next/link';
import { PermissionGate } from '@/components/PermissionGate';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card, CardBody } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { DataTable, type Column } from '@/components/ui/DataTable';
import { Pagination } from '@/components/ui/Pagination';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { SelectField, TextAreaField, TextField } from '@/components/ui/Form';
import { StatusPill } from '@/components/ui/StatusPill';
import { useCreatePayrollRun, usePayrollRuns } from '@/features/ledger/hooks';
import { formatDateTime, humanize } from '@/lib/format';
import type { PayrollRun } from '@/lib/types';

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

export default function AdminPayrollPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const query = usePayrollRuns({ status: status || undefined, page });
  const create = useCreatePayrollRun();

  const now = new Date();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    period_year: String(now.getUTCFullYear()),
    period_month: String(now.getUTCMonth() + 1),
    notes: ''
  });

  const columns: Array<Column<PayrollRun>> = [
    {
      key: 'period',
      header: 'Period',
      render: (row) => `${MONTHS[row.period_month - 1] ?? row.period_month} ${row.period_year}`
    },
    { key: 'status', header: 'Status', render: (row) => <StatusPill value={row.status} /> },
    { key: 'created_at', header: 'Created', render: (row) => formatDateTime(row.created_at) },
    { key: 'finalized_at', header: 'Finalized', render: (row) => (row.finalized_at ? formatDateTime(row.finalized_at) : '-') },
    { key: 'paid_at', header: 'Paid', render: (row) => (row.paid_at ? formatDateTime(row.paid_at) : '-') },
    {
      key: 'open',
      header: '',
      render: (row) => (
        <Link href={`/admin/payroll/${row.id}`} className="text-sm font-medium text-primary hover:underline">
          Open run
        </Link>
      )
    }
  ];

  return (
    <div className="space-y-5">
      <PageHeader
        title="Payroll"
        description="Compute, finalize, lock and pay salary runs. Finalized records are immutable."
        actions={
          <PermissionGate anyOf={['salary.compute']}>
            <Button onClick={() => setOpen(true)}>New run</Button>
          </PermissionGate>
        }
      />

      <Card>
        <CardBody className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <SelectField
            label="Status"
            name="status"
            placeholder="Any"
            value={status}
            onChange={(event) => { setStatus(event.target.value); setPage(1); }}
            options={['DRAFT', 'COMPUTED', 'FINALIZED', 'LOCKED', 'PAID'].map((value) => ({ value, label: humanize(value) }))}
          />
        </CardBody>
      </Card>

      <DataTable
        columns={columns}
        rows={query.data?.items ?? []}
        getRowId={(row) => row.id}
        loading={query.isLoading}
        error={query.error ? <ProblemAlert error={query.error} onRetry={() => void query.refetch()} /> : undefined}
        emptyTitle="No payroll runs"
        emptyHint="Create a run for a period to compute salary records."
      />

      {query.data ? (
        <Pagination
          page={query.data.page}
          pageSize={query.data.page_size}
          totalItems={query.data.total_items}
          totalPages={query.data.total_pages}
          onPageChange={setPage}
        />
      ) : null}

      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Create a payroll run"
        description="A run is created in DRAFT; nothing is payable until it is computed, finalized and paid."
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              loading={create.isPending}
              disabled={create.isPending}
              onClick={() =>
                create.mutate(
                  {
                    period_year: Number(form.period_year),
                    period_month: Number(form.period_month),
                    notes: form.notes.trim() || undefined
                  },
                  { onSuccess: () => setOpen(false) }
                )
              }
            >
              Create run
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {create.error ? <ProblemAlert error={create.error} /> : null}
          <TextField label="Year" name="period_year" type="number" required value={form.period_year} onChange={(event) => setForm({ ...form, period_year: event.target.value })} />
          <SelectField
            label="Month"
            name="period_month"
            required
            value={form.period_month}
            onChange={(event) => setForm({ ...form, period_month: event.target.value })}
            options={MONTHS.map((label, index) => ({ value: String(index + 1), label }))}
          />
          <TextAreaField label="Notes (optional)" name="notes" value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} />
        </div>
      </Dialog>
    </div>
  );
}