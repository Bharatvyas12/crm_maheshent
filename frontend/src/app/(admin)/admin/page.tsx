'use client';

import { useDashboardSummary } from '@/features/reports/hooks';
import { useCorrections } from '@/features/attendance/hooks';
import { useLeaves } from '@/features/leaves/hooks';
import { useSubmissions } from '@/features/tasks/hooks';
import { useComplaints } from '@/features/complaints/hooks';
import { useOrders } from '@/features/orders/hooks';
import { useUnreadCount } from '@/features/notifications/hooks';
import { pickNumber } from '@/lib/summary';
import { StatCard } from '@/components/StatCard';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import Link from 'next/link';

export default function AdminDashboardPage() {
  const summary = useDashboardSummary();
  const corrections = useCorrections({ status: 'PENDING', page: 1 });
  const leaves = useLeaves({ status: 'PENDING', page: 1 });
  const submissions = useSubmissions({ status: 'PENDING_DECISION', page: 1 });
  const complaints = useComplaints({ status: 'OPEN', page: 1 });
  const broadcast = useOrders({ status: 'BROADCASTED', page: 1 });
  const unread = useUnreadCount();

  const data = summary.data;

  /** Prefer the server summary; fall back to the documented list total (also server-provided). */
  function counter(keys: string[], fallback: number | null | undefined): number | null {
    const fromSummary = pickNumber(data, keys);
    if (fromSummary !== null) return fromSummary;
    return typeof fallback === 'number' ? fallback : null;
  }

  return (
    <div className="space-y-5">
      <PageHeader title="Dashboard" description="Today across attendance, work, finance and support." />

      {summary.error ? <ProblemAlert error={summary.error} onRetry={() => void summary.refetch()} testId="admin-dashboard-error" /> : null}

      {summary.isSuccess && !data ? (
        <ProblemAlert
          error={{ title: 'No dashboard data', code: 'RESOURCE_NOT_FOUND', detail: 'The server returned an empty summary.' }}
          testId="admin-dashboard-empty"
        />
      ) : null}

      <section className="space-y-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-content-muted">Attendance today</h2>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard label="Present" value={counter(['present_today', 'today_present', 'present'], null)} tone="success" href="/admin/attendance?status=PRESENT" loading={summary.isLoading} />
          <StatCard label="Absent" value={counter(['absent_today', 'today_absent', 'absent'], null)} tone="danger" href="/admin/attendance?status=ABSENT" loading={summary.isLoading} />
          <StatCard label="Incomplete" value={counter(['incomplete_today', 'today_incomplete', 'incomplete'], null)} tone="warning" href="/admin/attendance?status=INCOMPLETE" loading={summary.isLoading} />
          <StatCard label="Pending corrections" value={counter(['pending_corrections'], corrections.data?.total_items)} tone="warning" href="/admin/attendance/corrections" loading={summary.isLoading || corrections.isLoading} />
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-content-muted">Work</h2>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard label="Broadcast open" value={counter(['broadcasted_unclaimed', 'open_claims', 'broadcasted'], broadcast.data?.total_items)} href="/admin/orders?status=BROADCASTED" loading={summary.isLoading || broadcast.isLoading} />
          <StatCard label="Tasks awaiting review" value={counter(['tasks_awaiting_review', 'review_queue'], submissions.data?.total_items)} tone="info" href="/admin/tasks/review" loading={summary.isLoading || submissions.isLoading} />
          <StatCard label="Pending leave" value={counter(['pending_leaves', 'leave_pending'], leaves.data?.total_items)} tone="warning" href="/admin/leaves?status=PENDING" loading={summary.isLoading || leaves.isLoading} />
          <StatCard label="Open complaints" value={counter(['open_complaints', 'complaints_open'], complaints.data?.total_items)} tone="warning" href="/admin/complaints?status=OPEN" loading={summary.isLoading || complaints.isLoading} />
        </div>
      </section>

      <Card>
        <CardHeader>
          <CardTitle as="h2">Shortcuts</CardTitle>
        </CardHeader>
        <CardBody className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3 lg:grid-cols-4">
          <Link className="rounded-md border border-surface-border px-3 py-3 hover:bg-surface-muted" href="/admin/employees">Employees</Link>
          <Link className="rounded-md border border-surface-border px-3 py-3 hover:bg-surface-muted" href="/admin/attendance/qr">Shop QR</Link>
          <Link className="rounded-md border border-surface-border px-3 py-3 hover:bg-surface-muted" href="/admin/orders">Orders</Link>
          <Link className="rounded-md border border-surface-border px-3 py-3 hover:bg-surface-muted" href="/admin/payroll">Payroll</Link>
          <Link className="rounded-md border border-surface-border px-3 py-3 hover:bg-surface-muted" href="/admin/reports">Reports</Link>
          <Link className="rounded-md border border-surface-border px-3 py-3 hover:bg-surface-muted" href="/admin/settings">Settings</Link>
          <Link className="rounded-md border border-surface-border px-3 py-3 hover:bg-surface-muted" href="/admin/audit">Audit log</Link>
          <Link className="rounded-md border border-surface-border px-3 py-3 hover:bg-surface-muted" href="/admin/notifications">Notifications</Link>
        </CardBody>
      </Card>
    </div>
  );
}