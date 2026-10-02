'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/lib/api-client';
import { describeProblem } from '@/lib/problem-details';
import { useToast } from '@/components/ui/Toast';
import { useIdempotency } from '@/lib/idempotency';
import {
  adjustLeaveBalance,
  applyLeave,
  approveLeave,
  cancelLeave,
  createLeaveType,
  getLeave,
  listBalanceMovements,
  listLeaveBalances,
  listLeaveTypes,
  listLeaves,
  listMyLeaves,
  myLeaveBalances,
  rejectLeave,
  requestLeaveModification,
  updateLeaveType,
  type LeaveApplicationInput
} from './api';

const KEY = 'leaves';

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

export const useLeaveTypes = (includeInactive = false) =>
  useQuery({ queryKey: [KEY, 'types', includeInactive], queryFn: () => listLeaveTypes(includeInactive) });

export const useMyLeaves = (params: { status?: string; page?: number } = {}) =>
  useQuery({ queryKey: [KEY, 'mine', params], queryFn: () => listMyLeaves(params) });

export const useLeaves = (params: Parameters<typeof listLeaves>[0] = {}) =>
  useQuery({ queryKey: [KEY, 'all', params], queryFn: () => listLeaves(params) });

export const useLeave = (id: string) => useQuery({ queryKey: [KEY, 'leave', id], queryFn: () => getLeave(id), enabled: Boolean(id) });

export const useMyLeaveBalances = (periodYear?: number) =>
  useQuery({ queryKey: [KEY, 'balances', 'mine', periodYear ?? 'current'], queryFn: () => myLeaveBalances(periodYear) });

export const useLeaveBalances = (params: Parameters<typeof listLeaveBalances>[0] = {}) =>
  useQuery({ queryKey: [KEY, 'balances', 'all', params], queryFn: () => listLeaveBalances(params) });

export const useBalanceMovements = (id: string, enabled = true) =>
  useQuery({ queryKey: [KEY, 'movements', id], queryFn: () => listBalanceMovements(id), enabled: Boolean(id) && enabled });

export function useApplyLeave() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  const idem = useIdempotency();
  return useMutation({
    mutationFn: (body: LeaveApplicationInput) => applyLeave(body, idem.key()),
    onSuccess: () => {
      idem.reset();
      invalidate();
      push({ tone: 'success', title: 'Leave request submitted' });
    },
    onError: (error) => {
      const message = error instanceof ApiError ? describeProblem(error.problem).title : 'Could not submit the leave request.';
      push({ tone: 'error', title: message });
    }
  });
}

export function useDecideLeave() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: async ({ id, action, notes }: { id: string; action: 'approve' | 'reject' | 'request-modification'; notes?: string }) => {
      if (action === 'approve') return approveLeave(id, notes);
      if (action === 'reject') return rejectLeave(id, notes ?? '');
      return requestLeaveModification(id, notes ?? '');
    },
    onSuccess: (_data, variables) => {
      invalidate();
      push({ tone: 'success', title: `Leave ${variables.action.replace('-', ' ')} recorded` });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Decision failed.' });
    }
  });
}

export function useCancelLeave() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => cancelLeave(id, reason),
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Leave cancelled' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not cancel the leave.' });
    }
  });
}

export function useAdjustLeaveBalance() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: adjustLeaveBalance,
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Balance adjusted' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Adjustment failed.' });
    }
  });
}

export function useCreateLeaveType() {
  const invalidate = useInvalidate();
  const toastError = useErrorToast();
  return useMutation({
    mutationFn: createLeaveType,
    onSuccess: invalidate,
    onError: (error) => toastError(error, 'Could not create the leave type.')
  });
}

export function useUpdateLeaveType() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof updateLeaveType>[1] }) => updateLeaveType(id, body),
    onSuccess: invalidate
  });
}