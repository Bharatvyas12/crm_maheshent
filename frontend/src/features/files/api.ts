'use client';

import { api, apiFetch, API_BASE_URL } from '@/lib/api-client';
import type { FileMeta } from '@/lib/types';

/** Upload a file and return its metadata. The server validates size/type and scans content. */
export function uploadFile(file: File, purpose: string, idempotencyKey?: string): Promise<FileMeta> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('purpose', purpose);
  return apiFetch<FileMeta>('/files', { method: 'POST', formData, idempotencyKey });
}

export function getFile(id: string) {
  return api.get<FileMeta>(`/files/${id}`);
}

export function getFileUrl(id: string, disposition?: 'inline' | 'attachment') {
  return api.get<{ url: string; expires_at: string }>(`/files/${id}/url`, { disposition });
}

export function deleteFile(id: string) {
  return api.delete<void>(`/files/${id}`);
}

export { API_BASE_URL };