'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { useAttendanceEvents, useAttendanceRecord, useAttendanceVerifications, useRecomputeAttendance } from '@/features/attendance/hooks';
import { useSession } from '@/features/auth/session';
import { formatBusinessDate, formatDateTime, formatDuration, formatTime, humanize } from '@/lib/format';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { StatusPill } from '@/components/ui/StatusPill';
import { SkeletonList } from '@/components/ui/Skeleton';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { Alert } from '@/components/ui/Alert';
import { Dialog } from '@/components/ui/Dialog';
import { TextAreaField } from '@/components/ui/Form';
import { PermissionGate } from '@/components/PermissionGate';

export default function AdminAttendanceDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? '';
  const { settings } = useSession();

  const record = useAttendanceRecord(id);
  const events = useAttendanceEvents(id);
  const verifications = useAttendanceVerifications(id);
  const recompute = useRecomputeAttendance();

  const [recomputeOpen, setRecomputeOpen] = useState(false);
  const [reason, setReason] = useState('');

  if (record.isLoading) return <SkeletonList rows={4} />;
  if (record.error) return <ProblemAlert error={record.error} onRetry={() => void record.refetch()} />;
  if (!record.data) return null;

  const data = record.data;

  return (
    <div className="space-y-4">
      <Link href="/admin/attendance" className="inline-block text-sm text-primary underline">
        Back to register
      </Link>

      <PageHeader
        title={`${data.employee?.full_name ?? 'Employee'} - ${formatBusinessDate(data.business_date)}`}
        description="Recorded events and the verification evidence behind them."
        actions={
          <PermissionGate anyOf={['attendance.manage']}>
            <Button variant="secondary" onClick={() => setRecomputeOpen(true)}>
              Recompute
            </Button>
          </PermissionGate>
        }
      />

      <Card>
        <CardHeader action={<StatusPill value={data.status} />}>
          <CardTitle as="h2">Summary</CardTitle>
          <p className="mt-0.5 text-xs text-content-muted">{humanize(data.day_classification)}</p>
        </CardHeader>
        <CardBody>
          <dl className="grid grid-cols-2 gap-3 text-sm lg:grid-cols-4">
            <div>
              <dt className="text-xs text-content-muted">First check-in</dt>
              <dd>{formatTime(data.first_check_in_at, settings.business_timezone)}</dd>
            </div>
            <div>
              <dt className="text-xs text-content-muted">Last check-out</dt>
              <dd>{formatTime(data.last_check_out_at, settings.business_timezone)}</dd>
            </div>
            <div>
              <dt className="text-xs text-content-muted">Worked</dt>
              <dd>{formatDuration(data.worked_seconds)}</dd>
            </div>
            <div>
              <dt className="text-xs text-content-muted">Unpaid break</dt>
              <dd>{formatDuration(data.unpaid_break_seconds)}</dd>
            </div>
            <div>
              <dt className="text-xs text-content-muted">Overtime</dt>
              <dd>{formatDuration(data.overtime_seconds)}</dd>
            </div>
            <div>
              <dt className="text-xs text-content-muted">Late / early</dt>
              <dd>
                {data.late_minutes} / {data.early_checkout_minutes} min
              </dd>
            </div>
            <div>
              <dt className="text-xs text-content-muted">Computed at</dt>
              <dd>{formatDateTime(data.computed_at, settings.business_timezone)}</dd>
            </div>
            <div>
              <dt className="text-xs text-content-muted">Version</dt>
              <dd>{data.version}</dd>
            </div>
          </dl>
        </CardBody>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle as="h2">Event timeline</CardTitle>
          </CardHeader>
          <CardBody>
            {events.isLoading ? (
              <SkeletonList rows={3} />
            ) : events.error ? (
              <ProblemAlert error={events.error} onRetry={() => void events.refetch()} />
            ) : (events.data?.items?.length ?? 0) === 0 ? (
              <p className="text-sm text-content-muted">No events.</p>
            ) : (
              <ol className="space-y-2 text-sm">
                {events.data?.items?.map((event) => (
                  <li key={event.id} className="flex items-center justify-between gap-3 border-b border-surface-border/60 pb-2 last:border-0">
                    <span>
                      <span className="font-medium">{humanize(event.event_type)}</span>
                      {event.is_manual ? <span className="ml-2 rounded bg-warning-soft px-1.5 py-0.5 text-xs text-warning">Manual</span> : null}
                    </span>
                    <span className="text-content-muted">{formatTime(event.occurred_at, settings.business_timezone)}</span>
                  </li>
                ))}
              </ol>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle as="h2">Verification evidence</CardTitle>
          </CardHeader>
          <CardBody>
            {verifications.isLoading ? (
              <SkeletonList rows={3} />
            ) : verifications.error ? (
              <ProblemAlert error={verifications.error} onRetry={() => void verifications.refetch()} />
            ) : (verifications.data?.items?.length ?? 0) === 0 ? (
              <p className="text-sm text-content-muted">No verification rows.</p>
            ) : (
              <ul className="space-y-3 text-sm">
                {verifications.data?.items?.map((verification) => (
                  <li key={verification.id} className="border-b border-surface-border/60 pb-2 last:border-0">
                    <p className="font-medium">
                      {humanize(verification.method)} - {humanize(verification.result)}
                    </p>
                    <p className="text-xs text-content-muted">
                      {verification.distance_meters !== null ? `distance ${Math.round(verification.distance_meters)} m` : 'distance n/a'}
                      {verification.accuracy_meters !== null ? ` - accuracy ${Math.round(verification.accuracy_meters)} m` : ''}
                      {verification.geofence_radius_meters !== null ? ` - radius ${Math.round(verification.geofence_radius_meters)} m` : ''}
                    </p>
                    {verification.qr_result ? <p className="text-xs text-content-muted">QR: {humanize(verification.qr_result)}</p> : null}
                    {verification.failure_code ? (
                      <p className="text-xs font-medium text-danger">
                        {humanize(verification.failure_code)}
                        {verification.failure_reason ? ` - ${verification.failure_reason}` : ''}
                      </p>
                    ) : null}
                    <p className="text-xs text-content-muted">{formatDateTime(verification.captured_at, settings.business_timezone)}</p>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>

      <Alert
        tone="info"
        title="Manual attendance events"
        nextStep="Recording a manual punch requires a documented endpoint that is not present in the current API contract; use an approved correction instead."
      />

      <Dialog
        open={recomputeOpen}
        onClose={() => setRecomputeOpen(false)}
        title="Recompute this day"
        description="Derived values are recalculated from stored events using the settings snapshot. History is not rewritten."
        footer={
          <>
            <Button variant="secondary" onClick={() => setRecomputeOpen(false)}>
              Cancel
            </Button>
            <Button
              loading={recompute.isPending}
              disabled={reason.trim().length === 0 || recompute.isPending}
              onClick={() =>
                recompute.mutate(
                  { id, reason: reason.trim() },
                  {
                    onSuccess: () => {
                      setRecomputeOpen(false);
                      setReason('');
                    }
                  }
                )
              }
            >
              Recompute
            </Button>
          </>
        }
      >
        <TextAreaField label="Reason" name="reason" required value={reason} onChange={(e) => setReason(e.target.value)} help="Recorded in the audit trail." />
      </Dialog>
    </div>
  );
}