'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useCreateTask, useTasks } from '@/features/tasks/hooks';
import { useEmployees } from '@/features/employees/hooks';
import { formatDateTime, humanize } from '@/lib/format';
import { Card, CardBody } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { DataTable, type Column } from '@/components/ui/DataTable';
import { Pagination } from '@/components/ui/Pagination';
import { StatusPill } from '@/components/ui/StatusPill';
import { Dialog } from '@/components/ui/Dialog';
import { TextField, TextAreaField, SelectField, CheckboxField } from '@/components/ui/Form';
import { Alert } from '@/components/ui/Alert';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import type { Task } from '@/lib/types';

const PRIORITIES = ['LOW', 'NORMAL', 'HIGH', 'URGENT'];

export default function AdminTasksPage() {
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState('-created_at');
  const [status, setStatus] = useState('');
  const [priority, setPriority] = useState('');
  const [q, setQ] = useState('');
  const [applied, setApplied] = useState({ status: '', priority: '', q: '' });
  const [open, setOpen] = useState(false);

  const query = useTasks({ ...applied, sort, page });
  const employees = useEmployees({ status: 'ACTIVE', page: 1, page_size: 100 });
  const create = useCreateTask();

  const [form, setForm] = useState({
    title: '',
    description: '',
    priority: 'NORMAL',
    due_at: '',
    requires_evidence: false,
    requires_attachment: false,
    assignee_ids: [] as string[]
  });
  const [formError, setFormError] = useState<string | null>(null);

  const createError = create.error;

  function toggleAssignee(id: string) {
    setForm((current) => ({
      ...current,
      assignee_ids: current.assignee_ids.includes(id)
        ? current.assignee_ids.filter((value) => value !== id)
        : [...current.assignee_ids, id]
    }));
  }

  function submit() {
    setFormError(null);
    if (form.title.trim().length < 3) return setFormError('Give the task a title.');
    if (form.assignee_ids.length === 0) return setFormError('Choose at least one assignee.');
    create.mutate(
      {
        title: form.title.trim(),
        description: form.description || undefined,
        priority: form.priority,
        due_at: form.due_at ? new Date(form.due_at).toISOString() : null,
        requires_evidence: form.requires_evidence,
        requires_attachment: form.requires_attachment,
        assignee_employee_ids: form.assignee_ids
      },
      {
        onSuccess: () => {
          setOpen(false);
          setForm({ title: '', description: '', priority: 'NORMAL', due_at: '', requires_evidence: false, requires_attachment: false, assignee_ids: [] });
        }
      }
    );
  }

  const columns: Array<Column<Task>> = [
    {
      key: 'title',
      header: 'Task',
      sortable: true,
      render: (row) => (
        <Link href={`/admin/tasks/${row.id}`} className="font-medium text-primary underline">
          {row.title}
        </Link>
      )
    },
    { key: 'priority', header: 'Priority', sortable: true, render: (row) => <StatusPill value={row.priority} /> },
    { key: 'status', header: 'Status', sortable: true, render: (row) => <StatusPill value={row.status} /> },
    { key: 'due_at', header: 'Due', sortable: true, render: (row) => (row.due_at ? formatDateTime(row.due_at) : '-') },
    { key: 'assignments', header: 'Assignees', align: 'right', render: (row) => row.assignment_count ?? row.assignments?.length ?? 0 },
    { key: 'created_at', header: 'Created', sortable: true, render: (row) => formatDateTime(row.created_at) }
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Tasks"
        description="Create and assign work. Review happens in the review queue."
        actions={
          <div className="flex gap-2">
            <Link
              href="/admin/tasks/review"
              className="inline-flex min-h-touch items-center rounded-md border border-surface-border px-4 text-sm font-medium"
            >
              Review queue
            </Link>
            <Button onClick={() => setOpen(true)}>Create task</Button>
          </div>
        }
      />

      <Card>
        <CardBody className="grid gap-3 md:grid-cols-4">
          <SelectField
            label="Status"
            name="status"
            placeholder="Any"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            options={['OPEN', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED'].map((value) => ({ value, label: humanize(value) }))}
          />
          <SelectField
            label="Priority"
            name="priority"
            placeholder="Any"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            options={PRIORITIES.map((value) => ({ value, label: humanize(value) }))}
          />
          <TextField label="Search" name="q" value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="flex items-end gap-2">
            <Button
              onClick={() => {
                setApplied({ status, priority, q });
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
                setQ('');
                setApplied({ status: '', priority: '', q: '' });
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
            emptyTitle="No tasks"
            emptyHint="Create a task to assign work."
            sort={sort}
            onSortChange={(next) => {
              setSort(next);
              setPage(1);
            }}
            caption="Tasks"
            testId="admin-tasks-table"
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

      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Create task"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={submit} loading={create.isPending} disabled={create.isPending}>
              Create and assign
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {createError ? <ProblemAlert error={createError} testId="create-task-error" /> : null}
          {formError ? <Alert tone="danger" title={formError} /> : null}
          <TextField label="Title" name="title" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          <TextAreaField label="Description" name="description" rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          <SelectField
            label="Priority"
            name="priority"
            value={form.priority}
            onChange={(e) => setForm({ ...form, priority: e.target.value })}
            options={PRIORITIES.map((value) => ({ value, label: humanize(value) }))}
          />
          <TextField label="Due at" type="datetime-local" name="due_at" value={form.due_at} onChange={(e) => setForm({ ...form, due_at: e.target.value })} />
          <CheckboxField label="Evidence required" checked={form.requires_evidence} onChange={(e) => setForm({ ...form, requires_evidence: e.target.checked })} />
          <CheckboxField label="Attachment required" checked={form.requires_attachment} onChange={(e) => setForm({ ...form, requires_attachment: e.target.checked })} />

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Assignees</legend>
            <div className="max-h-52 space-y-1 overflow-y-auto rounded-md border border-surface-border p-2">
              {(employees.data?.items ?? []).map((employee) => (
                <label key={employee.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="h-4 w-4"
                    checked={form.assignee_ids.includes(employee.id)}
                    onChange={() => toggleAssignee(employee.id)}
                  />
                  {employee.full_name} ({employee.employee_code})
                </label>
              ))}
              {(employees.data?.items.length ?? 0) === 0 ? <p className="text-xs text-content-muted">No active employees.</p> : null}
            </div>
          </fieldset>
        </div>
      </Dialog>
    </div>
  );
}