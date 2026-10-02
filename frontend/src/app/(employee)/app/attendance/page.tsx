'use client';

import { useState } from 'react';
import Link from 'next/link';
import type { BreakType } from '@/lib/types';
import { useSession } from '@/features/auth/session';
import { useMyAttendance, useTodayAttendance, useBreakTypes } from '@/features/attendance/hooks';
import { formatBusinessDate, formatDuration, formatTime } from '@/lib/format';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { StatusPill } from '@/components/ui/StatusPill';
import { SkeletonList } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { Pagination } from '@/components/ui/Pagination';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { AttendanceActionPanel } from '@/components/attendance/AttendanceActionPanel';
import { Icon } from '@/components/ui/Icons';

function monthRange(): { from: string; to: string } {
  const now = new Date();
  const from = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1));
  const to = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 1));
  return { from: from.toISOString().slice(0, 10), to: to.toISOString().slice(0, 10) };
}

export default function EmployeeAttendancePage() {
  const { settings } = useSession();
  const [page, setPage] = useState(1);
  const range = monthRange();
  const today = useTodayAttendance();
  const history = useMyAttendance({ from: range.from, to: range.to, page });
  const breakTypes = useBreakTypes();
  const breakTypeList: BreakType[] = breakTypes.data?.items ?? [];

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Attendance</h1>
          <p className="text-sm text-content-muted">Check in, take breaks and review your days.</p>
        </div>
        <Link
          href="/app/attendance/corrections"
          className="flex min-h-touch items-center rounded-md border border-surface-border px-3 text-sm font-medium"
        >
          Corrections
        </Link>
      </div>

      {today.isLoading ? (
        <SkeletonList rows={1} />
      ) : today.error ? (
        <ProblemAlert error={today.error} onRetry={() => void today.refetch()} />
      ) : today.data ? (
        <Card data-testid="attendance-today-card">
          <CardBody className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold">Today - {formatBusinessDate(today.data.business_date)}</p>
                <p className="text-xs text-content-muted">
                  Worked {formatDuration(today.data.worked_seconds)} - break {formatDuration(today.data.break_seconds)}
                </p>
              </div>
              <StatusPill value={today.data.status} />
            </div>
            <AttendanceActionPanel record={today.data} />
          </CardBody>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle as="h2">Break types available</CardTitle>
        </CardHeader>
        <CardBody>
          {breakTypes.isLoading ? (
            <SkeletonList rows={1} />
          ) : breakTypeList.length === 0 ? (
            <p className="text-sm text-content-muted">No break types are configured yet.</p>
          ) : (
            <ul className="flex flex-wrap gap-2">
              {breakTypeList.map((type) => (
                <li key={type.id} className="rounded-full border border-surface-border px-3 py-1 text-xs">
                  {type.name}
                  {type.is_paid ? '' : ' (unpaid)'}
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <section className="space-y-3">
        <h2 className="text-base font-semibold">This month</h2>
        {history.isLoading ? (
          <SkeletonList rows={4} />
        ) : history.error ? (
          <ProblemAlert error={history.error} onRetry={() => void history.refetch()} />
        ) : (history.data?.items.length ?? 0) === 0 ? (
          <EmptyState title="No attendance records this month" hint="Your recorded days will appear here." />
        ) : (
          <ul className="space-y-2">
            {history.data?.items.map((record) => (
              <li key={record.id}>
                <Link
                  href={`/app/attendance/${record.business_date}`}
                  className="flex items-center justify-between gap-3 rounded-card border border-surface-border bg-surface px-4 py-3 hover:bg-surface-muted"
                >
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">{formatBusinessDate(record.business_date)}</span>
                    <span className="block text-xs text-content-muted">
                      {formatTime(record.first_check_in_at, settings.business_timezone)} - {formatTime(record.last_check_out_at, settings.business_timezone)}
                      {' - '}
                      {formatDuration(record.worked_seconds)}
                    </span>
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    <StatusPill value={record.status} />
                    <Icon name="list" className="h-4 w-4 text-content-muted" />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
        {history.data ? (
          <Pagination
            page={history.data.page}
            pageSize={history.data.page_size}
            totalItems={history.data.total_items}
            totalPages={history.data.total_pages}
            onPageChange={setPage}
          />
        ) : null}
      </section>

      <Button variant="secondary" size="md" className="w-full" onClick={() => void today.refetch()}>
        Refresh today
      </Button>
    </div>
  );
}