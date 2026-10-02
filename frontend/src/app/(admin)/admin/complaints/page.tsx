'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useComplaints } from '@/features/complaints/hooks';
import { useComplaintCategories } from '@/features/complaints/hooks';
import { formatDateTime, humanize } from '@/lib/format';
import { Card, CardBody } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { DataTable, type Column } from '@/components/ui/DataTable';
import { Pagination } from '@/components/ui/Pagination';
import { StatusPill } from '@/components/ui/StatusPill';
import { TextField, SelectField } from '@/components/ui/Form';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import type { Complaint } from '@/lib/types';

export default function AdminComplaintsPage() {
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState('-created_at');
  const [status, setStatus] = useState('');
  const [priority, setPriority] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [q, setQ] = useState('');
  const [applied, setApplied] = useState({ status: '', priority: '', category_id: '', q: '' });

  const categories = useComplaintCategories(true);
  const query = useComplaints({ ...applied, sort, page });

  const columns: Array<Column<Complaint>> = [
    {
      key: 'complaint_code',
      header: 'Code',
      sortable: true,
      render: (row) => (
        <Link href={`/admin/complaints/${row.id}`} className="font-medium text-primary underline">
          {row.complaint_code}
        </Link>
      )
    },
    { key: 'title', header: 'Title', sortable: true, render: (row) => <span className="line-clamp-1">{row.title}</span> },
    { key: 'category', header: 'Category', render: (row) => row.category?.name ?? '-' },
    { key: 'priority', header: 'Priority', sortable: true, render: (row) => (row.priority ? <StatusPill value={row.priority} /> : '-') },
    { key: 'status', header: 'Status', sortable: true, render: (row) => <StatusPill value={row.status} /> },
    { key: 'visibility', header: 'Visibility', render: (row) => humanize(row.visibility) },
    { key: 'subject', header: 'About', render: (row) => row.subject_employee?.full_name ?? '-' },
    { key: 'created_at', header: 'Opened', sortable: true, render: (row) => formatDateTime(row.created_at) }
  ];

  return (
    <div className="space-y-4">
      <PageHeader title="Complaints" description="Triage, assign and resolve. Visibility rules are enforced server-side." />

      <Card>
        <CardBody className="grid gap-3 md:grid-cols-5">
          <SelectField
            label="Status"
            name="status"
            placeholder="Any"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            options={['OPEN', 'IN_REVIEW', 'ACTION_REQUIRED', 'RESOLVED', 'CLOSED', 'REJECTED'].map((value) => ({ value, label: humanize(value) }))}
          />
          <SelectField
            label="Priority"
            name="priority"
            placeholder="Any"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            options={['LOW', 'NORMAL', 'HIGH', 'URGENT'].map((value) => ({ value, label: humanize(value) }))}
          />
          <SelectField
            label="Category"
            name="category_id"
            placeholder="Any"
            value={categoryId}
            onChange={(e) => setCategoryId(e.target.value)}
            options={(categories.data?.items ?? []).map((category) => ({ value: category.id, label: category.name }))}
          />
          <TextField label="Search" name="q" value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="flex items-end gap-2">
            <Button
              onClick={() => {
                setApplied({ status, priority, category_id: categoryId, q });
                setPage(1);
              }}
            >
              Apply
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setStatus('');
                setPriority('');
                setCategoryId('');
                setQ('');
                setApplied({ status: '', priority: '', category_id: '', q: '' });
                setPage(1);
              }}
            >
              Clear
            </Button>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardBody>
          <DataTable
            columns={columns}
            rows={query.data?.items ?? []}
            getRowId={(row) => row.id}
            loading={query.isLoading}
            error={query.error ? <ProblemAlert error={query.error} onRetry={() => void query.refetch()} /> : undefined}
            emptyTitle="No complaints"
            emptyHint="Complaints raised by employees appear here."
            sort={sort}
            onSortChange={(next) => {
              setSort(next);
              setPage(1);
            }}
            caption="Complaints"
            testId="complaints-table"
          />
          {query.data ? (
            <Pagination
              page={query.data.page}
              pageSize={query.data.page_size}
              totalItems={query.data.total_items}
              totalPages={query.data.total_pages}
              onPageChange={setPage}
            />
          ) : null}
        </CardBody>
      </Card>
    </div>
  );
}