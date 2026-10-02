'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ApiError } from '@/lib/api-client';
import { describeProblem } from '@/lib/problem-details';
import { formatBusinessDate, formatDateTime, formatTime, humanize } from '@/lib/format';
import { useSession } from '@/features/auth/session';
import { useCreateCorrection, useMyAttendance, useMyCorrections, useCancelCorrection } from '@/features/attendance/hooks';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { TextField, TextAreaField, SelectField } from '@/components/ui/Form';
import { StatusPill } from '@/components/ui/StatusPill';
import { Alert } from '@/components/ui/Alert';
import { SkeletonList } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { ProblemAlert } from '@/components/ui/ProblemAlert';

const CORRECTION_TYPES = [
  { value: 'CHECK_IN_TIME', label: 'Check-in time was wrong' },
  { value: 'CHECK_OUT_TIME', label: 'Check-out time was wrong' },
  { value: 'BREAK_TIME', label: 'Break time was wrong' },
  { value: 'MISSING_CHECK_IN', label: 'Check-in is missing' },
  { value: 'MISSING_CHECK_OUT', label: 'Check-out is missing' }
];

/** Convert a local datetime-local value to an RFC 3339 UTC timestamp for the API. */
function toIso(local: string): string | null {
  if (!local) return null;
  const parsed = new Date(local);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString();
}

export default function MyCorrectionsPage() {
  const { settings } = useSession();
  const [statusFilter, setStatusFilter] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);

  const list = useMyCorrections(statusFilter ? { status: statusFilter } : {});
  const cancel = useCancelCorrection();

  const [date, setDate] = useState('');
  const [correctionType, setCorrectionType] = useState('CHECK_IN_TIME');
  const [checkInAt, setCheckInAt] = useState('');
  const [checkOutAt, setCheckOutAt] = useState('');
  const [reason, setReason] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  const nextDay = (() => {
    if (!date) return '';
    const parsed = new Date(`${date}T00:00:00Z`);
    if (Number.isNaN(parsed.getTime())) return '';
    parsed.setUTCDate(parsed.getUTCDate() + 1);
    return parsed.toISOString().slice(0, 10);
  })();

  const recordQuery = useMyAttendance(date ? { from: date, to: nextDay, page: 1 } : {});
  const record = date ? recordQuery.data?.items?.[0] ?? null : null;

  const create = useCreateCorrection();

  function resetForm() {
    setDate('');
    setCorrectionType('CHECK_IN_TIME');
    setCheckInAt('');
    setCheckOutAt('');
    setReason('');
    setFormError(null);
  }

  function submit() {
    setFormError(null);
    if (!date) {
      setFormError('Choose the date you want to correct.');
      return;
    }
    if (!record) {
      setFormError('There is no attendance record for that date, so a correction cannot be filed against it.');
      return;
    }
    if (reason.trim().length === 0) {
      setFormError('A reason is required.');
      return;
    }
    const needsCheckIn = correctionType === 'CHECK_IN_TIME' || correctionType === 'MISSING_CHECK_IN';
    const needsCheckOut = correctionType === 'CHECK_OUT_TIME' || correctionType === 'MISSING_CHECK_OUT';
    if (needsCheckIn && !checkInAt) {
      setFormError('Provide the correct check-in time.');
      return;
    }
    if (needsCheckOut && !checkOutAt) {
      setFormError('Provide the correct check-out time.');
      return;
    }

    create.mutate(
      {
        attendance_record_id: record.id,
        correction_type: correctionType,
        requested_check_in_at: needsCheckIn ? toIso(checkInAt) : null,
        requested_check_out_at: needsCheckOut ? toIso(checkOutAt) : null,
        reason: reason.trim()
      },
      {
        onSuccess: () => {
          setDialogOpen(false);
          resetForm();
        }
      }
    );
  }

  const createError = create.error instanceof ApiError ? create.error : null;

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">My corrections</h1>
          <p className="text-sm text-content-muted">Attendance values change only through an approved correction.</p>
        </div>
        <Link href="/app/attendance" className="flex min-h-touch items-center text-sm text-primary underline">
          Attendance
        </Link>
      </div>

      <div className="flex items-center gap-2">
        <SelectField
          label="Filter by status"
          name="status"
          containerClassName="w-48"
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value)}
          options={[
            { value: 'PENDING', label: 'Pending' },
            { value: 'APPROVED', label: 'Approved' },
            { value: 'REJECTED', label: 'Rejected' },
            { value: 'CANCELLED', label: 'Cancelled' }
          ]}
        />
        <Button className="mt-6" onClick={() => setDialogOpen(true)}>
          New request
        </Button>
      </div>

      {list.isLoading ? (
        <SkeletonList rows={4} />
      ) : list.error ? (
        <ProblemAlert error={list.error} onRetry={() => void list.refetch()} />
      ) : (list.data?.items.length ?? 0) === 0 ? (
        <EmptyState title="No correction requests" hint="If a punch is missing or wrong, request a correction here." />
      ) : (
        <ul className="space-y-2">
          {list.data?.items.map((correction) => (
            <li key={correction.id}>
              <Card>
                <CardHeader action={<StatusPill value={correction.status} />}>
                  <CardTitle>{humanize(correction.correction_type)}</CardTitle>
                  <p className="mt-0.5 text-xs text-content-muted">
                    {correction.record ? formatBusinessDate(correction.record.business_date) : ''} - filed {formatDateTime(correction.created_at, settings.business_timezone)}
                  </p>
                </CardHeader>
                <CardBody className="space-y-2 text-sm">
                  <p className="text-content-muted">{correction.reason}</p>
                  {correction.requested_check_in_at ? (
                    <p className="text-xs">Requested check-in: {formatTime(correction.requested_check_in_at, settings.business_timezone)}</p>
                  ) : null}
                  {correction.requested_check_out_at ? (
                    <p className="text-xs">Requested check-out: {formatTime(correction.requested_check_out_at, settings.business_timezone)}</p>
                  ) : null}
                  {correction.decision_notes ? <p className="text-xs text-content-muted">Decision note: {correction.decision_notes}</p> : null}
                  {correction.status === 'PENDING' ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      loading={cancel.isPending}
                      onClick={() => cancel.mutate({ id: correction.id, reason: 'Cancelled by employee' })}
                    >
                      Cancel request
                    </Button>
                  ) : null}
                </CardBody>
              </Card>
            </li>
          ))}
        </ul>
      )}

      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title="Request an attendance correction"
        description="The admin approves or rejects this against the stored evidence."
        footer={
          <>
            <Button variant="secondary" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={submit} loading={create.isPending} disabled={create.isPending}>
              Submit request
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {createError ? (
            <Alert tone="danger" title={describeProblem(createError.problem).title} nextStep={describeProblem(createError.problem).nextStep}>
              {createError.problem.detail ? <p>{createError.problem.detail}</p> : null}
            </Alert>
          ) : null}
          {formError ? <Alert tone="danger" title={formError} /> : null}

          <TextField
            label="Date to correct"
            type="date"
            name="correction_date"
            required
            value={date}
            onChange={(event) => setDate(event.target.value)}
          />

          {date && recordQuery.isSuccess && !record ? (
            <Alert tone="warning" title="No attendance record exists for that date." nextStep="Choose a date that has a recorded day." />
          ) : null}

          <SelectField
            label="What is wrong?"
            name="correction_type"
            value={correctionType}
            onChange={(event) => setCorrectionType(event.target.value)}
            options={CORRECTION_TYPES}
          />

          {correctionType === 'CHECK_IN_TIME' || correctionType === 'MISSING_CHECK_IN' ? (
            <TextField
              label="Correct check-in time"
              type="datetime-local"
              name="requested_check_in_at"
              value={checkInAt}
              onChange={(event) => setCheckInAt(event.target.value)}
            />
          ) : null}
          {correctionType === 'CHECK_OUT_TIME' || correctionType === 'MISSING_CHECK_OUT' ? (
            <TextField
              label="Correct check-out time"
              type="datetime-local"
              name="requested_check_out_at"
              value={checkOutAt}
              onChange={(event) => setCheckOutAt(event.target.value)}
            />
          ) : null}

          <TextAreaField
            label="Reason"
            name="reason"
            required
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            help="This is recorded in the audit trail."
          />
        </div>
      </Dialog>
    </div>
  );
}