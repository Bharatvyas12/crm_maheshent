'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import {
  useAddComplaintComment,
  useCloseComplaint,
  useComplaint,
  useComplaintComments,
  useComplaintStatus,
  useRejectComplaint,
  useResolveComplaint,
  useUpdateComplaint
} from '@/features/complaints/hooks';
import { useEmployees } from '@/features/employees/hooks';
import { usePermissions } from '@/features/auth/session';
import { formatDateTime, humanize } from '@/lib/format';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { TextAreaField, SelectField, Switch } from '@/components/ui/Form';
import { StatusPill } from '@/components/ui/StatusPill';
import { SkeletonList } from '@/components/ui/Skeleton';
import { ProblemAlert } from '@/components/ui/ProblemAlert';

const STATUSES = ['OPEN', 'IN_REVIEW', 'ACTION_REQUIRED'];

export default function AdminComplaintDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? '';
  const { can } = usePermissions();

  const complaint = useComplaint(id);
  const comments = useComplaintComments(id, can('complaint.read.internal'));
  const commentList = comments.data?.items ?? [];
  const employees = useEmployees({ status: 'ACTIVE', page: 1, page_size: 100 });

  const update = useUpdateComplaint();
  const statusChange = useComplaintStatus();
  const resolve = useResolveComplaint();
  const close = useCloseComplaint();
  const reject = useRejectComplaint();
  const addComment = useAddComplaintComment();

  const [dialog, setDialog] = useState<'status' | 'resolve' | 'close' | 'reject' | null>(null);
  const [statusTo, setStatusTo] = useState('IN_REVIEW');
  const [statusReason, setStatusReason] = useState('');
  const [internalNote, setInternalNote] = useState('');
  const [resolutionSummary, setResolutionSummary] = useState('');
  const [closeNote, setCloseNote] = useState('');
  const [rejectionReason, setRejectionReason] = useState('');
  const [commentBody, setCommentBody] = useState('');
  const [commentInternal, setCommentInternal] = useState(false);

  if (complaint.isLoading) return <SkeletonList rows={4} />;
  if (complaint.error) return <ProblemAlert error={complaint.error} onRetry={() => void complaint.refetch()} />;
  if (!complaint.data) return null;

  const data = complaint.data;

  return (
    <div className="space-y-4">
      <Link href="/admin/complaints" className="inline-block text-sm text-primary underline">
        Back to complaints
      </Link>

      <PageHeader
        title={data.title}
        description={`${data.complaint_code} - ${humanize(data.visibility)} - opened ${formatDateTime(data.created_at)}`}
        actions={
          <>
            <StatusPill value={data.status} />
            <Button variant="secondary" onClick={() => setDialog('status')}>
              Change status
            </Button>
            <Button onClick={() => setDialog('resolve')}>Resolve</Button>
            <Button variant="secondary" onClick={() => setDialog('close')}>
              Close
            </Button>
            <Button variant="danger" onClick={() => setDialog('reject')}>
              Reject
            </Button>
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle as="h2">Details</CardTitle>
          </CardHeader>
          <CardBody className="space-y-3 text-sm">
            <p className="whitespace-pre-wrap">{data.description}</p>
            <dl className="grid grid-cols-2 gap-2">
              <div>
                <dt className="text-xs text-content-muted">Category</dt>
                <dd>{data.category?.name ?? '-'}</dd>
              </div>
              <div>
                <dt className="text-xs text-content-muted">Priority</dt>
                <dd>{data.priority ? humanize(data.priority) : '-'}</dd>
              </div>
              <div>
                <dt className="text-xs text-content-muted">About</dt>
                <dd>{data.subject_employee?.full_name ?? '-'}</dd>
              </div>
              <div>
                <dt className="text-xs text-content-muted">Visibility</dt>
                <dd>{humanize(data.visibility)}</dd>
              </div>
            </dl>

            <div className="grid gap-2 border-t border-surface-border pt-3">
              <SelectField
                label="Assign to"
                name="assigned_to"
                placeholder="Unassigned"
                value={data.assigned_to_user_id ?? ''}
                onChange={(e) => update.mutate({ id, body: { assigned_to: e.target.value } })}
                options={(employees.data?.items ?? []).map((employee) => ({ value: employee.user_id, label: employee.full_name }))}
              />
              <SelectField
                label="Priority"
                name="priority_update"
                placeholder="Unchanged"
                value=""
                onChange={(e) => update.mutate({ id, body: { priority: e.target.value } })}
                options={['LOW', 'NORMAL', 'HIGH', 'URGENT'].map((value) => ({ value, label: humanize(value) }))}
              />
              <SelectField
                label="Visibility"
                name="visibility_update"
                placeholder="Unchanged"
                value=""
                onChange={(e) => update.mutate({ id, body: { visibility: e.target.value } })}
                options={['EMPLOYEE_PRIVATE', 'ADMIN_ONLY', 'INTERNAL_TEAM'].map((value) => ({ value, label: humanize(value) }))}
              />
            </div>
            {update.error ? <ProblemAlert error={update.error} /> : null}
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle as="h2">Discussion</CardTitle>
          </CardHeader>
          <CardBody className="space-y-3">
            {comments.isLoading ? (
              <SkeletonList rows={2} />
            ) : (
              <ul className="space-y-2 text-sm">
                {commentList.map((comment) => (
                  <li key={comment.id} className="border-b border-surface-border/60 pb-2 last:border-0">
                    <p>{comment.body}</p>
                    <p className="text-xs text-content-muted">
                      {formatDateTime(comment.created_at)}
                      {comment.is_internal ? ' - internal' : ''}
                    </p>
                  </li>
                ))}
                {commentList.length === 0 ? <li className="text-content-muted">No comments yet.</li> : null}
              </ul>
            )}

            <TextAreaField label="Add a comment" name="comment" rows={3} value={commentBody} onChange={(e) => setCommentBody(e.target.value)} />
            {can('complaint.read.internal') ? (
              <Switch label="Internal note (not visible to the raiser)" checked={commentInternal} onChange={setCommentInternal} />
            ) : null}
            <Button
              variant="secondary"
              loading={addComment.isPending}
              disabled={commentBody.trim().length === 0}
              onClick={() =>
                addComment.mutate(
                  { id, body: { body: commentBody.trim(), is_internal: commentInternal || undefined } },
                  { onSuccess: () => setCommentBody('') }
                )
              }
            >
              Post comment
            </Button>
          </CardBody>
        </Card>
      </div>

      <Dialog
        open={dialog === 'status'}
        onClose={() => setDialog(null)}
        title="Change status"
        footer={
          <>
            <Button variant="secondary" onClick={() => setDialog(null)}>
              Cancel
            </Button>
            <Button
              loading={statusChange.isPending}
              onClick={() =>
                statusChange.mutate(
                  { id, body: { to_status: statusTo, reason: statusReason || undefined, internal_note: internalNote || undefined } },
                  { onSuccess: () => setDialog(null) }
                )
              }
            >
              Update status
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {statusChange.error ? <ProblemAlert error={statusChange.error} /> : null}
          <SelectField
            label="New status"
            name="to_status"
            value={statusTo}
            onChange={(e) => setStatusTo(e.target.value)}
            options={[...STATUSES, ...(data.allowed_transitions ?? [])].filter((value, index, all) => all.indexOf(value) === index).map((value) => ({ value, label: humanize(value) }))}
          />
          <TextAreaField label="Reason" name="reason" rows={2} value={statusReason} onChange={(e) => setStatusReason(e.target.value)} />
          {can('complaint.read.internal') ? (
            <TextAreaField label="Internal note" name="internal_note" rows={2} value={internalNote} onChange={(e) => setInternalNote(e.target.value)} />
          ) : null}
        </div>
      </Dialog>

      <Dialog
        open={dialog === 'resolve'}
        onClose={() => setDialog(null)}
        title="Resolve complaint"
        footer={
          <>
            <Button variant="secondary" onClick={() => setDialog(null)}>
              Cancel
            </Button>
            <Button
              loading={resolve.isPending}
              disabled={resolutionSummary.trim().length === 0}
              onClick={() => resolve.mutate({ id, summary: resolutionSummary.trim() }, { onSuccess: () => setDialog(null) })}
            >
              Resolve
            </Button>
          </>
        }
      >
        {resolve.error ? <ProblemAlert error={resolve.error} /> : null}
        <TextAreaField label="Resolution summary" name="resolution_summary" required value={resolutionSummary} onChange={(e) => setResolutionSummary(e.target.value)} />
      </Dialog>

      <Dialog
        open={dialog === 'close'}
        onClose={() => setDialog(null)}
        title="Close complaint"
        description="Only a resolved complaint can be closed."
        footer={
          <>
            <Button variant="secondary" onClick={() => setDialog(null)}>
              Cancel
            </Button>
            <Button loading={close.isPending} onClick={() => close.mutate({ id, note: closeNote || undefined }, { onSuccess: () => setDialog(null) })}>
              Close
            </Button>
          </>
        }
      >
        {close.error ? <ProblemAlert error={close.error} /> : null}
        <TextAreaField label="Closing note" name="note" rows={2} value={closeNote} onChange={(e) => setCloseNote(e.target.value)} />
      </Dialog>

      <Dialog
        open={dialog === 'reject'}
        onClose={() => setDialog(null)}
        title="Reject complaint"
        footer={
          <>
            <Button variant="secondary" onClick={() => setDialog(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={reject.isPending}
              disabled={rejectionReason.trim().length === 0}
              onClick={() => reject.mutate({ id, reason: rejectionReason.trim() }, { onSuccess: () => setDialog(null) })}
            >
              Reject
            </Button>
          </>
        }
      >
        {reject.error ? <ProblemAlert error={reject.error} /> : null}
        <TextAreaField label="Rejection reason" name="rejection_reason" required value={rejectionReason} onChange={(e) => setRejectionReason(e.target.value)} />
      </Dialog>
    </div>
  );
}