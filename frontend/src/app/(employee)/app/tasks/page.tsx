'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useMyAssignments } from '@/features/tasks/hooks';
import { formatDateTime, humanize } from '@/lib/format';
import { Card, CardBody } from '@/components/ui/Card';
import { Tabs, TabPanel } from '@/components/ui/Tabs';
import { StatusPill } from '@/components/ui/StatusPill';
import { SkeletonList } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { Pagination } from '@/components/ui/Pagination';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { Badge } from '@/components/ui/Badge';

const TABS = [
  { id: 'ACTIVE', label: 'Active' },
  { id: 'SUBMITTED', label: 'In review' },
  { id: 'RESUBMISSION_REQUESTED', label: 'Needs rework' },
  { id: 'APPROVED', label: 'Approved' },
  { id: 'ALL', label: 'All' }
];

function isOverdue(dueAt: string | null, status: string): boolean {
  if (!dueAt) return false;
  if (status === 'APPROVED' || status === 'REJECTED' || status === 'CANCELLED' || status === 'SUBMITTED') return false;
  return new Date(dueAt).getTime() < Date.now();
}

export default function MyTasksPage() {
  const [tab, setTab] = useState('ACTIVE');
  const [page, setPage] = useState(1);

  const statusParam = tab === 'ALL' ? undefined : tab === 'ACTIVE' ? undefined : tab;
  const query = useMyAssignments({ status: statusParam, page });

  const items = (query.data?.items ?? []).filter((assignment) => {
    if (tab === 'ACTIVE') return ['ASSIGNED', 'STARTED', 'COMPLETED'].includes(assignment.status);
    return true;
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">My tasks</h1>
        <p className="text-sm text-content-muted">Work assigned to you, newest first.</p>
      </div>

      <Tabs tabs={TABS} activeId={tab} onChange={(id) => { setTab(id); setPage(1); }} ariaLabel="Task status" />

      <TabPanel id={tab} activeId={tab}>
        {query.isLoading ? (
          <SkeletonList rows={4} />
        ) : query.error ? (
          <ProblemAlert error={query.error} onRetry={() => void query.refetch()} />
        ) : items.length === 0 ? (
          <EmptyState title="Nothing here" hint={tab === 'ACTIVE' ? 'You have no open work right now.' : 'No tasks match this filter.'} />
        ) : (
          <ul className="space-y-2">
            {items.map((assignment) => {
              const overdue = isOverdue(assignment.due_at, assignment.status);
              return (
                <li key={assignment.id}>
                  <Link href={`/app/tasks/${assignment.id}`} className="block">
                    <Card className="transition-shadow hover:shadow-md">
                      <CardBody className="space-y-2">
                        <div className="flex items-start justify-between gap-3">
                          <p className="text-sm font-semibold">{assignment.task?.title ?? 'Task'}</p>
                          <StatusPill value={assignment.status} />
                        </div>
                        {assignment.task?.description ? (
                          <p className="line-clamp-2 text-xs text-content-muted">{assignment.task.description}</p>
                        ) : null}
                        <div className="flex flex-wrap items-center gap-2 text-xs text-content-muted">
                          {assignment.task?.priority ? <Badge tone={assignment.task.priority === 'URGENT' ? 'danger' : 'neutral'}>{humanize(assignment.task.priority)}</Badge> : null}
                          {assignment.due_at ? <span>Due {formatDateTime(assignment.due_at)}</span> : <span>No due date</span>}
                          {overdue ? <span className="font-semibold text-danger">Overdue</span> : null}
                          {assignment.attempt_count > 1 ? <span>Attempt {assignment.attempt_count}</span> : null}
                        </div>
                      </CardBody>
                    </Card>
                  </Link>
                </li>
              );
            })}
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
      </TabPanel>
    </div>
  );
}