'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { formatDateTime, humanize } from '@/lib/format';
import { useAddComplaintComment, useComplaint, useComplaintComments } from '@/features/complaints/hooks';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { StatusPill } from '@/components/ui/StatusPill';
import { SkeletonList } from '@/components/ui/Skeleton';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { Alert } from '@/components/ui/Alert';
import { TextAreaField } from '@/components/ui/Form';

export default function EmployeeComplaintDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? '';
  const complaint = useComplaint(id);
  const comments = useComplaintComments(id, false);
  const addComment = useAddComplaintComment();
  const [body, setBody] = useState('');

  if (complaint.isLoading) return <SkeletonList rows={4} />;
  if (complaint.error) return <ProblemAlert error={complaint.error} onRetry={() => void complaint.refetch()} />;
  if (!complaint.data) return null;

  const data = complaint.data;
  const closed = ['CLOSED', 'REJECTED'].includes(data.status);

  return (
    <div className="space-y-4">
      <Link href="/app/complaints" className="inline-block text-sm text-primary underline">
        Back to complaints
      </Link>

      <Card>
        <CardHeader action={<StatusPill value={data.status} />}>
          <CardTitle as="h1">{data.title}</CardTitle>
          <p className="mt-0.5 text-xs text-content-muted">
            {data.complaint_code} - {data.category?.name ?? 'Uncategorised'} - {formatDateTime(data.created_at)}
          </p>
        </CardHeader>
        <CardBody className="space-y-3">
          <p className="whitespace-pre-wrap text-sm">{data.description}</p>
          {data.resolution_summary ? (
            <Alert tone="success" title="Resolution">
              <p>{data.resolution_summary}</p>
            </Alert>
          ) : null}
          {data.rejection_reason ? (
            <Alert tone="warning" title="Rejected">
              <p>{data.rejection_reason}</p>
            </Alert>
          ) : null}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle as="h2">Discussion</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          {comments.isLoading ? (
            <SkeletonList rows={2} />
          ) : comments.error ? (
            <ProblemAlert error={comments.error} onRetry={() => void comments.refetch()} />
          ) : (comments.data?.items.length ?? 0) === 0 ? (
            <p className="text-sm text-content-muted">No messages yet.</p>
          ) : (
            <ul className="space-y-2">
              {comments.data?.items.map((comment) => (
                <li key={comment.id} className="border-b border-surface-border/60 pb-2 text-sm last:border-0">
                  <p>{comment.body}</p>
                  <p className="text-xs text-content-muted">{formatDateTime(comment.created_at)}</p>
                </li>
              ))}
            </ul>
          )}

          {closed ? (
            <p className="text-xs text-content-muted">This complaint is closed, so no further comments can be added.</p>
          ) : (
            <>
              <TextAreaField label="Add a message" name="comment" rows={3} value={body} onChange={(event) => setBody(event.target.value)} />
              <Button
                variant="secondary"
                loading={addComment.isPending}
                disabled={body.trim().length === 0 || addComment.isPending}
                onClick={() => addComment.mutate({ id, body: { body: body.trim() } }, { onSuccess: () => setBody('') })}
              >
                Post message
              </Button>
            </>
          )}
          <p className="text-xs text-content-muted">
            Status: {humanize(data.status)}. Some internal notes are withheld from employee view by policy.
          </p>
        </CardBody>
      </Card>
    </div>
  );
}