'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { ApiError } from '@/lib/api-client';
import { describeProblem } from '@/lib/problem-details';
import { formatDateTime, humanize } from '@/lib/format';
import { useAssignment, useCommentOnAssignment, useCompleteAssignment, useStartAssignment, useSubmitAssignment } from '@/features/tasks/hooks';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { StatusPill } from '@/components/ui/StatusPill';
import { SkeletonList } from '@/components/ui/Skeleton';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { Alert } from '@/components/ui/Alert';
import { TextAreaField } from '@/components/ui/Form';
import { FileUploadField, type UploadedFile } from '@/components/FileUploadField';

/** Matches the server-provided transition token without hard-coding the state machine. */
function hasTransition(allowed: string[] | undefined, token: string): boolean {
  if (!allowed) return false;
  return allowed.some((value) => value.toUpperCase().includes(token));
}

export default function EmployeeTaskDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? '';

  const query = useAssignment(id);
  const start = useStartAssignment();
  const complete = useCompleteAssignment();
  const submit = useSubmitAssignment();
  const comment = useCommentOnAssignment();

  const [description, setDescription] = useState('');
  const [attachments, setAttachments] = useState<UploadedFile[]>([]);
  const [commentBody, setCommentBody] = useState('');
  const [actionError, setActionError] = useState<unknown>(null);

  if (query.isLoading) return <SkeletonList rows={4} />;
  if (query.error) return <ProblemAlert error={query.error} onRetry={() => void query.refetch()} />;
  if (!query.data) return null;

  const assignment = query.data;
  const allowed = assignment.allowed_transitions ?? [];
  const canStart = hasTransition(allowed, 'START');
  const canComplete = hasTransition(allowed, 'COMPLETE');
  const canSubmit = hasTransition(allowed, 'SUBMIT');
  const lastSubmission = assignment.submissions?.[assignment.submissions.length - 1];

  return (
    <div className="space-y-4">
      <Link href="/app/tasks" className="inline-block text-sm text-primary underline">
        Back to tasks
      </Link>

      <Card>
        <CardHeader action={<StatusPill value={assignment.status} />}>
          <CardTitle as="h1">{assignment.task?.title ?? 'Task'}</CardTitle>
          <p className="mt-0.5 text-xs text-content-muted">
            {assignment.due_at ? `Due ${formatDateTime(assignment.due_at)}` : 'No due date'}
            {assignment.attempt_count > 1 ? ` - attempt ${assignment.attempt_count}` : ''}
          </p>
        </CardHeader>
        <CardBody className="space-y-3">
          {assignment.task?.description ? <p className="whitespace-pre-wrap text-sm">{assignment.task.description}</p> : null}
          {assignment.task?.requires_evidence ? <p className="text-xs font-medium text-warning">Evidence is required before submitting.</p> : null}
          {assignment.task?.requires_attachment ? <p className="text-xs font-medium text-warning">An attachment is required before submitting.</p> : null}
          {assignment.review_notes ? (
            <Alert tone="warning" title="Reviewer note" testId="task-review-note">
              <p>{assignment.review_notes}</p>
            </Alert>
          ) : null}
        </CardBody>
      </Card>

      {assignment.task?.attachments && assignment.task.attachments.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle as="h2">Brief attachments</CardTitle>
          </CardHeader>
          <CardBody>
            <ul className="space-y-1 text-sm">
              {assignment.task.attachments.map((attachment) => (
                <li key={attachment.id}>
                  <a
                    className="text-primary underline"
                    href={`/api/v1/files/${attachment.file_id}/url`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {attachment.file?.original_name ?? 'Attachment'}
                  </a>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}

      {actionError ? <ProblemAlert error={actionError} onRetry={() => setActionError(null)} /> : null}

      <Card>
        <CardHeader>
          <CardTitle as="h2">Next step</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          {canStart ? (
            <Button
              size="action"
              loading={start.isPending}
              onClick={() => {
                setActionError(null);
                start.mutate(id, { onError: setActionError });
              }}
              data-testid="task-start-button"
            >
              Start work
            </Button>
          ) : null}

          {canComplete ? (
            <Button
              size="action"
              loading={complete.isPending}
              onClick={() => {
                setActionError(null);
                complete.mutate({ id }, { onError: setActionError });
              }}
              data-testid="task-complete-button"
            >
              Mark complete
            </Button>
          ) : null}

          {canSubmit ? (
            <div className="space-y-3">
              <TextAreaField
                label="What did you do?"
                name="submission_description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                help="Description and evidence are kept per attempt; earlier attempts are never overwritten."
              />
              <FileUploadField
                purpose="TASK_EVIDENCE"
                label="Evidence"
                help="Photos or files that support this submission."
                accept="image/*,.pdf"
                multiple
                onUploaded={setAttachments}
                testId="task-evidence-upload"
              />
              <Button
                size="action"
                loading={submit.isPending}
                disabled={submit.isPending}
                onClick={() => {
                  setActionError(null);
                  submit.mutate(
                    { id, description, attachmentFileIds: attachments.map((file) => file.id) },
                    { onError: setActionError }
                  );
                }}
                data-testid="task-submit-button"
              >
                {assignment.attempt_count > 1 ? `Resubmit (attempt ${assignment.attempt_count + 1})` : 'Submit for review'}
              </Button>
            </div>
          ) : null}

          {!canStart && !canComplete && !canSubmit ? (
            <p className="text-sm text-content-muted">
              No action is available for you right now. This assignment is {humanize(assignment.status)}.
            </p>
          ) : null}
          {start.error || complete.error ? (
            <ProblemAlert error={start.error ?? complete.error} testId="task-action-error" />
          ) : null}
        </CardBody>
      </Card>

      {assignment.submissions && assignment.submissions.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle as="h2">Submission history</CardTitle>
          </CardHeader>
          <CardBody className="space-y-3">
            {assignment.submissions.map((submission) => (
              <div key={submission.id} className="border-b border-surface-border/60 pb-2 text-sm last:border-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">Attempt {submission.attempt_no}</span>
                  <StatusPill value={submission.status} />
                </div>
                <p className="text-xs text-content-muted">Submitted {formatDateTime(submission.submitted_at)}</p>
                {submission.description ? <p className="mt-1 text-xs">{submission.description}</p> : null}
                {submission.review_notes ? <p className="mt-1 text-xs text-warning">Reviewer: {submission.review_notes}</p> : null}
              </div>
            ))}
          </CardBody>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle as="h2">Comments</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          {lastSubmission === undefined && (assignment.comments?.length ?? 0) === 0 ? (
            <p className="text-sm text-content-muted">No comments yet.</p>
          ) : null}
          <ul className="space-y-2">
            {assignment.comments?.map((item) => (
              <li key={item.id} className="text-sm">
                <p>{item.body}</p>
                <p className="text-xs text-content-muted">{formatDateTime(item.created_at)}</p>
              </li>
            ))}
          </ul>
          <TextAreaField label="Add a comment" name="comment" rows={2} value={commentBody} onChange={(event) => setCommentBody(event.target.value)} />
          <Button
            variant="secondary"
            loading={comment.isPending}
            disabled={commentBody.trim().length === 0 || comment.isPending}
            onClick={() =>
              comment.mutate(
                { id, body: commentBody.trim() },
                {
                  onSuccess: () => setCommentBody(''),
                  onError: (error) => setActionError(error instanceof ApiError ? error : error)
                }
              )
            }
          >
            Post comment
          </Button>
        </CardBody>
      </Card>
    </div>
  );
}