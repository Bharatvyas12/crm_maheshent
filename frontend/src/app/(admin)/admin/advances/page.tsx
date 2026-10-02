'use client';

import { useState } from 'react';
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
import { Alert } from '@/components/ui/Alert';
import {
  useAddAdvanceRepayment,
  useAdvance,
  useAdvances,
  useCreateAdvance,
  useDecideAdvance,
  useWriteOffAdvance
} from '@/features/ledger/hooks';
import { useEmployees } from '@/features/employees/hooks';
import { formatBusinessDate, formatMoney, humanize } from '@/lib/format';
import type { Advance } from '@/lib/types';

const REPAYMENT_MODES = ['SALARY_DEDUCTION', 'CASH', 'MIXED'] as const;

export default function AdminAdvancesPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [employeeId, setEmployeeId] = useState('');

  const query = useAdvances({ status: status || undefined, employee_id: employeeId || undefined, page });
  const employees = useEmployees({ page_size: 100 });
  const create = useCreateAdvance();
  const decide = useDecideAdvance();
  const repay = useAddAdvanceRepayment();
  const writeOff = useWriteOffAdvance();

  const [selected, setSelected] = useState<Advance | null>(null);
  const detail = useAdvance(selected?.id ?? '');
  const [issueOpen, setIssueOpen] = useState(false);
  const [decision, setDecision] = useState<'approve' | 'reject' | null>(null);
  const [repayOpen, setRepayOpen] = useState(false);
  const [writeOffOpen, setWriteOffOpen] = useState(false);
  const [notes, setNotes] = useState('');
  const [repayForm, setRepayForm] = useState({ amount: '', business_date: new Date().toISOString().slice(0, 10), reason: '' });
  const [issueForm, setIssueForm] = useState({
    employee_id: '',
    amount: '',
    currency: 'INR',
    issued_on: new Date().toISOString().slice(0, 10),
    reason: '',
    repayment_mode: 'SALARY_DEDUCTION',
    installment_count: ''
  });

  const issueInvalid = !issueForm.employee_id || !issueForm.amount || !issueForm.reason.trim();

  const columns: Array<Column<Advance>> = [
    { key: 'employee', header: 'Employee', render: (row) => row.employee?.full_name ?? row.employee_id.slice(0, 8) },
    { key: 'amount', header: 'Issued', align: 'right', render: (row) => formatMoney(row.amount, row.currency) },
    { key: 'outstanding_amount', header: 'Outstanding', align: 'right', render: (row) => formatMoney(row.outstanding_amount, row.currency) },
    { key: 'issued_on', header: 'Issued on', render: (row) => formatBusinessDate(row.issued_on) },
    { key: 'repayment_mode', header: 'Recovery', render: (row) => humanize(row.repayment_mode) },
    { key: 'installment_count', header: 'Installments', align: 'right', render: (row) => row.installment_count ?? '-' },
    { key: 'status', header: 'Status', render: (row) => <StatusPill value={row.status} /> }
  ];

  return (
    <div className="space-y-5">
      <PageHeader
        title="Advances"
        description="Issue advances, approve them and record recovery. The server enforces the outstanding cap."
        actions={
          <PermissionGate anyOf={['advance.create']}>
            <Button onClick={() => setIssueOpen(true)}>Issue advance</Button>
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
            options={['PENDING_APPROVAL', 'OUTSTANDING', 'CLOSED', 'WRITTEN_OFF', 'CANCELLED'].map((value) => ({ value, label: humanize(value) }))}
          />
          <SelectField
            label="Employee"
            name="employee_id"
            placeholder="Any"
            value={employeeId}
            onChange={(event) => { setEmployeeId(event.target.value); setPage(1); }}
            options={(employees.data?.items ?? []).map((employee) => ({ value: employee.id, label: `${employee.full_name} (${employee.employee_code})` }))}
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
        emptyTitle="No advances"
        emptyHint="Issued advances and their recovery schedule appear here."
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
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title={selected ? `Advance for ${selected.employee?.full_name ?? selected.employee_id}` : 'Advance'}
        footer={
          selected ? (
            <div className="flex flex-wrap gap-2">
              {selected.status === 'PENDING_APPROVAL' ? (
                <>
                  <PermissionGate anyOf={['advance.approve']}>
                    <Button onClick={() => { setDecision('approve'); setNotes(''); }}>Approve</Button>
                  </PermissionGate>
                  <PermissionGate anyOf={['advance.approve']}>
                    <Button variant="danger" onClick={() => { setDecision('reject'); setNotes(''); }}>Reject</Button>
                  </PermissionGate>
                </>
              ) : null}
              {selected.status === 'OUTSTANDING' ? (
                <PermissionGate anyOf={['ledger.entry.create']}>
                  <Button variant="secondary" onClick={() => { setRepayOpen(true); setRepayForm({ amount: selected.outstanding_amount, business_date: new Date().toISOString().slice(0, 10), reason: '' }); }}>
                    Record cash repayment
                  </Button>
                </PermissionGate>
              ) : null}
              {selected.status === 'OUTSTANDING' ? (
                <PermissionGate allOf={['advance.approve', 'ledger.entry.adjust']}>
                  <Button variant="danger" onClick={() => { setWriteOffOpen(true); setNotes(''); }}>Write off</Button>
                </PermissionGate>
              ) : null}
            </div>
          ) : null
        }
      >
        {selected ? (
          <div className="space-y-3 text-sm">
            <dl className="space-y-2">
              <div className="flex justify-between gap-3"><dt className="text-content-muted">Issued</dt><dd>{formatMoney(selected.amount, selected.currency)}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-content-muted">Outstanding</dt><dd>{formatMoney(selected.outstanding_amount, selected.currency)}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-content-muted">Reason</dt><dd className="text-right">{selected.reason}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-content-muted">Status</dt><dd><StatusPill value={selected.status} /></dd></div>
            </dl>
            {detail.data?.installments?.length ? (
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-content-muted">Installments</p>
                <ul className="space-y-1">
                  {detail.data.installments.map((installment) => (
                    <li key={installment.id} className="flex items-center justify-between gap-2 rounded border border-surface-border px-2 py-1">
                      <span>#{installment.installment_no} - due {formatBusinessDate(installment.due_on)}</span>
                      <span className="flex items-center gap-2">
                        <span>{formatMoney(installment.amount, selected.currency)}</span>
                        <StatusPill value={installment.status} />
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
      </Dialog>

      <Dialog
        open={issueOpen}
        onClose={() => setIssueOpen(false)}
        title="Issue an advance"
        description="The server validates the outstanding cap and the installment pattern before accepting this."
        footer={
          <>
            <Button variant="secondary" onClick={() => setIssueOpen(false)}>Cancel</Button>
            <Button
              loading={create.isPending}
              disabled={issueInvalid || create.isPending}
              onClick={() =>
                create.mutate(
                  {
                    employee_id: issueForm.employee_id,
                    amount: issueForm.amount,
                    currency: issueForm.currency,
                    issued_on: issueForm.issued_on,
                    reason: issueForm.reason.trim(),
                    repayment_mode: issueForm.repayment_mode,
                    installment_count: issueForm.installment_count ? Number(issueForm.installment_count) : undefined
                  },
                  { onSuccess: () => setIssueOpen(false) }
                )
              }
            >
              Issue
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {create.error ? <ProblemAlert error={create.error} /> : null}
          <SelectField
            label="Employee"
            name="employee_id"
            required
            value={issueForm.employee_id}
            onChange={(event) => setIssueForm({ ...issueForm, employee_id: event.target.value })}
            options={(employees.data?.items ?? []).map((employee) => ({ value: employee.id, label: `${employee.full_name} (${employee.employee_code})` }))}
          />
          <TextField label="Amount" name="amount" required inputMode="decimal" value={issueForm.amount} onChange={(event) => setIssueForm({ ...issueForm, amount: event.target.value })} />
          <TextField label="Currency" name="currency" required value={issueForm.currency} onChange={(event) => setIssueForm({ ...issueForm, currency: event.target.value })} />
          <TextField label="Issued on" name="issued_on" type="date" required value={issueForm.issued_on} onChange={(event) => setIssueForm({ ...issueForm, issued_on: event.target.value })} />
          <SelectField
            label="Repayment mode"
            name="repayment_mode"
            required
            value={issueForm.repayment_mode}
            onChange={(event) => setIssueForm({ ...issueForm, repayment_mode: event.target.value })}
            options={REPAYMENT_MODES.map((mode) => ({ value: mode, label: humanize(mode) }))}
          />
          <TextField
            label="Installment count"
            name="installment_count"
            type="number"
            help="Leave blank to let the server use the configured default."
            value={issueForm.installment_count}
            onChange={(event) => setIssueForm({ ...issueForm, installment_count: event.target.value })}
          />
          <TextAreaField label="Reason" name="reason" required value={issueForm.reason} onChange={(event) => setIssueForm({ ...issueForm, reason: event.target.value })} />
        </div>
      </Dialog>

      <Dialog
        open={Boolean(decision)}
        onClose={() => setDecision(null)}
        title={decision === 'approve' ? 'Approve advance' : 'Reject advance'}
        footer={
          <>
            <Button variant="secondary" onClick={() => setDecision(null)}>Cancel</Button>
            <Button
              variant={decision === 'reject' ? 'danger' : 'primary'}
              loading={decide.isPending}
              disabled={decision === 'reject' && !notes.trim()}
              onClick={() => {
                if (!selected || !decision) return;
                decide.mutate(
                  { id: selected.id, action: decision, notes: notes.trim() || undefined },
                  { onSuccess: () => { setDecision(null); setSelected(null); } }
                );
              }}
            >
              Confirm
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Alert tone="info" title="Self-approval is not permitted.">The server rejects a decision made by the requester.</Alert>
          <TextAreaField
            label={decision === 'reject' ? 'Decision notes (required)' : 'Decision notes (optional)'}
            name="notes"
            required={decision === 'reject'}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
        </div>
      </Dialog>

      <Dialog
        open={repayOpen}
        onClose={() => setRepayOpen(false)}
        title="Record a cash repayment"
        description="A cash repayment posts an ADVANCE_REPAYMENT ledger entry and can never exceed the outstanding amount."
        footer={
          <>
            <Button variant="secondary" onClick={() => setRepayOpen(false)}>Cancel</Button>
            <Button
              loading={repay.isPending}
              disabled={!repayForm.amount || !repayForm.reason.trim() || repay.isPending}
              onClick={() => {
                if (!selected) return;
                repay.mutate(
                  { id: selected.id, body: repayForm },
                  { onSuccess: () => { setRepayOpen(false); setSelected(null); } }
                );
              }}
            >
              Record repayment
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {repay.error ? <ProblemAlert error={repay.error} /> : null}
          <TextField label="Amount" name="amount" required inputMode="decimal" value={repayForm.amount} onChange={(event) => setRepayForm({ ...repayForm, amount: event.target.value })} />
          <TextField label="Business date" name="business_date" type="date" required value={repayForm.business_date} onChange={(event) => setRepayForm({ ...repayForm, business_date: event.target.value })} />
          <TextAreaField label="Reason" name="reason" required value={repayForm.reason} onChange={(event) => setRepayForm({ ...repayForm, reason: event.target.value })} />
        </div>
      </Dialog>

      <Dialog
        open={writeOffOpen}
        onClose={() => setWriteOffOpen(false)}
        title="Write off this advance"
        description="Write-off closes the advance as WRITTEN_OFF with a required reason and is audited."
        footer={
          <>
            <Button variant="secondary" onClick={() => setWriteOffOpen(false)}>Cancel</Button>
            <Button
              variant="danger"
              loading={writeOff.isPending}
              disabled={!notes.trim() || writeOff.isPending}
              onClick={() => {
                if (!selected) return;
                writeOff.mutate({ id: selected.id, body: { reason: notes.trim() } }, { onSuccess: () => { setWriteOffOpen(false); setSelected(null); } });
              }}
            >
              Confirm write-off
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {writeOff.error ? <ProblemAlert error={writeOff.error} /> : null}
          <TextAreaField label="Reason" name="reason" required value={notes} onChange={(event) => setNotes(event.target.value)} />
        </div>
      </Dialog>
    </div>
  );
}