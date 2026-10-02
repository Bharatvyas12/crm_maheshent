'use client';

import { api, apiFetch } from '@/lib/api-client';
import type { ListResponse, Paginated, Task, TaskAssignment, TaskComment, TaskSubmission } from '@/lib/types';

export function listAssignments(params: { status?: string; due_before?: string; sort?: string; page?: number } = {}) {
  return api.get<Paginated<TaskAssignment>>('/task-assignments/mine', params);
}

export function getAssignment(id: string) {
  return api.get<TaskAssignment>(`/task-assignments/${id}`);
}

export function startAssignment(id: string) {
  return api.post<TaskAssignment>(`/task-assignments/${id}/start`);
}

export function completeAssignment(id: string, description?: string) {
  return api.post<TaskAssignment>(`/task-assignments/${id}/complete`, description ? { description } : {});
}

export function submitAssignment(
  id: string,
  body: { description?: string; attachment_file_ids?: string[] },
  idempotencyKey: string
) {
  return apiFetch<TaskSubmission>(`/task-assignments/${id}/submissions`, { method: 'POST', body, idempotencyKey });
}

export function commentOnAssignment(id: string, body: string) {
  return api.post<TaskComment>(`/task-assignments/${id}/comments`, { body });
}

// --- Admin -----------------------------------------------------------------

export function listTasks(params: { status?: string; priority?: string; assignee_employee_id?: string; from?: string; to?: string; q?: string; sort?: string; page?: number } = {}) {
  return api.get<Paginated<Task>>('/tasks', params);
}

export interface CreateTaskInput {
  title: string;
  description?: string;
  priority?: string;
  due_at?: string | null;
  requires_evidence?: boolean;
  requires_attachment?: boolean;
  assignee_employee_ids: string[];
  brief_attachment_file_ids?: string[];
}

export function createTask(body: CreateTaskInput) {
  return api.post<Task>('/tasks', body);
}

export function getTask(id: string) {
  return api.get<Task>(`/tasks/${id}`);
}

export function updateTask(id: string, body: Partial<CreateTaskInput>) {
  return api.patch<Task>(`/tasks/${id}`, body);
}

export function cancelTask(id: string, reason: string) {
  return api.post<Task>(`/tasks/${id}/cancel`, { reason });
}

export function assignTask(id: string, body: { employee_ids: string[]; due_at?: string | null }) {
  return api.post<ListResponse<TaskAssignment>>(`/tasks/${id}/assignments`, body);
}

export function removeAssignment(taskId: string, assignmentId: string) {
  return api.delete<void>(`/tasks/${taskId}/assignments/${assignmentId}`);
}

export function addTaskAttachment(id: string, fileId: string) {
  return api.post<Task>(`/tasks/${id}/attachments`, { file_id: fileId, attachment_type: 'BRIEF' });
}

// --- Review ----------------------------------------------------------------

export function listSubmissions(params: { status?: string; employee_id?: string; page?: number } = {}) {
  return api.get<Paginated<TaskSubmission>>('/task-submissions', params);
}

export function approveSubmission(id: string, reviewNotes?: string) {
  return api.post<TaskSubmission>(`/task-submissions/${id}/approve`, reviewNotes ? { review_notes: reviewNotes } : {});
}

export function rejectSubmission(id: string, reviewNotes: string) {
  return api.post<TaskSubmission>(`/task-submissions/${id}/reject`, { review_notes: reviewNotes });
}

export function requestResubmission(id: string, reviewNotes: string) {
  return api.post<TaskSubmission>(`/task-submissions/${id}/request-resubmission`, { review_notes: reviewNotes });
}

export function commentOnTask(id: string, body: { body: string; assignment_id?: string; is_internal?: boolean }) {
  return api.post<TaskComment>(`/tasks/${id}/comments`, body);
}