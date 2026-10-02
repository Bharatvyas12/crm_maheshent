'use client';

import Link from 'next/link';
import { useSession } from '@/features/auth/session';
import { useTodayAttendance, useMyAttendanceSummary } from '@/features/attendance/hooks';
import { useAvailableOrders } from '@/features/orders/hooks';
import { useMyLeaveBalances } from '@/features/leaves/hooks';
import { useUnreadCount } from '@/features/notifications/hooks';
import { useDashboardSummary } from '@/features/reports/hooks';
import { pickNumber } from '@/lib/summary';
import { formatDuration, formatTime } from '@/lib/format';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { SkeletonList } from '@/components/ui/Skeleton';
import { Alert } from '@/components/ui/Alert';
import { StatusPill } from '@/components/ui/StatusPill';
import { StatCard } from '@/components/StatCard';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { AttendanceActionPanel } from '@/components/attendance/AttendanceActionPanel';

export default function EmployeeDashboardPage() {
  const { employee, settings, permissions } = useSession();
  const today = useTodayAttendance();
  const summary = useMyAttendanceSummary();
  const summaryCards = useDashboardSummary();
  const availableOrders = useAvailableOrders({ page: 1 });
  const leaveBalances = useMyLeaveBalances();
  const unread = useUnreadCount();

  const record = today.data;
  const openTasks = pickNumber(summaryCards.data, ['open_tasks', 'tasks_open', 'open_task_count', 'tasks_pending']);
  const activeClaims = pickNumber(summaryCards.data, ['active_claims', 'my_active_claims', 'claims_active']);
  const leaveAvailable = leaveBalances.data?.items[0]?.available_days ?? null;

  const needsAttention = record && (record.status === 'INCOMPLETE' || (record.is_open && record.business_date !== new Date().toISOString().slice(0, 10)));

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Hello{employee?.full_name ? `, ${employee.full_name.split(' ')[0]}` : ''}</h1>
        <p className="text-sm text-content-muted">Your day at a glance.</p>
      </div>

      {today.isLoading ? (
        <SkeletonList rows={1} />
      ) : today.error ? (
        <ProblemAlert error={today.error} onRetry={() => void today.refetch()} testId="dashboard-today-error" />
      ) : record ? (
        <Card data-testid="dashboard-attendance-card">
          <CardHeader
            action={<StatusPill value={record.status} />}
            className="items-center"
          >
            <CardTitle>Today</CardTitle>
            <p className="mt-0.5 text-xs text-content-muted">
              {record.day_classification && record.day_classification !== 'NONE' ? record.day_classification.replace(/_/g, ' ').toLowerCase() : 'Not classified yet'}
              {' - '}
              worked {formatDuration(record.worked_seconds)}
            </p>
          </CardHeader>
          <CardBody className="space-y-4">
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-xs text-content-muted">First check-in</p>
                <p>{formatTime(record.first_check_in_at, settings.business_timezone)}</p>
              </div>
              <div>
                <p className="text-xs text-content-muted">Last check-out</p>
                <p>{formatTime(record.last_check_out_at, settings.business_timezone)}</p>
              </div>
            </div>
            <AttendanceActionPanel record={record} />
          </CardBody>
        </Card>
      ) : null}

      {needsAttention ? (
        <Alert
          tone="warning"
          title="This day needs attention."
          nextStep="Open corrections to explain the missing or incomplete time."
          testId="dashboard-needs-attention"
          actions={
            <Link href="/app/attendance/corrections" className="rounded border border-current px-3 py-1 text-xs font-medium">
              Go to corrections
            </Link>
          }
        />
      ) : null}

      <div className="grid grid-cols-2 gap-3">
        <StatCard label="Open tasks" value={openTasks} href="/app/tasks" tone="info" loading={summaryCards.isLoading} />
        <StatCard
          label="Available orders"
          value={availableOrders.data?.total_items ?? null}
          href="/app/orders?tab=available"
          tone="info"
          loading={availableOrders.isLoading}
        />
        <StatCard label="My active claims" value={activeClaims} href="/app/orders?tab=mine" loading={summaryCards.isLoading} />
        <StatCard
          label="Unread alerts"
          value={unread.data ?? null}
          href="/app/notifications"
          tone={unread.data ? 'warning' : 'neutral'}
          loading={unread.isLoading}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle as="h2">This period</CardTitle>
        </CardHeader>
        <CardBody>
          {summary.isLoading ? (
            <SkeletonList rows={1} />
          ) : summary.data ? (
            <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
              <div>
                <dt className="text-xs text-content-muted">Present days</dt>
                <dd className="font-medium">{summary.data.present_days}</dd>
              </div>
              <div>
                <dt className="text-xs text-content-muted">Worked</dt>
                <dd className="font-medium">{formatDuration(summary.data.worked_seconds)}</dd>
              </div>
              <div>
                <dt className="text-xs text-content-muted">Overtime</dt>
                <dd className="font-medium">{formatDuration(summary.data.overtime_seconds)}</dd>
              </div>
              {leaveAvailable && permissions.includes('leave.read.self') ? (
                <div>
                  <dt className="text-xs text-content-muted">Leave available</dt>
                  <dd className="font-medium">{leaveAvailable} days</dd>
                </div>
              ) : null}
            </dl>
          ) : (
            <p className="text-sm text-content-muted">No attendance summary is available yet.</p>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle as="h2">Quick links</CardTitle>
        </CardHeader>
        <CardBody className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
          <Link className="rounded-md border border-surface-border px-3 py-3 hover:bg-surface-muted" href="/app/attendance">Attendance</Link>
          <Link className="rounded-md border border-surface-border px-3 py-3 hover:bg-surface-muted" href="/app/tasks">Tasks</Link>
          <Link className="rounded-md border border-surface-border px-3 py-3 hover:bg-surface-muted" href="/app/orders">Orders</Link>
          <Link className="rounded-md border border-surface-border px-3 py-3 hover:bg-surface-muted" href="/app/leaves">Leave</Link>
          <Link className="rounded-md border border-surface-border px-3 py-3 hover:bg-surface-muted" href="/app/complaints">Complaints</Link>
          <Link className="rounded-md border border-surface-border px-3 py-3 hover:bg-surface-muted" href="/app/profile">Profile</Link>
        </CardBody>
      </Card>

    </div>
  );
}