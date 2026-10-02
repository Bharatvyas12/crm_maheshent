'use client';

import { Suspense, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { PermissionGate } from '@/components/PermissionGate';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Dialog } from '@/components/ui/Dialog';
import { DataTable, type Column } from '@/components/ui/DataTable';
import { Pagination } from '@/components/ui/Pagination';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { StatCard } from '@/components/StatCard';
import { SelectField, TextAreaField, TextField } from '@/components/ui/Form';
import { useCreateLedgerEntry, useLedger, useReverseLedgerEntry } from '@/features/ledger/hooks';
import { useEmployees } from '@/features/employees/hooks';
import { formatMoney, humanize } from '@/lib/format';
import type { LedgerEntry } from '@/lib/types';

/**
 * Manual ledger entry types documented in docs/04_BUSINESS_RULES.md section 13 (ledger sign
 * convention). The server remains authoritative about which types are permitted manually; the
 * list is only a convenience and an unknown value is still submitted verbatim.
 */
const MANUAL_ENTRY_TYPES = [
  'BONUS',
  'OVERTIME_PAY',
  'ADJUSTMENT',
  'LEAVE_DEDUCTION',
  'LATE_DEDUCTION',
  'OTHER_DEDUCTION',
  'PAYMENT_MADE'
] as const;

interface EntryForm {
  employee_id: string;
  entry_type: string;
  direction: string;
  amount: string;
  business_date: string;
  reason: string;
}

const EMPTY_FORM: EntryForm = {
  employee_id: '',
  entry_type: 'BONUS',
  direction: 'CREDIT',
  amount: '',
  business_date: new Date().toISOString().slice(0, 10),
  reason: ''
};

function LedgerInner() {
  const searchParams = useSearchParams();
  const [page, setPage] = useState(1);
  const [employeeId, setEmployeeId] = useState(searchParams.get('employee_id') ?? '');
  const [entryType, setEntryType] = useState(searchParams.get('entry_type') ?? '');
  const [direction, setDirection] = useState(searchParams.get('direction') ?? '');

  const query = useLedger({ employee_id: employeeId || undefined, entry_type: entryType || undefined, direction: direction || undefined, page });
  const employees = useEmployees({ page_size: 100 });
  const create = useCreateLedgerEntry();
  const reverse = useReverseLedgerEntry();

  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState<EntryForm>(EMPTY_FORM);
  const [formError, setFormError] = useState<unknown>(null);
  const [selected, setSelected] = useState<LedgerEntry | null>(null);
  const [reason, setReason] = useState('');
  const [reverseOpen, setReverseOpen] = useState(false);

  const summary = query.data?.summary ?? null;
  const formInvalid = !form.employee_id || !form.amount || !form.reason.trim();

  const columns: Array<Column<LedgerEntry>> = [
    { key: 'business_date', header: 'Date', sortable: true, render: (row) => row.business_date },
    {
      key: 'employee',
      header: 'Employee',
      render: (row) => row.employee?.full_name ?? row.employee_id.slice(0, 8)
    },
    { key: 'entry_type', header: 'Type', render: (row) => humanize(row.entry_type) },
    {
      key: 'direction',
      header: 'Direction',
      render: (row) => <Badge tone={row.direction === 'CREDIT' ? 'success' : 'neutral'}>{humanize(row.direction)}</Badge>
    },
    { key: 'amount', header: 'Amount', align: 'right', render: (row) => formatMoney(row.amount, row.currency) },
    { key: 'reason', header: 'Reason', render: (row) => <span className="text-content-muted">{row.reason}</span> },
    {
      key: 'state',
      header: 'State',
      render: (row) => (row.is_reversed ? <Badge tone="warning">Reversed</Badge> : <Badge tone="neutral">Posted</Badge>)
    }
  ];

  return (
    <div className="space-y-5">
      <PageHeader
        title="Employee ledger"
        description="Append-only financial movements. Corrections are reversal entries; nothing is edited in place."
        actions={
          <PermissionGate anyOf={['ledger.entry.create']}>
            <Button onClick={() => { setForm(EMPTY_FORM); setFormError(null); setFormOpen(true); }}>Post entry</Button>
          </PermissionGate>
        }
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatCard label="Credits" value={summary ? formatMoney(summary.credit_total) : null} tone="success" loading={query.isLoading} />
        <StatCard label="Debits" value={summary ? formatMoney(summary.debit_total) : null} tone="warning" loading={query.isLoading} />
        <StatCard label="Net balance" value={summary ? formatMoney(summary.net) : null} loading={query.isLoading} />
      </div>

      <Card>
        <CardBody className="grid grid-cols-1 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <SelectField
            label="Employee"
            name="employee_id"
            placeholder="Any"
            value={employeeId}
            onChange={(event) => { setEmployeeId(event.target.value); setPage(1); }}
            options={(employees.data?.items ?? []).map((employee) => ({ value: employee.id, label: `${employee.full_name} (${employee.employee_code})` }))}
          />
          <SelectField
            label="Entry type"
            name="entry_type"
            placeholder="Any"
            value={entryType}
            onChange={(event) => { setEntryType(event.target.value); setPage(1); }}
            options={MANUAL_ENTRY_TYPES.map((type) => ({ value: type, label: humanize(type) }))}
          />
          <SelectField
            label="Direction"
            name="direction"
            placeholder="Any"
            value={direction}
            onChange={(event) => { setDirection(event.target.value); setPage(1); }}
            options={[{ value: 'CREDIT', label: 'Credit' }, { value: 'DEBIT', label: 'Debit' }]}
          />
        </CardBody>
      </Card>

      <DataTable
        columns={columns}
        rows={query.data?.items ?? []}
        getRowId={(row) => row.id}
        loading={query.isLoading}
        error={query.error ? <ProblemAlert error={query.error} onRetry={() => void query.refetch()} /> : undefined}
        onRowClick={(row) => setSelected(row)}
        emptyTitle="No ledger entries"
        emptyHint="Entries appear when payroll, advances or manual adjustments are posted."
        testId="ledger-table"
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
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title="Post a ledger entry"
        description="The server validates the entry type, the date and whether the period is locked."
        footer={
          <>
            <Button variant="secondary" onClick={() => setFormOpen(false)}>Cancel</Button>
            <Button
              loading={create.isPending}
              disabled={formInvalid || create.isPending}
              onClick={() =>
                create.mutate(
                  { ...form, reason: form.reason.trim() },
                  { onSuccess: () => { setFormOpen(false); setForm(EMPTY_FORM); } }
                )
              }
            >
              Post entry
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {formError ? <ProblemAlert error={formError} /> : null}
          <SelectField
            label="Employee"
            name="employee_id"
            required
            value={form.employee_id}
            onChange={(event) => setForm({ ...form, employee_id: event.target.value })}
            options={(employees.data?.items ?? []).map((employee) => ({ value: employee.id, label: `${employee.full_name} (${employee.employee_code})` }))}
          />
          <SelectField
            label="Entry type"
            name="entry_type"
            required
            value={form.entry_type}
            onChange={(event) => setForm({ ...form, entry_type: event.target.value })}
            options={MANUAL_ENTRY_TYPES.map((type) => ({ value: type, label: humanize(type) }))}
          />
          <SelectField
            label="Direction"
            name="direction"
            required
            value={form.direction}
            onChange={(event) => setForm({ ...form, direction: event.target.value })}
            options={[{ value: 'CREDIT', label: 'Credit (increases amount owed)' }, { value: 'DEBIT', label: 'Debit (reduces amount owed)' }]}
          />
          <TextField
            label="Amount"
            name="amount"
            required
            inputMode="decimal"
            help="Decimal string with up to 2 decimals, for example 1500.00"
            value={form.amount}
            onChange={(event) => setForm({ ...form, amount: event.target.value })}
          />
          <TextField
            label="Business date"
            name="business_date"
            type="date"
            required
            value={form.business_date}
            onChange={(event) => setForm({ ...form, business_date: event.target.value })}
          />
          <TextAreaField
            label="Reason"
            name="reason"
            required
            value={form.reason}
            onChange={(event) => setForm({ ...form, reason: event.target.value })}
          />
        </div>
      </Dialog>

      <Dialog
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title="Ledger entry"
        footer={
          <PermissionGate anyOf={['ledger.entry.adjust']}>
            <Button
              variant="danger"
              disabled={!selected || selected.is_reversed}
              onClick={() => { setReverseOpen(true); setReason(''); }}
            >
              Reverse entry
            </Button>
          </PermissionGate>
        }
      >
        {selected ? (
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between gap-3"><dt className="text-content-muted">Employee</dt><dd>{selected.employee?.full_name ?? selected.employee_id}</dd></div>
            <div className="flex justify-between gap-3"><dt className="text-content-muted">Type</dt><dd>{humanize(selected.entry_type)}</dd></div>
            <div className="flex justify-between gap-3"><dt className="text-content-muted">Direction</dt><dd>{humanize(selected.direction)}</dd></div>
            <div className="flex justify-between gap-3"><dt className="text-content-muted">Amount</dt><dd>{formatMoney(selected.amount, selected.currency)}</dd></div>
            <div className="flex justify-between gap-3"><dt className="text-content-muted">Business date</dt><dd>{selected.business_date}</dd></div>
            <div className="flex justify-between gap-3"><dt className="text-content-muted">Reason</dt><dd className="text-right">{selected.reason}</dd></div>
            {selected.is_reversed ? <p className="text-warning">This entry has been reversed. Both rows remain visible.</p> : null}
          </dl>
        ) : null}
      </Dialog>

      <Dialog
        open={reverseOpen}
        onClose={() => setReverseOpen(false)}
        title="Reverse this entry"
        description="A reversal entry references the original; the original is never edited or deleted."
        footer={
          <>
            <Button variant="secondary" onClick={() => setReverseOpen(false)}>Cancel</Button>
            <Button
              variant="danger"
              loading={reverse.isPending}
              disabled={!reason.trim() || reverse.isPending}
              onClick={() => {
                if (!selected) return;
                reverse.mutate({ id: selected.id, reason: reason.trim() }, { onSuccess: () => { setReverseOpen(false); setSelected(null); } });
              }}
            >
              Confirm reversal
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {reverse.error ? <ProblemAlert error={reverse.error} /> : null}
          <TextAreaField label="Reason" name="reason" required value={reason} onChange={(event) => setReason(event.target.value)} />
        </div>
      </Dialog>
    </div>
  );
}

export default function AdminLedgerPage() {
  return (
    <Suspense fallback={<div className="h-40" />}>
      <LedgerInner />
    </Suspense>
  );
}