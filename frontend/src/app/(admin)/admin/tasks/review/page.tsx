'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useReviewSubmission, useSubmissions } from '@/features/tasks/hooks';
import { formatDateTime, humanize } from '@/lib/format';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { TextAreaField } from '@/components/ui/Form';
import { StatusPill } from '@/components/ui/StatusPill';
import { SkeletonList } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { Alert } from '@/components/ui/Alert';

export default function AdminTaskReviewPage() {
  const query = useSubmissions({ status: 'PENDING_DECISION', page: 1 });
  const review = useReviewSubmission();
  const [selected, setSelected] = useState<{ id: string; action: 'approve' | 'reject' | 'request-resubmission' } | null>(null);
  const [notes, setNotes] = useState('');

  return (
    <div className="space-y-4">
      <PageHeader
        title="Task review queue"
        description="Submissions awaiting a decision. Self-review is rejected by the server."
        actions={
          <Link href="/admin/tasks" className="inline-flex min-h-touch items-center rounded-md border border-surface-border px-4 text-sm font-medium">
            All tasks
          </Link>
        }
      />

      {query.isLoading ? (
        <SkeletonList rows={4} />
      ) : query.error ? (
        <ProblemAlert error={query.error} onRetry={() => void query.refetch()} />
      ) : (query.data?.items.length ?? 0) === 0 ? (
        <EmptyState title="Nothing awaiting review" hint="Submissions will appear here as employees complete work." />
      ) : (
        <ul className="space-y-2">
          {query.data?.items.map((submission) => (
            <li key={submission.id}>
              <Card>
                <CardHeader action={<StatusPill value={submission.status} />}>
                  <CardTitle>Attempt {submission.attempt_no}</CardTitle>
                  <p className="mt-0.5 text-xs text-content-muted">Submitted {formatDateTime(submission.submitted_at)}</p>
                </CardHeader>
                <CardBody className="space-y-3 text-sm">
                  {submission.description ? <p className="whitespace-pre-wrap">{submission.description}</p> : <p className="text-content-muted">No description provided.</p>}
                  {submission.attachments && submission.attachments.length > 0 ? (
                    <ul className="space-y-1 text-xs">
                      {submission.attachments.map((attachment) => (
                        <li key={attachment.id}>
                          <a className="text-primary underline" href={`/api/v1/files/${attachment.file_id}/url`} target="_blank" rel="noreferrer">
                            {attachment.file?.original_name ?? 'Evidence file'}
                          </a>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-content-muted">No attachments on this attempt.</p>
                  )}
                  <div className="flex flex-wrap gap-2">
                    <Button onClick={() => { setSelected({ id: submission.id, action: 'approve' }); setNotes(''); }}>Approve</Button>
                    <Button variant="danger" onClick={() => { setSelected({ id: submission.id, action: 'reject' }); setNotes(''); }}>
                      Reject
                    </Button>
                    <Button variant="secondary" onClick={() => { setSelected({ id: submission.id, action: 'request-resubmission' }); setNotes(''); }}>
                      Request resubmission
                    </Button>
                  </div>
                </CardBody>
              </Card>
            </li>
          ))}
        </ul>
      )}

      <Dialog
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title={
          selected?.action === 'approve'
            ? 'Approve submission'
            : selected?.action === 'reject'
              ? 'Reject submission'
              : 'Request resubmission'
        }
        description={
          selected?.action === 'reject'
            ? 'A rejection is terminal for this assignment; further work needs a new task or assignment.'
            : 'Notes are visible to the employee for rejection and resubmission.'
        }
        footer={
          <>
            <Button variant="secondary" onClick={() => setSelected(null)}>
              Cancel
            </Button>
            <Button
              variant={selected?.action === 'reject' ? 'danger' : 'primary'}
              loading={review.isPending}
              disabled={(selected?.action !== 'approve' && notes.trim().length === 0) || review.isPending}
              onClick={() => {
                if (!selected) return;
                review.mutate(
                  { id: selected.id, action: selected.action, notes: notes.trim() || undefined },
                  {
                    onSuccess: () => {
                      setSelected(null);
                      setNotes('');
                    }
                  }
                );
              }}
            >
              Confirm
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {review.error ? <ProblemAlert error={review.error} testId="review-error" /> : null}
          {selected?.action === 'approve' ? <Alert tone="info" title="You cannot approve your own submission." /> : null}
          <TextAreaField
            label={selected?.action === 'approve' ? 'Review notes (optional)' : 'Review notes (required)'}
            name="review_notes"
            required={selected?.action !== 'approve'}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            help={selected ? humanize(selected.action) : undefined}
          />
        </div>
      </Dialog>
    </div>
  );
}