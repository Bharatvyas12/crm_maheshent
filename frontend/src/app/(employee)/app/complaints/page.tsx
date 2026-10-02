'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ApiError } from '@/lib/api-client';
import { describeProblem } from '@/lib/problem-details';
import { formatDateTime, humanize } from '@/lib/format';
import { useComplaintCategories, useCreateComplaint, useMyComplaints } from '@/features/complaints/hooks';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { TextField, TextAreaField, SelectField } from '@/components/ui/Form';
import { StatusPill } from '@/components/ui/StatusPill';
import { SkeletonList } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { Alert } from '@/components/ui/Alert';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { FileUploadField, type UploadedFile } from '@/components/FileUploadField';

export default function EmployeeComplaintsPage() {
  const categories = useComplaintCategories();
  const complaints = useMyComplaints({});
  const create = useCreateComplaint();

  const [open, setOpen] = useState(false);
  const [categoryId, setCategoryId] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState('');
  const [attachments, setAttachments] = useState<UploadedFile[]>([]);
  const [error, setError] = useState<string | null>(null);

  const createError = create.error instanceof ApiError ? create.error : null;

  function submit() {
    setError(null);
    if (!categoryId) return setError('Choose a category.');
    if (title.trim().length < 3) return setError('Give the complaint a short title.');
    if (description.trim().length < 10) return setError('Describe what happened.');

    create.mutate(
      {
        category_id: categoryId,
        title: title.trim(),
        description: description.trim(),
        priority: priority || undefined,
        attachment_file_ids: attachments.map((file) => file.id)
      },
      {
        onSuccess: () => {
          setOpen(false);
          setCategoryId('');
          setTitle('');
          setDescription('');
          setPriority('');
          setAttachments([]);
        }
      }
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Complaints</h1>
          <p className="text-sm text-content-muted">Raise an issue and follow its progress.</p>
        </div>
        <Button className="mt-1" onClick={() => setOpen(true)}>
          New
        </Button>
      </div>

      {complaints.isLoading ? (
        <SkeletonList rows={3} />
      ) : complaints.error ? (
        <ProblemAlert error={complaints.error} onRetry={() => void complaints.refetch()} />
      ) : (complaints.data?.items.length ?? 0) === 0 ? (
        <EmptyState title="No complaints" hint="Anything you raise will appear here with its status." />
      ) : (
        <ul className="space-y-2">
          {complaints.data?.items.map((complaint) => (
            <li key={complaint.id}>
              <Link href={`/app/complaints/${complaint.id}`} className="block">
                <Card className="transition-shadow hover:shadow-md">
                  <CardHeader action={<StatusPill value={complaint.status} />}>
                    <CardTitle>{complaint.title}</CardTitle>
                    <p className="mt-0.5 text-xs text-content-muted">
                      {complaint.complaint_code} - {complaint.category?.name ?? 'Uncategorised'}
                    </p>
                  </CardHeader>
                  <CardBody>
                    <p className="line-clamp-2 text-xs text-content-muted">{complaint.description}</p>
                    <p className="mt-1 text-xs text-content-muted">Opened {formatDateTime(complaint.created_at)}</p>
                  </CardBody>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}

      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Submit a complaint"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={submit} loading={create.isPending} disabled={create.isPending}>
              Submit
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {createError ? (
            <Alert tone="danger" title={describeProblem(createError.problem).title} nextStep={describeProblem(createError.problem).nextStep}>
              {createError.problem.detail ? <p>{createError.problem.detail}</p> : null}
            </Alert>
          ) : null}
          {error ? <Alert tone="danger" title={error} /> : null}

          <SelectField
            label="Category"
            name="category_id"
            required
            placeholder="Select a category"
            value={categoryId}
            onChange={(event) => setCategoryId(event.target.value)}
            options={(categories.data?.items ?? []).map((category) => ({ value: category.id, label: category.name }))}
          />
          <TextField label="Title" name="title" required value={title} onChange={(event) => setTitle(event.target.value)} />
          <TextAreaField
            label="What happened?"
            name="description"
            required
            rows={5}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
          <SelectField
            label="Priority (if you may set it)"
            name="priority"
            placeholder="Let the admin decide"
            value={priority}
            onChange={(event) => setPriority(event.target.value)}
            options={[
              { value: 'LOW', label: 'Low' },
              { value: 'NORMAL', label: 'Normal' },
              { value: 'HIGH', label: 'High' },
              { value: 'URGENT', label: 'Urgent' }
            ]}
          />
          <FileUploadField purpose="COMPLAINT_EVIDENCE" label="Evidence" accept="image/*,.pdf" multiple onUploaded={setAttachments} />
        </div>
      </Dialog>

      <p className="text-xs text-content-muted">
        Categories: {(categories.data?.items ?? []).map((category) => humanize(category.name)).join(', ') || 'none configured'}
      </p>
    </div>
  );
}