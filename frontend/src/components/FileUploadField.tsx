'use client';

import { useRef, useState } from 'react';
import { ApiError } from '@/lib/api-client';
import { describeProblem } from '@/lib/problem-details';
import { uploadFile } from '@/features/files/api';
import { Button } from '@/components/ui/Button';
import { Alert } from '@/components/ui/Alert';
import type { FileMeta } from '@/lib/types';

export interface UploadedFile {
  id: string;
  meta: FileMeta;
}

/**
 * Reusable evidence upload used by task submissions, order proof and complaint attachments.
 * Upload is a separate mutation from the record that references the file, matching
 * docs/03_API_CONTRACT.md section 14 and workflow W-29.
 */
export function FileUploadField({
  purpose,
  label,
  help,
  accept,
  multiple,
  onUploaded,
  testId
}: {
  purpose: string;
  label: string;
  help?: string;
  accept?: string;
  multiple?: boolean;
  onUploaded: (files: UploadedFile[]) => void;
  testId?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState<UploadedFile[]>([]);

  async function handleFiles(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;
    setUploading(true);
    setError(null);
    const results: UploadedFile[] = [];
    try {
      for (const file of Array.from(fileList)) {
        const meta = await uploadFile(file, purpose);
        results.push({ id: meta.id, meta });
      }
      const next = [...uploaded, ...results];
      setUploaded(next);
      onUploaded(next);
    } catch (err) {
      setError(err instanceof ApiError ? describeProblem(err.problem).title : 'Upload failed.');
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  }

  return (
    <div className="space-y-2" data-testid={testId}>
      <p className="text-sm font-medium text-content">{label}</p>
      {help ? <p className="text-xs text-content-muted">{help}</p> : null}
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        aria-label={label}
        disabled={uploading}
        onChange={(event) => void handleFiles(event.target.files)}
        className="block w-full text-sm text-content-muted file:mr-3 file:min-h-touch file:rounded-md file:border file:border-surface-border file:bg-surface file:px-3 file:text-sm file:font-medium"
      />
      {uploading ? <p className="text-xs text-content-muted">Uploading...</p> : null}
      {error ? <Alert tone="danger" title={error} /> : null}
      {uploaded.length > 0 ? (
        <ul className="space-y-1">
          {uploaded.map((file) => (
            <li key={file.id} className="flex items-center justify-between gap-2 rounded border border-surface-border px-2 py-1 text-xs">
              <span className="truncate">{file.meta.original_name}</span>
              <span className="shrink-0 text-content-muted">{Math.round(file.meta.size_bytes / 1024)} KB</span>
            </li>
          ))}
        </ul>
      ) : null}
      {uploaded.length > 0 ? (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setUploaded([]);
            onUploaded([]);
          }}
        >
          Clear attachments
        </Button>
      ) : null}
    </div>
  );
}