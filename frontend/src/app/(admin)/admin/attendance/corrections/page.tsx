'use client';

import { useState } from 'react';
import { useCorrections, useDecideCorrection } from '@/features/attendance/hooks';
import { useSession } from '@/features/auth/session';
import { formatBusinessDate, formatDateTime, formatTime, humanize } from '@/lib/format';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { TextAreaField, SelectField } from '@/components/ui/Form';
import { StatusPill } from '@/components/ui/StatusPill';
import { SkeletonList } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { Pagination } from '@/components/ui/Pagination';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { Alert } from '@/components/ui/Alert';
import type { AttendanceCorrection } from '@/lib/types';

export default function AdminCorrectionsPage() {
  const { settings } = useSession();
  const [status, setStatus] = useState('PENDING');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<AttendanceCorrection | null>(null);
  const [action, setAction] = useState<'approve' | 'reject'>('approve');
  const [notes, setNotes] = useState('');

  const query = useCorrections({ status: status || undefined, page });
  const decide = useDecideCorrection();

  return (
    <div className="space-y-4">
      <PageHeader title="Correction queue" description="Compare the request with the stored evidence before deciding." />

      <Card>
        <CardBody className="flex flex-wrap items-end gap-3">
          <SelectField
            label="Status"
            name="status"
            containerClassName="w-48"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
            options={['PENDING', 'APPROVED', 'REJECTED', 'CANCELLED'].map((value) => ({ value, label: humanize(value) }))}
          />
          <Button variant="secondary" onClick={() => void query.refetch()}>
            Refresh
          </Button>
        </CardBody>
      </Card>

      {query.isLoading ? (
        <SkeletonList rows={4} />
      ) : query.error ? (
        <ProblemAlert error={query.error} onRetry={() => void query.refetch()} />
      ) : (query.data?.items.length ?? 0) === 0 ? (
        <EmptyState title="Nothing in this queue" hint="New correction requests will appear here." />
      ) : (
        <ul className="space-y-2">
          {query.data?.items.map((correction) => (
            <li key={correction.id}>
              <Card>
                <CardHeader action={<StatusPill value={correction.status} />}>
                  <CardTitle>
                    {correction.employee?.full_name ?? 'Employee'} - {humanize(correction.correction_type)}
                  </CardTitle>
                  <p className="mt-0.5 text-xs text-content-muted">
                    {correction.record ? formatBusinessDate(correction.record.business_date) : ''} - filed{' '}
                    {formatDateTime(correction.created_at, settings.business_timezone)}
                  </p>
                </CardHeader>
                <CardBody className="space-y-3 text-sm">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="rounded-md border border-surface-border p-3">
                      <p className="text-xs font-semibold uppercase text-content-muted">Original</p>
                      <p>In: {formatTime(correction.record?.first_check_in_at ?? null, settings.business_timezone)}</p>
                      <p>Out: {formatTime(correction.record?.last_check_out_at ?? null, settings.business_timezone)}</p>
                    </div>
                    <div className="rounded-md border border-primary/40 bg-primary-soft p-3">
                      <p className="text-xs font-semibold uppercase text-primary">Requested</p>
                      <p>In: {formatTime(correction.requested_check_in_at, settings.business_timezone)}</p>
                      <p>Out: {formatTime(correction.requested_check_out_at, settings.business_timezone)}</p>
                    </div>
                  </div>
                  <p className="text-content-muted">Reason: {correction.reason}</p>
                  {correction.decision_notes ? <p className="text-xs text-content-muted">Decision note: {correction.decision_notes}</p> : null}
                  {correction.status === 'PENDING' ? (
                    <div className="flex flex-wrap gap-2">
                      <Button
                        onClick={() => {
                          setSelected(correction);
                          setAction('approve');
                          setNotes('');
                        }}
                      >
                        Approve
                      </Button>
                      <Button
                        variant="danger"
                        onClick={() => {
                          setSelected(correction);
                          setAction('reject');
                          setNotes('');
                        }}
                      >
                        Reject
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
        title={action === 'approve' ? 'Approve correction' : 'Reject correction'}
        description="Approving records a CORRECTION event, recomputes the day and audits the before/after values."
        footer={
          <>
            <Button variant="secondary" onClick={() => setSelected(null)}>
              Cancel
            </Button>
            <Button
              variant={action === 'reject' ? 'danger' : 'primary'}
              loading={decide.isPending}
              disabled={(action === 'reject' && notes.trim().length === 0) || decide.isPending}
              onClick={() => {
                if (!selected) return;
                decide.mutate(
                  { id: selected.id, action, notes: notes.trim() },
                  {
                    onSuccess: () => {
                      setSelected(null);
                      setNotes('');
                    }
                  }
                );
              }}
            >
              {action === 'approve' ? 'Approve' : 'Reject'}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {decide.error ? <ProblemAlert error={decide.error} testId="correction-decision-error" /> : null}
          {action === 'approve' ? (
            <Alert tone="info" title="The payroll period must not be locked." nextStep="A locked period rejects the approval and requires an adjustment instead." />
          ) : null}
          <TextAreaField
            label={action === 'reject' ? 'Decision notes (required)' : 'Decision notes'}
            name="decision_notes"
            required={action === 'reject'}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>
      </Dialog>
    </div>
  );
}