'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/lib/api-client';
import { describeProblem } from '@/lib/problem-details';
import { useToast } from '@/components/ui/Toast';
import {
  approveCorrection,
  cancelCorrection,
  checkIn,
  checkOut,
  createCorrection,
  createHoliday,
  createQrToken,
  deleteHoliday,
  endBreak,
  getAttendanceEvents,
  getAttendanceRecord,
  getAttendanceVerifications,
  getCurrentQrToken,
  getToday,
  listAttendance,
  listBreakTypes,
  listCorrections,
  listHolidays,
  listMyAttendance,
  listMyCorrections,
  mySummary,
  recomputeAttendance,
  rejectCorrection,
  startBreak,
  type AttendanceEvidence
} from './api';

const KEY = 'attendance';

export function useTodayAttendance() {
  return useQuery({ queryKey: [KEY, 'today'], queryFn: getToday, refetchOnMount: 'always' });
}

export function useMyAttendance(params: { from?: string; to?: string; page?: number } = {}) {
  return useQuery({ queryKey: [KEY, 'me', params], queryFn: () => listMyAttendance(params) });
}

export function useMyAttendanceSummary(params: { from?: string; to?: string } = {}) {
  return useQuery({ queryKey: [KEY, 'summary', params], queryFn: () => mySummary(params) });
}

export function useAdminAttendance(params: Parameters<typeof listAttendance>[0] = {}) {
  return useQuery({ queryKey: [KEY, 'all', params], queryFn: () => listAttendance(params) });
}

export function useAttendanceRecord(id: string) {
  return useQuery({ queryKey: [KEY, 'record', id], queryFn: () => getAttendanceRecord(id), enabled: Boolean(id) });
}

export function useAttendanceEvents(id: string) {
  return useQuery({ queryKey: [KEY, 'events', id], queryFn: () => getAttendanceEvents(id), enabled: Boolean(id) });
}

export function useAttendanceVerifications(id: string) {
  return useQuery({ queryKey: [KEY, 'verifications', id], queryFn: () => getAttendanceVerifications(id), enabled: Boolean(id) });
}

export function useBreakTypes(includeInactive = false) {
  return useQuery({ queryKey: [KEY, 'break-types', includeInactive], queryFn: () => listBreakTypes(includeInactive) });
}

export function useHolidays(year: number) {
  return useQuery({ queryKey: [KEY, 'holidays', year], queryFn: () => listHolidays(year), enabled: Number.isFinite(year) });
}

function useAttendanceInvalidation() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: [KEY] });
  };
}

export function useCheckIn() {
  const invalidate = useAttendanceInvalidation();
  return useMutation({
    mutationFn: ({ evidence, idempotencyKey }: { evidence: AttendanceEvidence; idempotencyKey: string }) =>
      checkIn(evidence, idempotencyKey),
    onSuccess: invalidate
  });
}

export function useCheckOut() {
  const invalidate = useAttendanceInvalidation();
  return useMutation({
    mutationFn: ({ evidence, idempotencyKey }: { evidence: AttendanceEvidence; idempotencyKey: string }) =>
      checkOut(evidence, idempotencyKey),
    onSuccess: invalidate
  });
}

export function useStartBreak() {
  const invalidate = useAttendanceInvalidation();
  return useMutation({
    mutationFn: ({ breakTypeId, idempotencyKey }: { breakTypeId: string; idempotencyKey: string }) =>
      startBreak(breakTypeId, idempotencyKey),
    onSuccess: invalidate
  });
}

export function useEndBreak() {
  const invalidate = useAttendanceInvalidation();
  return useMutation({ mutationFn: (idempotencyKey: string) => endBreak(idempotencyKey), onSuccess: invalidate });
}

export function useRecomputeAttendance() {
  const invalidate = useAttendanceInvalidation();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => recomputeAttendance(id, reason),
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Attendance recomputed from stored events' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Recompute failed.' });
    }
  });
}

// --- Corrections -----------------------------------------------------------

export function useMyCorrections(params: { status?: string; page?: number } = {}) {
  return useQuery({ queryKey: [KEY, 'corrections', 'mine', params], queryFn: () => listMyCorrections(params) });
}

export function useCorrections(params: Parameters<typeof listCorrections>[0] = {}) {
  return useQuery({ queryKey: [KEY, 'corrections', 'all', params], queryFn: () => listCorrections(params) });
}

export function useCreateCorrection() {
  const invalidate = useAttendanceInvalidation();
  const { push } = useToast();
  return useMutation({
    mutationFn: createCorrection,
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Correction request submitted for approval' });
    }
  });
}

export function useDecideCorrection() {
  const invalidate = useAttendanceInvalidation();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, action, notes }: { id: string; action: 'approve' | 'reject'; notes: string }) =>
      action === 'approve' ? approveCorrection(id, { decision_notes: notes }) : rejectCorrection(id, notes),
    onSuccess: (_data, variables) => {
      invalidate();
      push({ tone: 'success', title: variables.action === 'approve' ? 'Correction approved' : 'Correction rejected' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Decision failed.' });
    }
  });
}

export function useCancelCorrection() {
  const invalidate = useAttendanceInvalidation();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => cancelCorrection(id, reason),
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Correction request cancelled' });
    }
  });
}

// --- Admin configuration ---------------------------------------------------

export function useCreateHoliday() {
  const invalidate = useAttendanceInvalidation();
  const { push } = useToast();
  return useMutation({
    mutationFn: createHoliday,
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Holiday added' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not add holiday.' });
    }
  });
}

export function useDeleteHoliday() {
  const invalidate = useAttendanceInvalidation();
  return useMutation({ mutationFn: deleteHoliday, onSuccess: invalidate });
}

export function useIssueQrToken() {
  return useMutation({ mutationFn: (purpose?: string) => createQrToken(purpose) });
}

export function useCurrentQrToken(purpose: string, enabled: boolean) {
  return useQuery({
    queryKey: [KEY, 'qr-current', purpose],
    queryFn: () => getCurrentQrToken(purpose),
    enabled,
    retry: false
  });
}