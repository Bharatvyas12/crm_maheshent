'use client';

import { useParams } from 'next/navigation';
import Link from 'next/link';
import { useSession } from '@/features/auth/session';
import { useAttendanceEvents, useMyAttendance } from '@/features/attendance/hooks';
import { formatBusinessDate, formatDuration, formatTime, humanize } from '@/lib/format';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { StatusPill } from '@/components/ui/StatusPill';
import { SkeletonList } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { ProblemAlert } from '@/components/ui/ProblemAlert';

export default function EmployeeAttendanceDayPage() {
  const params = useParams<{ date: string }>();
  const date = params?.date ?? '';
  const { settings } = useSession();

  const nextDay = (() => {
    const parsed = new Date(`${date}T00:00:00Z`);
    if (Number.isNaN(parsed.getTime())) return date;
    parsed.setUTCDate(parsed.getUTCDate() + 1);
    return parsed.toISOString().slice(0, 10);
  })();

  // The contract exposes /attendance/{record_id}, so the business date is resolved to a record id.
  const dayQuery = useMyAttendance({ from: date, to: nextDay, page: 1 });
  const record = dayQuery.data?.items?.[0] ?? null;
  const events = useAttendanceEvents(record?.id ?? '');

  return (
    <div className="space-y-4">
      <Link href="/app/attendance" className="inline-block text-sm text-primary underline">
        Back to attendance
      </Link>

      {dayQuery.isLoading ? (
        <SkeletonList rows={2} />
      ) : dayQuery.error ? (
        <ProblemAlert error={dayQuery.error} onRetry={() => void dayQuery.refetch()} />
      ) : !record ? (
        <EmptyState title={`No attendance record for ${formatBusinessDate(date)}`} hint="Only recorded days have a detail view." />
      ) : (
        <>
          <Card>
            <CardHeader action={<StatusPill value={record.status} />}>
              <CardTitle as="h1">{formatBusinessDate(record.business_date)}</CardTitle>
              <p className="mt-0.5 text-xs text-content-muted">{humanize(record.day_classification)}</p>
            </CardHeader>
            <CardBody>
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <dt className="text-xs text-content-muted">First check-in</dt>
                  <dd>{formatTime(record.first_check_in_at, settings.business_timezone)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-content-muted">Last check-out</dt>
                  <dd>{formatTime(record.last_check_out_at, settings.business_timezone)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-content-muted">Worked (server)</dt>
                  <dd>{formatDuration(record.worked_seconds)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-content-muted">Break</dt>
                  <dd>{formatDuration(record.break_seconds)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-content-muted">Overtime</dt>
                  <dd>{formatDuration(record.overtime_seconds)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-content-muted">Late</dt>
                  <dd>{record.late_minutes} min</dd>
                </div>
              </dl>
              {record.anomalies && record.anomalies.length > 0 ? (
                <ul className="mt-3 list-inside list-disc text-xs text-warning">
                  {record.anomalies.map((anomaly) => (
                    <li key={anomaly}>{humanize(anomaly)}</li>
                  ))}
                </ul>
              ) : null}
            </CardBody>
          </Card>

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
                <p className="text-sm text-content-muted">No events recorded.</p>
              ) : (
                <ol className="space-y-2">
                  {events.data?.items.map((event) => (
                    <li key={event.id} className="flex items-center justify-between gap-3 border-b border-surface-border/60 pb-2 text-sm last:border-0">
                      <span>
                        <span className="font-medium">{humanize(event.event_type)}</span>
                        {event.is_manual ? <span className="ml-2 rounded bg-warning-soft px-1.5 py-0.5 text-xs text-warning">Manual</span> : null}
                        {event.note ? <span className="block text-xs text-content-muted">{event.note}</span> : null}
                      </span>
                      <span className="shrink-0 text-content-muted">{formatTime(event.occurred_at, settings.business_timezone)}</span>
                    </li>
                  ))}
                </ol>
              )}
            </CardBody>
          </Card>

          <Link
            href="/app/attendance/corrections"
            className="inline-flex min-h-touch w-full items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-fg"
          >
            Request a correction for this day
          </Link>
        </>
      )}
    </div>
  );
}