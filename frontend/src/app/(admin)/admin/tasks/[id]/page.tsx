'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { useAssignTask, useCancelTask, useRemoveAssignment, useTask, useUpdateTask } from '@/features/tasks/hooks';
import { useEmployees } from '@/features/employees/hooks';
import { formatDateTime, humanize } from '@/lib/format';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { TextField, TextAreaField, SelectField, CheckboxField } from '@/components/ui/Form';
import { StatusPill } from '@/components/ui/StatusPill';
import { SkeletonList } from '@/components/ui/Skeleton';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { PermissionGate } from '@/components/PermissionGate';

const PRIORITIES = ['LOW', 'NORMAL', 'HIGH', 'URGENT'];

export default function AdminTaskDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? '';
  const task = useTask(id);
  const employees = useEmployees({ status: 'ACTIVE', page: 1, page_size: 100 });
  const update = useUpdateTask();
  const assign = useAssignTask();
  const removeAssignment = useRemoveAssignment();
  const cancel = useCancelTask();

  const [edit, setEdit] = useState({ title: '', description: '', priority: 'NORMAL', due_at: '', requires_evidence: false, requires_attachment: false });
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignIds, setAssignIds] = useState<string[]>([]);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState('');

  useEffect(() => {
    if (!task.data) return;
    setEdit({
      title: task.data.title,
      description: task.data.description ?? '',
      priority: task.data.priority,
      due_at: task.data.due_at ? task.data.due_at.slice(0, 16) : '',
      requires_evidence: task.data.requires_evidence,
      requires_attachment: task.data.requires_attachment
    });
  }, [task.data]);

  if (task.isLoading) return <SkeletonList rows={4} />;
  if (task.error) return <ProblemAlert error={task.error} onRetry={() => void task.refetch()} />;
  if (!task.data) return null;

  const data = task.data;

  return (
    <div className="space-y-4">
      <Link href="/admin/tasks" className="inline-block text-sm text-primary underline">
        Back to tasks
      </Link>

      <PageHeader
        title={data.title}
        description={`Created ${formatDateTime(data.created_at)}${data.due_at ? ` - due ${formatDateTime(data.due_at)}` : ''}`}
        actions={
          <>
            <StatusPill value={data.status} />
            <Button variant="secondary" onClick={() => setAssignOpen(true)}>
              Assign
            </Button>
            <Button variant="danger" onClick={() => setCancelOpen(true)}>
              Cancel task
            </Button>
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle as="h2">Details</CardTitle>
          </CardHeader>
          <CardBody className="space-y-3">
            {update.error ? <ProblemAlert error={update.error} /> : null}
            <TextField label="Title" name="title" value={edit.title} onChange={(e) => setEdit({ ...edit, title: e.target.value })} />
            <TextAreaField label="Description" name="description" rows={4} value={edit.description} onChange={(e) => setEdit({ ...edit, description: e.target.value })} />
            <SelectField
              label="Priority"
              name="priority"
              value={edit.priority}
              onChange={(e) => setEdit({ ...edit, priority: e.target.value })}
              options={PRIORITIES.map((value) => ({ value, label: humanize(value) }))}
            />
            <TextField label="Due at" type="datetime-local" name="due_at" value={edit.due_at} onChange={(e) => setEdit({ ...edit, due_at: e.target.value })} />
            <CheckboxField label="Evidence required" checked={edit.requires_evidence} onChange={(e) => setEdit({ ...edit, requires_evidence: e.target.checked })} />
            <CheckboxField label="Attachment required" checked={edit.requires_attachment} onChange={(e) => setEdit({ ...edit, requires_attachment: e.target.checked })} />
            <PermissionGate anyOf={['task.update']}>
              <Button
                loading={update.isPending}
                onClick={() =>
                  update.mutate({
                    id,
                    body: {
                      title: edit.title,
                      description: edit.description || undefined,
                      priority: edit.priority,
                      due_at: edit.due_at ? new Date(edit.due_at).toISOString() : null,
                      requires_evidence: edit.requires_evidence,
                      requires_attachment: edit.requires_attachment
                    }
                  })
                }
              >
                Save changes
              </Button>
            </PermissionGate>
            <p className="text-xs text-content-muted">Completed or cancelled tasks reject edits.</p>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle as="h2">Assignments</CardTitle>
          </CardHeader>
          <CardBody className="space-y-2">
            {(data.assignments ?? []).length === 0 ? (
              <p className="text-sm text-content-muted">No assignments.</p>
            ) : (
              <ul className="space-y-2">
                {data.assignments?.map((assignment) => (
                  <li key={assignment.id} className="flex items-center justify-between gap-3 border-b border-surface-border/60 pb-2 text-sm last:border-0">
                    <span>
                      <span className="font-medium">{assignment.employee?.full_name ?? 'Employee'}</span>
                      <span className="block text-xs text-content-muted">
                        Attempts {assignment.attempt_count}
                        {assignment.review_notes ? ` - note: ${assignment.review_notes}` : ''}
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-2">
                      <StatusPill value={assignment.status} />
                      {assignment.status === 'ASSIGNED' ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          loading={removeAssignment.isPending}
                          onClick={() => removeAssignment.mutate({ taskId: id, assignmentId: assignment.id })}
                        >
                          Remove
                        </Button>
                      ) : null}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>

      <Dialog
        open={assignOpen}
        onClose={() => setAssignOpen(false)}
        title="Assign employees"
        description="Already-assigned employees return a duplicate conflict."
        footer={
          <>
            <Button variant="secondary" onClick={() => setAssignOpen(false)}>
              Cancel
            </Button>
            <Button
              loading={assign.isPending}
              disabled={assignIds.length === 0 || assign.isPending}
              onClick={() =>
                assign.mutate(
                  { id, body: { employee_ids: assignIds } },
                  {
                    onSuccess: () => {
                      setAssignOpen(false);
                      setAssignIds([]);
                    }
                  }
                )
              }
            >
              Assign
            </Button>
          </>
        }
      >
        <div className="max-h-64 space-y-1 overflow-y-auto rounded-md border border-surface-border p-2">
          {(employees.data?.items ?? []).map((employee) => (
            <label key={employee.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="h-4 w-4"
                checked={assignIds.includes(employee.id)}
                onChange={() =>
                  setAssignIds((current) =>
                    current.includes(employee.id) ? current.filter((value) => value !== employee.id) : [...current, employee.id]
                  )
                }
              />
              {employee.full_name} ({employee.employee_code})
            </label>
          ))}
        </div>
      </Dialog>

      <Dialog
        open={cancelOpen}
        onClose={() => setCancelOpen(false)}
        title="Cancel task"
        description="Open assignments are cancelled and assignees are notified."
        footer={
          <>
            <Button variant="secondary" onClick={() => setCancelOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={cancel.isPending}
              disabled={cancelReason.trim().length === 0}
              onClick={() =>
                cancel.mutate(
                  { id, reason: cancelReason.trim() },
                  {
                    onSuccess: () => {
                      setCancelOpen(false);
                      setCancelReason('');
                    }
                  }
                )
              }
            >
              Cancel task
            </Button>
          </>
        }
      >
        {cancel.error ? <ProblemAlert error={cancel.error} /> : null}
        <TextAreaField label="Reason" name="cancel_reason" required value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} />
      </Dialog>
    </div>
  );
}