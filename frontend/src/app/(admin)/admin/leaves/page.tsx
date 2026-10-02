'use client';

import { Suspense, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useDecideLeave, useLeaveTypes, useLeaves } from '@/features/leaves/hooks';
import { useEmployees } from '@/features/employees/hooks';
import { formatDateRange, formatDateTime, humanize } from '@/lib/format';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { TextAreaField, SelectField, TextField } from '@/components/ui/Form';
import { StatusPill } from '@/components/ui/StatusPill';
import { SkeletonList } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { Pagination } from '@/components/ui/Pagination';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import type { Leave } from '@/lib/types';

function LeaveQueue() {
  const searchParams = useSearchParams();
  const [status, setStatus] = useState(searchParams.get('status') ?? 'PENDING');
  const [leaveTypeId, setLeaveTypeId] = useState('');
  const [employeeId, setEmployeeId] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Leave | null>(null);
  const [action, setAction] = useState<'approve' | 'reject' | 'request-modification'>('approve');
  const [notes, setNotes] = useState('');

  const types = useLeaveTypes(true);
  const employees = useEmployees({ page: 1, page_size: 100 });
  const query = useLeaves({
    status: status || undefined,
    leave_type_id: leaveTypeId || undefined,
    employee_id: employeeId || undefined,
    from: from || undefined,
    to: to || undefined,
    page
  });
  const decide = useDecideLeave();

  return (
    <div className="space-y-4">
      <PageHeader
        title="Leave queue"
        description="Approve, reject or request modification. Self-approval is rejected by the server."
        actions={
          <Link href="/admin/leave-balances" className="inline-flex min-h-touch items-center rounded-md border border-surface-border px-4 text-sm font-medium">
            Balances
          </Link>
        }
      />

      <Card>
        <CardBody className="grid gap-3 md:grid-cols-3 lg:grid-cols-6">
          <SelectField
            label="Status"
            name="status"
            placeholder="Any"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
            options={['PENDING', 'APPROVED', 'REJECTED', 'MODIFICATION_REQUESTED', 'CANCELLED'].map((value) => ({ value, label: humanize(value) }))}
          />
          <SelectField
            label="Leave type"
            name="leave_type_id"
            placeholder="Any"
            value={leaveTypeId}
            onChange={(e) => {
              setLeaveTypeId(e.target.value);
              setPage(1);
            }}
            options={(types.data?.items ?? []).map((type) => ({ value: type.id, label: type.name }))}
          />
          <SelectField
            label="Employee"
            name="employee_id"
            placeholder="Any"
            value={employeeId}
            onChange={(e) => {
              setEmployeeId(e.target.value);
              setPage(1);
            }}
            options={(employees.data?.items ?? []).map((employee) => ({ value: employee.id, label: `${employee.full_name} (${employee.employee_code})` }))}
          />
          <TextField label="From" type="date" name="from" value={from} onChange={(e) => setFrom(e.target.value)} />
          <TextField label="To" type="date" name="to" value={to} onChange={(e) => setTo(e.target.value)} />
          <TextField label="Search" name="q" value="" onChange={() => undefined} disabled />
        </CardBody>
      </Card>

      {query.isLoading ? (
        <SkeletonList rows={4} />
      ) : query.error ? (
        <ProblemAlert error={query.error} onRetry={() => void query.refetch()} />
      ) : (query.data?.items.length ?? 0) === 0 ? (
        <EmptyState title="No leave requests" hint="Requests appear here as employees apply." />
      ) : (
        <ul className="space-y-2">
          {query.data?.items.map((leave) => (
            <li key={leave.id}>
              <Card>
                <CardHeader action={<StatusPill value={leave.status} />}>
                  <CardTitle>
                    {leave.employee?.full_name ?? 'Employee'} - {leave.leave_type?.name ?? 'Leave'}
                  </CardTitle>
                  <p className="mt-0.5 text-xs text-content-muted">
                    {formatDateRange(leave.start_date, leave.end_date)} - {leave.total_days} day(s) - filed{' '}
                    {formatDateTime(leave.created_at)}
                  </p>
                </CardHeader>
                <CardBody className="space-y-2 text-sm">
                  <p className="text-content-muted">{leave.reason}</p>
                  {leave.decision_notes ? <p className="text-xs text-content-muted">Decision note: {leave.decision_notes}</p> : null}
                  {leave.status === 'PENDING' || leave.status === 'MODIFICATION_REQUESTED' ? (
                    <div className="flex flex-wrap gap-2">
                      <Button onClick={() => { setSelected(leave); setAction('approve'); setNotes(''); }}>Approve</Button>
                      <Button variant="danger" onClick={() => { setSelected(leave); setAction('reject'); setNotes(''); }}>
                        Reject
                      </Button>
                      <Button variant="secondary" onClick={() => { setSelected(leave); setAction('request-modification'); setNotes(''); }}>
                        Request modification
                      </Button>
                    </div>
                  ) : null}
                </CardBody>
              </Card>
            </li>
          ))}
        </ul>
      )}

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
        title={
          action === 'approve' ? 'Approve leave' : action === 'reject' ? 'Reject leave' : 'Request modification'
        }
        description="Approval converts the pending hold into usage against the balance."
        footer={
          <>
            <Button variant="secondary" onClick={() => setSelected(null)}>
              Cancel
            </Button>
            <Button
              variant={action === 'reject' ? 'danger' : 'primary'}
              loading={decide.isPending}
              disabled={(action !== 'approve' && notes.trim().length === 0) || decide.isPending}
              onClick={() => {
                if (!selected) return;
                decide.mutate(
                  { id: selected.id, action, notes: notes.trim() || undefined },
                  {
                    onSuccess: () => {
                      setSelected(null);
                      setNotes('');
                    }
                  }
                );
              }}
            >
              Confirm
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {decide.error ? <ProblemAlert error={decide.error} testId="leave-decision-error" /> : null}
          <TextAreaField
            label={action === 'approve' ? 'Decision notes (optional)' : 'Decision notes (required)'}
            name="decision_notes"
            required={action !== 'approve'}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>
      </Dialog>
    </div>
  );
}

export default function AdminLeavesPage() {
  return (
    <Suspense fallback={<div className="h-40" />}>
      <LeaveQueue />
    </Suspense>
  );
}