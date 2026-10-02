'use client';

import { useState } from 'react';
import { ApiError } from '@/lib/api-client';
import { describeProblem } from '@/lib/problem-details';
import { formatBusinessDate, formatDateRange, humanize } from '@/lib/format';
import { useApplyLeave, useCancelLeave, useLeaveTypes, useMyLeaveBalances, useMyLeaves } from '@/features/leaves/hooks';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { TextField, TextAreaField, SelectField, CheckboxField } from '@/components/ui/Form';
import { StatusPill } from '@/components/ui/StatusPill';
import { SkeletonList } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { Alert } from '@/components/ui/Alert';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { FileUploadField, type UploadedFile } from '@/components/FileUploadField';

function calendarDays(start: string, end: string): number | null {
  if (!start || !end) return null;
  const from = new Date(`${start}T00:00:00Z`);
  const to = new Date(`${end}T00:00:00Z`);
  if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime()) || to < from) return null;
  return Math.round((to.getTime() - from.getTime()) / 86_400_000) + 1;
}

export default function EmployeeLeavesPage() {
  const types = useLeaveTypes();
  const balances = useMyLeaveBalances();
  const leaves = useMyLeaves({});
  const apply = useApplyLeave();
  const cancel = useCancelLeave();

  const balanceList = balances.data?.items ?? [];
  const typeList = types.data?.items ?? [];

  const [open, setOpen] = useState(false);
  const [breakdownFor, setBreakdownFor] = useState<string | null>(null);
  const [leaveTypeId, setLeaveTypeId] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [isHalfDay, setIsHalfDay] = useState(false);
  const [halfDayPeriod, setHalfDayPeriod] = useState('FIRST_HALF');
  const [reason, setReason] = useState('');
  const [attachment, setAttachment] = useState<UploadedFile[]>([]);
  const [formError, setFormError] = useState<string | null>(null);

  const selectedType = typeList.find((type) => type.id === leaveTypeId) ?? null;
  const span = calendarDays(startDate, endDate);
  const applyError = apply.error instanceof ApiError ? apply.error : null;

  function resetForm() {
    setLeaveTypeId('');
    setStartDate('');
    setEndDate('');
    setIsHalfDay(false);
    setReason('');
    setAttachment([]);
    setFormError(null);
  }

  function submit() {
    setFormError(null);
    if (!leaveTypeId) return setFormError('Choose a leave type.');
    if (!startDate || !endDate) return setFormError('Choose the start and end dates.');
    if (span === null) return setFormError('The end date must be on or after the start date.');
    if (reason.trim().length === 0) return setFormError('A reason is required.');
    if (isHalfDay && span !== 1) return setFormError('A half day must be a single day.');

    apply.mutate(
      {
        leave_type_id: leaveTypeId,
        start_date: startDate,
        end_date: endDate,
        is_half_day: isHalfDay || undefined,
        half_day_period: isHalfDay ? halfDayPeriod : undefined,
        reason: reason.trim(),
        attachment_file_id: attachment[0]?.id ?? null
      },
      {
        onSuccess: () => {
          setOpen(false);
          resetForm();
        }
      }
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Leave</h1>
          <p className="text-sm text-content-muted">Balances, requests and decisions.</p>
        </div>
        <Button className="mt-1" onClick={() => setOpen(true)}>
          Apply
        </Button>
      </div>

      <section className="space-y-2">
        <h2 className="text-base font-semibold">Balances</h2>
        {balances.isLoading ? (
          <SkeletonList rows={2} />
        ) : balances.error ? (
          <ProblemAlert error={balances.error} onRetry={() => void balances.refetch()} />
        ) : balanceList.length === 0 ? (
          <EmptyState title="No leave balances yet" hint="Balances appear once the admin configures leave types." />
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            {balanceList.map((balance) => (
              <Card key={balance.id}>
                <CardBody className="space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold">{balance.leave_type?.name ?? 'Leave'}</p>
                    <span className="text-lg font-semibold text-primary">{balance.available_days}</span>
                  </div>
                  <p className="text-xs text-content-muted">Available days - {balance.period_year}</p>
                  <Button variant="link" size="sm" onClick={() => setBreakdownFor(breakdownFor === balance.id ? null : balance.id)}>
                    {breakdownFor === balance.id ? 'Hide calculation' : 'How it is calculated'}
                  </Button>
                  {breakdownFor === balance.id ? (
                    <dl className="grid grid-cols-2 gap-1 text-xs">
                      <dt className="text-content-muted">Entitled</dt>
                      <dd>{balance.entitled_days}</dd>
                      <dt className="text-content-muted">Accrued</dt>
                      <dd>{balance.accrued_days}</dd>
                      <dt className="text-content-muted">Used</dt>
                      <dd>{balance.used_days}</dd>
                      <dt className="text-content-muted">Pending</dt>
                      <dd>{balance.pending_days}</dd>
                      <dt className="text-content-muted">Carried forward</dt>
                      <dd>{balance.carried_forward_days}</dd>
                      <dt className="text-content-muted">Adjustments</dt>
                      <dd>{balance.adjustment_days}</dd>
                    </dl>
                  ) : null}
                </CardBody>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="text-base font-semibold">My requests</h2>
        {leaves.isLoading ? (
          <SkeletonList rows={3} />
        ) : leaves.error ? (
          <ProblemAlert error={leaves.error} onRetry={() => void leaves.refetch()} />
        ) : (leaves.data?.items.length ?? 0) === 0 ? (
          <EmptyState title="No leave requests" hint="Apply for leave and track the decision here." />
        ) : (
          <ul className="space-y-2">
            {leaves.data?.items.map((leave) => (
              <li key={leave.id}>
                <Card>
                  <CardHeader action={<StatusPill value={leave.status} />}>
                    <CardTitle>{leave.leave_type?.name ?? 'Leave'}</CardTitle>
                    <p className="mt-0.5 text-xs text-content-muted">
                      {formatDateRange(leave.start_date, leave.end_date)} - {leave.total_days} day(s)
                    </p>
                  </CardHeader>
                  <CardBody className="space-y-2 text-sm">
                    <p className="text-content-muted">{leave.reason}</p>
                    {leave.decision_notes ? <p className="text-xs">Decision note: {leave.decision_notes}</p> : null}
                    {leave.status === 'PENDING' ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        loading={cancel.isPending}
                        onClick={() => cancel.mutate({ id: leave.id, reason: 'Withdrawn by employee' })}
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
      </section>

      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Apply for leave"
        description="The server validates balances, overlaps and policy limits."
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={submit} loading={apply.isPending} disabled={apply.isPending}>
              Submit request
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {applyError ? (
            <Alert tone="danger" title={describeProblem(applyError.problem).title} nextStep={describeProblem(applyError.problem).nextStep}>
              {applyError.problem.detail ? <p>{applyError.problem.detail}</p> : null}
            </Alert>
          ) : null}
          {formError ? <Alert tone="danger" title={formError} /> : null}

          <SelectField
            label="Leave type"
            name="leave_type_id"
            required
            placeholder="Select a leave type"
            value={leaveTypeId}
            onChange={(event) => {
              setLeaveTypeId(event.target.value);
              const type = typeList.find((item) => item.id === event.target.value);
              if (!type?.allow_half_day) setIsHalfDay(false);
            }}
            options={typeList.map((type) => ({ value: type.id, label: type.name }))}
          />

          <div className="grid grid-cols-2 gap-3">
            <TextField label="Start date" type="date" name="start_date" required value={startDate} onChange={(event) => setStartDate(event.target.value)} />
            <TextField label="End date" type="date" name="end_date" required value={endDate} onChange={(event) => setEndDate(event.target.value)} />
          </div>

          {span !== null ? (
            <p className="text-xs text-content-muted">
              {span} calendar day(s) selected. The server calculates the payable day count, excluding weekly offs and holidays.
            </p>
          ) : null}

          {selectedType?.allow_half_day ? (
            <>
              <CheckboxField label="This is a half day" checked={isHalfDay} onChange={(event) => setIsHalfDay(event.target.checked)} />
              {isHalfDay ? (
                <SelectField
                  label="Which half?"
                  name="half_day_period"
                  value={halfDayPeriod}
                  onChange={(event) => setHalfDayPeriod(event.target.value)}
                  options={[
                    { value: 'FIRST_HALF', label: 'First half' },
                    { value: 'SECOND_HALF', label: 'Second half' }
                  ]}
                />
              ) : null}
            </>
          ) : null}

          <TextAreaField label="Reason" name="reason" required value={reason} onChange={(event) => setReason(event.target.value)} />

          <FileUploadField
            purpose="LEAVE_ATTACHMENT"
            label="Attachment (only if required or helpful)"
            accept="image/*,.pdf"
            onUploaded={setAttachment}
          />

          {selectedType?.requires_attachment_after_days ? (
            <p className="text-xs text-content-muted">
              Attachments are required for requests longer than {selectedType.requires_attachment_after_days} day(s).
            </p>
          ) : null}
        </div>
      </Dialog>

      {leaves.data?.items.length ? <p className="sr-only">Leave history loaded</p> : null}
      <p className="text-xs text-content-muted">
        Leave types available: {(types.data?.items ?? []).map((type) => humanize(type.name)).join(', ') || 'none configured'}
      </p>
    </div>
  );
}