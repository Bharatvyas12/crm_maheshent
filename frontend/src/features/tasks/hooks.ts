'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/lib/api-client';
import { describeProblem } from '@/lib/problem-details';
import { useToast } from '@/components/ui/Toast';
import { useIdempotency } from '@/lib/idempotency';
import {
  addTaskAttachment,
  approveSubmission,
  assignTask,
  cancelTask,
  commentOnAssignment,
  commentOnTask,
  completeAssignment,
  createTask,
  getAssignment,
  getTask,
  listAssignments,
  listSubmissions,
  listTasks,
  rejectSubmission,
  removeAssignment,
  requestResubmission,
  startAssignment,
  submitAssignment,
  updateTask
} from './api';

const KEY = 'tasks';

function useInvalidate() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: [KEY] });
    void queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] });
  };
}

function useErrorToast() {
  const { push } = useToast();
  return (error: unknown, fallback: string) => {
    push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : fallback });
  };
}

export const useMyAssignments = (params: { status?: string; due_before?: string; sort?: string; page?: number } = {}) =>
  useQuery({ queryKey: [KEY, 'assignments', 'mine', params], queryFn: () => listAssignments(params) });

export const useAssignment = (id: string) =>
  useQuery({ queryKey: [KEY, 'assignment', id], queryFn: () => getAssignment(id), enabled: Boolean(id) });

export function useStartAssignment() {
  const invalidate = useInvalidate();
  const toastError = useErrorToast();
  return useMutation({
    mutationFn: startAssignment,
    onSuccess: invalidate,
    onError: (error) => toastError(error, 'Could not start the task.')
  });
}

export function useCompleteAssignment() {
  const invalidate = useInvalidate();
  const toastError = useErrorToast();
  return useMutation({
    mutationFn: ({ id, description }: { id: string; description?: string }) => completeAssignment(id, description),
    onSuccess: invalidate,
    onError: (error) => toastError(error, 'Could not mark the task complete.')
  });
}

export function useSubmitAssignment() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  const idem = useIdempotency();
  return useMutation({
    mutationFn: ({ id, description, attachmentFileIds }: { id: string; description?: string; attachmentFileIds?: string[] }) =>
      submitAssignment(id, { description, attachment_file_ids: attachmentFileIds }, idem.key()),
    onSuccess: (submission) => {
      idem.reset();
      invalidate();
      push({ tone: 'success', title: `Submitted (attempt ${submission.attempt_no})` });
    },
    onError: (error) => {
      const message = error instanceof ApiError ? describeProblem(error.problem).title : 'Submission failed.';
      push({ tone: 'error', title: message });
      // Keep the same idempotency key so a retry of this same attempt is not duplicated.
    }
  });
}

export function useCommentOnAssignment() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: string }) => commentOnAssignment(id, body),
    onSuccess: invalidate
  });
}

// --- Admin -----------------------------------------------------------------

export const useTasks = (params: Parameters<typeof listTasks>[0] = {}) =>
  useQuery({ queryKey: [KEY, 'all', params], queryFn: () => listTasks(params) });

export const useTask = (id: string) => useQuery({ queryKey: [KEY, 'task', id], queryFn: () => getTask(id), enabled: Boolean(id) });

export function useCreateTask() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: createTask,
    onSuccess: (task) => {
      invalidate();
      push({ tone: 'success', title: `Task created with ${task.assignments?.length ?? 0} assignment(s)` });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not create the task.' });
    }
  });
}

export function useUpdateTask() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof updateTask>[1] }) => updateTask(id, body),
    onSuccess: invalidate
  });
}

export function useCancelTask() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => cancelTask(id, reason),
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Task cancelled and open assignments notified' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not cancel the task.' });
    }
  });
}

export function useAssignTask() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: { employee_ids: string[]; due_at?: string | null } }) => assignTask(id, body),
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Assignment added' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not assign the task.' });
    }
  });
}

export function useRemoveAssignment() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ taskId, assignmentId }: { taskId: string; assignmentId: string }) => removeAssignment(taskId, assignmentId),
    onSuccess: invalidate
  });
}

export function useAddTaskAttachment() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, fileId }: { id: string; fileId: string }) => addTaskAttachment(id, fileId),
    onSuccess: invalidate
  });
}

// --- Review ----------------------------------------------------------------

export const useSubmissions = (params: { status?: string; employee_id?: string; page?: number } = {}) =>
  useQuery({ queryKey: [KEY, 'submissions', params], queryFn: () => listSubmissions(params) });

export function useReviewSubmission() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: async ({ id, action, notes }: { id: string; action: 'approve' | 'reject' | 'request-resubmission'; notes?: string }) => {
      if (action === 'approve') return approveSubmission(id, notes);
      if (action === 'reject') return rejectSubmission(id, notes ?? '');
      return requestResubmission(id, notes ?? '');
    },
    onSuccess: (_data, variables) => {
      invalidate();
      push({
        tone: 'success',
        title:
          variables.action === 'approve'
            ? 'Submission approved'
            : variables.action === 'reject'
              ? 'Submission rejected'
              : 'Resubmission requested'
      });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Review failed.' });
    }
  });
}

export function useCommentOnTask() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: { body: string; assignment_id?: string; is_internal?: boolean } }) =>
      commentOnTask(id, body),
    onSuccess: invalidate
  });
}