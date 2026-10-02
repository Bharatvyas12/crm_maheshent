'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/lib/api-client';
import { describeProblem } from '@/lib/problem-details';
import { useToast } from '@/components/ui/Toast';
import {
  addComplaintAttachment,
  addComplaintComment,
  closeComplaint,
  createComplaint,
  getComplaint,
  listComplaintCategories,
  listComplaintComments,
  listComplaints,
  listMyComplaints,
  rejectComplaint,
  resolveComplaint,
  updateComplaint,
  updateComplaintStatus
} from './api';

const KEY = 'complaints';

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

export const useComplaintCategories = (includeInactive = false) =>
  useQuery({ queryKey: [KEY, 'categories', includeInactive], queryFn: () => listComplaintCategories(includeInactive) });

export const useMyComplaints = (params: { status?: string; page?: number } = {}) =>
  useQuery({ queryKey: [KEY, 'mine', params], queryFn: () => listMyComplaints(params) });

export const useComplaints = (params: Parameters<typeof listComplaints>[0] = {}) =>
  useQuery({ queryKey: [KEY, 'all', params], queryFn: () => listComplaints(params) });

export const useComplaint = (id: string) =>
  useQuery({ queryKey: [KEY, 'complaint', id], queryFn: () => getComplaint(id), enabled: Boolean(id) });

export const useComplaintComments = (id: string, includeInternal = false) =>
  useQuery({
    queryKey: [KEY, 'comments', id, includeInternal],
    queryFn: () => listComplaintComments(id, includeInternal),
    enabled: Boolean(id)
  });

export function useCreateComplaint() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: createComplaint,
    onSuccess: (complaint) => {
      invalidate();
      push({ tone: 'success', title: `Complaint ${complaint.complaint_code} submitted` });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not submit the complaint.' });
    }
  });
}

export function useUpdateComplaint() {
  const invalidate = useInvalidate();
  const toastError = useErrorToast();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof updateComplaint>[1] }) => updateComplaint(id, body),
    onSuccess: invalidate,
    onError: (error) => toastError(error, 'Could not update the complaint.')
  });
}

export function useComplaintStatus() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: { to_status: string; reason?: string; internal_note?: string } }) =>
      updateComplaintStatus(id, body),
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Complaint status updated' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Status change failed.' });
    }
  });
}

export function useResolveComplaint() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, summary }: { id: string; summary: string }) => resolveComplaint(id, summary),
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Complaint resolved' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not resolve the complaint.' });
    }
  });
}

export function useCloseComplaint() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string }) => closeComplaint(id, note),
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Complaint closed' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not close the complaint.' });
    }
  });
}

export function useRejectComplaint() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => rejectComplaint(id, reason),
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Complaint rejected' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not reject the complaint.' });
    }
  });
}

export function useAddComplaintComment() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: { body: string; is_internal?: boolean } }) => addComplaintComment(id, body),
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Comment added' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not add the comment.' });
    }
  });
}

export function useAddComplaintAttachment() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: { file_id: string; note?: string } }) => addComplaintAttachment(id, body),
    onSuccess: invalidate
  });
}