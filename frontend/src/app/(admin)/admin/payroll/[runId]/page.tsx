'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { PermissionGate } from '@/components/PermissionGate';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Dialog } from '@/components/ui/Dialog';
import { DataTable, type Column } from '@/components/ui/DataTable';
import { Pagination } from '@/components/ui/Pagination';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { SkeletonList } from '@/components/ui/Skeleton';
import { StatCard } from '@/components/StatCard';
import { CheckboxField, TextAreaField, TextField } from '@/components/ui/Form';
import { StatusPill } from '@/components/ui/StatusPill';
import {
  useComputePayrollRun,
  useFinalizePayrollRun,
  useLockPayrollRun,
  useMarkPayrollPaid,
  usePayrollRun,
  useSalaryRecords,
  useUnlockPayrollRun
} from '@/features/ledger/hooks';
import { formatDateTime, formatMoney, humanize } from '@/lib/format';
import { pickNumber } from '@/lib/summary';
import type { SalaryRecord } from '@/lib/types';

type RunAction = 'compute' | 'finalize' | 'lock' | 'unlock' | 'pay';

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

function Money({ value, currency }: { value: string | number | null | undefined; currency: string }) {
  return <span>{formatMoney(value ?? null, currency)}</span>;
}

export default function AdminPayrollRunPage() {
  const params = useParams<{ runId: string }>();
  const runId = params?.runId ?? '';

  const run = usePayrollRun(runId);
  const [recordPage, setRecordPage] = useState(1);
  const records = useSalaryRecords({ payroll_run_id: runId, page: recordPage });

  const compute = useComputePayrollRun();
  const finalize = useFinalizePayrollRun();
  const lock = useLockPayrollRun();
  const unlock = useUnlockPayrollRun();
  const markPaid = useMarkPayrollPaid();

  const [action, setAction] = useState<RunAction | null>(null);
  const [reason, setReason] = useState('');
  const [paidOn, setPaidOn] = useState(new Date().toISOString().slice(0, 10));
  const [force, setForce] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState<SalaryRecord | null>(null);

  const currency = run.data?.summary?.currency ? String(run.data.summary.currency) : 'INR';
  const pending = action === 'compute' ? compute.isPending : action === 'finalize' ? finalize.isPending : action === 'lock' ? lock.isPending : action === 'unlock' ? unlock.isPending : action === 'pay' ? markPaid.isPending : false;

  const blockers = run.data?.summary?.blockers;
  const blockerList = Array.isArray(blockers) ? (blockers as Array<Record<string, unknown>>) : [];

  const counts = run.data?.record_counts ?? null;

  const columns: Array<Column<SalaryRecord>> = [
    { key: 'employee', header: 'Employee', render: (row) => row.employee?.full_name ?? row.employee_id.slice(0, 8) },
    { key: 'payable_days', header: 'Payable days', align: 'right', render: (row) => row.payable_days },
    { key: 'gross_amount', header: 'Gross', align: 'right', render: (row) => <Money value={row.gross_amount} currency={row.currency} /> },
    { key: 'overtime_amount', header: 'Overtime', align: 'right', render: (row) => <Money value={row.overtime_amount} currency={row.currency} /> },
    { key: 'total_deductions', header: 'Deductions', align: 'right', render: (row) => <Money value={row.total_deductions} currency={row.currency} /> },
    { key: 'net_amount', header: 'Net', align: 'right', render: (row) => <Money value={row.net_amount} currency={row.currency} /> },
    { key: 'status', header: 'Status', render: (row) => <StatusPill value={row.status} /> }
  ];

  function runAction() {
    if (!runId || !action) return;
    const done = () => { setAction(null); setReason(''); setForce(false); };
    if (action === 'compute') compute.mutate({ id: runId, reason: reason.trim() || undefined }, { onSuccess: done });
    if (action === 'finalize') finalize.mutate({ id: runId, reason: reason.trim() || undefined, force: force || undefined }, { onSuccess: done });
    if (action === 'lock') lock.mutate({ id: runId, reason: reason.trim() }, { onSuccess: done });
    if (action === 'unlock') unlock.mutate({ id: runId, reason: reason.trim() }, { onSuccess: done });
    if (action === 'pay') markPaid.mutate({ id: runId, body: { paid_on: paidOn, reason: reason.trim() || undefined } }, { onSuccess: done });
  }

  const reasonRequired = action === 'lock' || action === 'unlock';
  const canConfirm = Boolean(action) && !pending && (!reasonRequired || reason.trim().length > 0);

  if (run.isLoading) return <SkeletonList rows={6} />;
  if (run.error) return <ProblemAlert error={run.error} onRetry={() => void run.refetch()} />;
  if (!run.data) return null;

  const period = `${MONTHS[run.data.period_month - 1] ?? run.data.period_month} ${run.data.period_year}`;

  return (
    <div className="space-y-5">
      <PageHeader
        title={`Payroll run - ${period}`}
        description="Compute, finalize, lock and pay. Finalization makes every record immutable."
        actions={
          <Link href="/admin/payroll" className="text-sm font-medium text-primary hover:underline">
            Back to runs
          </Link>
        }
      />

      <Card>
        <CardBody className="flex flex-wrap items-center gap-3">
          <StatusPill value={run.data.status} />
          <span className="text-sm text-content-muted">Created {formatDateTime(run.data.created_at)}</span>
          {run.data.finalized_at ? <span className="text-sm text-content-muted">Finalized {formatDateTime(run.data.finalized_at)}</span> : null}
          {run.data.locked_at ? <span className="text-sm text-content-muted">Locked {formatDateTime(run.data.locked_at)}</span> : null}
          {run.data.paid_at ? <span className="text-sm text-content-muted">Paid {formatDateTime(run.data.paid_at)}</span> : null}
        </CardBody>
      </Card>

      {blockerList.length > 0 && run.data.status !== 'PAID' && run.data.status !== 'LOCKED' ? (
        <Alert tone="warning" title="Resolve these before finalizing">
          <ul className="list-inside list-disc">
            {blockerList.map((blocker, index) => (
              <li key={index}>{String(blocker.message ?? blocker.reason ?? JSON.stringify(blocker))}</li>
            ))}
          </ul>
        </Alert>
      ) : null}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Gross total" value={run.data.summary?.gross_total ? formatMoney(String(run.data.summary.gross_total), currency) : null} loading={run.isLoading} />
        <StatCard label="Deduction total" value={run.data.summary?.deduction_total ? formatMoney(String(run.data.summary.deduction_total), currency) : null} loading={run.isLoading} />
        <StatCard label="Net total" value={run.data.summary?.net_total ? formatMoney(String(run.data.summary.net_total), currency) : null} tone="success" loading={run.isLoading} />
        <StatCard label="Records" value={pickNumber(counts, ['total', 'TOTAL']) ?? records.data?.total_items ?? null} loading={run.isLoading} />
      </div>

      {counts ? (
        <Card>
          <CardHeader>
            <CardTitle as="h2">Records by status</CardTitle>
          </CardHeader>
          <CardBody className="flex flex-wrap gap-2">
            {Object.entries(counts).map(([key, value]) => (
              <Badge key={key} tone="neutral">
                {humanize(key)}: {value}
              </Badge>
            ))}
          </CardBody>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle as="h2">Run actions</CardTitle>
        </CardHeader>
        <CardBody className="flex flex-wrap gap-2">
          <PermissionGate anyOf={['salary.compute']}>
            <Button variant="secondary" disabled={run.data.status !== 'DRAFT' && run.data.status !== 'COMPUTED'} onClick={() => { setAction('compute'); setReason(''); }}>
              Compute
            </Button>
          </PermissionGate>
          <PermissionGate anyOf={['salary.finalize']}>
            <Button disabled={run.data.status !== 'COMPUTED'} onClick={() => { setAction('finalize'); setReason(''); setForce(false); }}>
              Finalize
            </Button>
          </PermissionGate>
          <PermissionGate anyOf={['payroll.lock']}>
            <Button variant="secondary" disabled={run.data.status !== 'FINALIZED'} onClick={() => { setAction('lock'); setReason(''); }}>
              Lock period
            </Button>
          </PermissionGate>
          <PermissionGate anyOf={['payroll.unlock']}>
            <Button variant="secondary" disabled={run.data.status !== 'LOCKED'} onClick={() => { setAction('unlock'); setReason(''); }}>
              Unlock
            </Button>
          </PermissionGate>
          <PermissionGate anyOf={['payroll.pay']}>
            <Button disabled={run.data.status !== 'FINALIZED' && run.data.status !== 'LOCKED'} onClick={() => { setAction('pay'); setReason(''); }}>
              Mark as paid
            </Button>
          </PermissionGate>
        </CardBody>
      </Card>

      <section className="space-y-3">
        <h2 className="text-base font-semibold">Salary records</h2>
        <DataTable
          columns={columns}
          rows={records.data?.items ?? []}
          getRowId={(row) => row.id}
          loading={records.isLoading}
          error={records.error ? <ProblemAlert error={records.error} onRetry={() => void records.refetch()} /> : undefined}
          onRowClick={(row) => setSelectedRecord(row)}
          emptyTitle="No records computed yet"
          emptyHint="Run compute to generate salary records for this period."
        />
        {records.data ? (
          <Pagination
            page={records.data.page}
            pageSize={records.data.page_size}
            totalItems={records.data.total_items}
            totalPages={records.data.total_pages}
            onPageChange={setRecordPage}
          />
        ) : null}
      </section>

      <Dialog
        open={Boolean(action)}
        onClose={() => setAction(null)}
        title={
          action === 'compute' ? 'Compute payroll'
            : action === 'finalize' ? 'Finalize payroll'
            : action === 'lock' ? 'Lock this period'
            : action === 'unlock' ? 'Unlock this period'
            : 'Mark payroll as paid'
        }
        footer={
          <>
            <Button variant="secondary" onClick={() => setAction(null)}>Cancel</Button>
            <Button
              variant={action === 'finalize' || action === 'lock' ? 'danger' : 'primary'}
              loading={pending}
              disabled={!canConfirm}
              onClick={runAction}
            >
              Confirm
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {finalize.error && action === 'finalize' ? <ProblemAlert error={finalize.error} /> : null}
          {lock.error && action === 'lock' ? <ProblemAlert error={lock.error} /> : null}
          {markPaid.error && action === 'pay' ? <ProblemAlert error={markPaid.error} /> : null}

          {action === 'finalize' ? (
            <Alert tone="danger" title="Finalization is not reversible.">
              Every salary record in this run becomes immutable. Later attendance corrections create an
              adjustment in the next open period instead of changing these numbers.
            </Alert>
          ) : null}
          {action === 'lock' ? <Alert tone="warning" title="Locking blocks further changes to this period." /> : null}
          {action === 'pay' ? (
            <TextField label="Paid on" name="paid_on" type="date" required value={paidOn} onChange={(event) => setPaidOn(event.target.value)} />
          ) : null}
          {action === 'pay' ? (
            <TextField label="Payment reference (optional)" name="payment_reference" value={reason} onChange={(event) => setReason(event.target.value)} />
          ) : (
            <TextAreaField
              label={reasonRequired ? 'Reason (required)' : 'Reason (optional)'}
              name="reason"
              required={reasonRequired}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          )}
          {action === 'finalize' ? (
            <PermissionGate anyOf={['ledger.entry.adjust']}>
              <CheckboxField
                label="Override pending attendance corrections (force)"
                checked={force}
                onChange={(event) => setForce(event.target.checked)}
                help="Only available with salary.finalize plus ledger.entry.adjust; the override is audited."
              />
            </PermissionGate>
          ) : null}
        </div>
      </Dialog>

      <Dialog
        open={Boolean(selectedRecord)}
        onClose={() => setSelectedRecord(null)}
        title={selectedRecord ? `Salary record - ${selectedRecord.employee?.full_name ?? selectedRecord.employee_id}` : 'Salary record'}
        description="Full breakdown so any number can be explained to the employee."
      >
        {selectedRecord ? (
          <div className="space-y-3 text-sm">
            <dl className="space-y-2">
              {[
                ['Compensation type', humanize(selectedRecord.compensation_type)],
                ['Base rate', formatMoney(selectedRecord.base_rate, selectedRecord.currency)],
                ['Payable days', selectedRecord.payable_days],
                ['Gross', formatMoney(selectedRecord.gross_amount, selectedRecord.currency)],
                ['Overtime', formatMoney(selectedRecord.overtime_amount, selectedRecord.currency)],
                ['Bonus', formatMoney(selectedRecord.bonus_amount, selectedRecord.currency)],
                ['Leave deduction', formatMoney(selectedRecord.leave_deduction, selectedRecord.currency)],
                ['Late deduction', formatMoney(selectedRecord.late_deduction, selectedRecord.currency)],
                ['Advance deduction', formatMoney(selectedRecord.advance_deduction, selectedRecord.currency)],
                ['Other deduction', formatMoney(selectedRecord.other_deduction, selectedRecord.currency)],
                ['Total deductions', formatMoney(selectedRecord.total_deductions, selectedRecord.currency)],
                ['Net pay', formatMoney(selectedRecord.net_amount, selectedRecord.currency)]
              ].map(([label, value]) => (
                <div key={label} className="flex justify-between gap-3">
                  <dt className="text-content-muted">{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
            <p className="break-all font-mono text-xs text-content-muted">
              Rule snapshot: {selectedRecord.rule_snapshot_hash}
            </p>
          </div>
        ) : null}
      </Dialog>
    </div>
  );
}