'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/lib/api-client';
import { describeProblem } from '@/lib/problem-details';
import { useToast } from '@/components/ui/Toast';
import { useIdempotency } from '@/lib/idempotency';
import {
  addAdvanceRepayment,
  approveAdvance,
  computePayrollRun,
  createAdvance,
  createLedgerEntry,
  createPayrollRun,
  finalizePayrollRun,
  getAdvance,
  getLedgerEntry,
  getPayrollRun,
  ledgerBalance,
  listAdvances,
  listLedger,
  listPayrollRuns,
  getSalaryRecord,
  listSalaryRecords,
  lockPayrollRun,
  markPayrollRunPaid,
  myAdvances,
  myLedger,
  rejectAdvance,
  reverseLedgerEntry,
  unlockPayrollRun,
  writeOffAdvance,
  type AdvanceCreateInput,
  type LedgerEntryInput
} from './api';

const KEY = 'ledger';

function useInvalidate() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: [KEY] });
    void queryClient.invalidateQueries({ queryKey: ['payroll'] });
    void queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] });
  };
}

function useErrorToast() {
  const { push } = useToast();
  return (error: unknown, fallback: string) => {
    push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : fallback });
  };
}

export const useMyLedger = (params: { from?: string; to?: string; entry_type?: string; page?: number } = {}) =>
  useQuery({ queryKey: [KEY, 'mine', params], queryFn: () => myLedger(params) });

export const useLedger = (params: Parameters<typeof listLedger>[0] = {}) =>
  useQuery({ queryKey: [KEY, 'all', params], queryFn: () => listLedger(params) });

export const useLedgerEntry = (id: string) =>
  useQuery({ queryKey: [KEY, 'entry', id], queryFn: () => getLedgerEntry(id), enabled: Boolean(id) });

export const useLedgerBalance = (employeeId: string, enabled = true) =>
  useQuery({
    queryKey: [KEY, 'balance', employeeId],
    queryFn: () => ledgerBalance(employeeId),
    enabled: Boolean(employeeId) && enabled
  });

export function useCreateLedgerEntry() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  const idem = useIdempotency();
  return useMutation({
    mutationFn: (body: LedgerEntryInput) => createLedgerEntry(body, idem.key()),
    onSuccess: () => {
      idem.reset();
      invalidate();
      push({ tone: 'success', title: 'Ledger entry posted' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not post the entry.' });
    }
  });
}

export function useReverseLedgerEntry() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => reverseLedgerEntry(id, reason),
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Reversal entry posted; the original remains visible' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Reversal failed.' });
    }
  });
}

// --- Advances --------------------------------------------------------------

export const useMyAdvances = (params: { status?: string; page?: number } = {}) =>
  useQuery({ queryKey: [KEY, 'advances', 'mine', params], queryFn: () => myAdvances(params) });

export const useAdvances = (params: Parameters<typeof listAdvances>[0] = {}) =>
  useQuery({ queryKey: [KEY, 'advances', 'all', params], queryFn: () => listAdvances(params) });

export const useAdvance = (id: string) =>
  useQuery({ queryKey: [KEY, 'advance', id], queryFn: () => getAdvance(id), enabled: Boolean(id) });

export function useCreateAdvance() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  const idem = useIdempotency();
  return useMutation({
    mutationFn: (body: AdvanceCreateInput) => createAdvance(body, idem.key()),
    onSuccess: (advance) => {
      idem.reset();
      invalidate();
      push({ tone: 'success', title: `Advance ${advance.status === 'PENDING_APPROVAL' ? 'submitted for approval' : 'issued'}` });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not issue the advance.' });
    }
  });
}

export function useDecideAdvance() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, action, notes }: { id: string; action: 'approve' | 'reject'; notes?: string }) =>
      action === 'approve' ? approveAdvance(id, notes) : rejectAdvance(id, notes ?? ''),
    onSuccess: (_data, variables) => {
      invalidate();
      push({ tone: 'success', title: variables.action === 'approve' ? 'Advance approved' : 'Advance rejected' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Decision failed.' });
    }
  });
}

export function useAddAdvanceRepayment() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  const idem = useIdempotency();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: { amount: string; business_date: string; reason: string } }) =>
      addAdvanceRepayment(id, body, idem.key()),
    onSuccess: () => {
      idem.reset();
      invalidate();
      push({ tone: 'success', title: 'Repayment recorded' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Repayment failed.' });
    }
  });
}

export function useWriteOffAdvance() {
  const invalidate = useInvalidate();
  const toastError = useErrorToast();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: { amount?: string; reason: string } }) => writeOffAdvance(id, body),
    onSuccess: invalidate,
    onError: (error) => toastError(error, 'Write-off failed.')
  });
}

// --- Payroll ---------------------------------------------------------------

export const usePayrollRuns = (params: { period_year?: number; status?: string; page?: number } = {}) =>
  useQuery({ queryKey: ['payroll', 'runs', params], queryFn: () => listPayrollRuns(params) });

export const usePayrollRun = (id: string) =>
  useQuery({ queryKey: ['payroll', 'run', id], queryFn: () => getPayrollRun(id), enabled: Boolean(id) });

export const useSalaryRecords = (params: { payroll_run_id?: string; status?: string; page?: number } = {}) =>
  useQuery({
    queryKey: ['payroll', 'records', params],
    queryFn: () => listSalaryRecords(params),
    enabled: Boolean(params.payroll_run_id)
  });

export const useSalaryRecord = (id: string) =>
  useQuery({ queryKey: ['payroll', 'record', id], queryFn: () => getSalaryRecord(id), enabled: Boolean(id) });

export function useCreatePayrollRun() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: createPayrollRun,
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Payroll run created' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not create the run.' });
    }
  });
}

function useRunAction<T>(fn: (args: T) => Promise<unknown>, successTitle: string) {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: successTitle });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Payroll action failed.' });
    }
  });
}

export const useComputePayrollRun = () =>
  useRunAction<{ id: string; employee_ids?: string[]; reason?: string }>(
    ({ id, ...body }) => computePayrollRun(id, body),
    'Payroll computed'
  );

export const useFinalizePayrollRun = () =>
  useRunAction<{ id: string; reason?: string; force?: boolean }>(
    ({ id, reason, force }) => finalizePayrollRun(id, reason, force),
    'Payroll finalized (records are now immutable)'
  );

export const useLockPayrollRun = () => useRunAction<{ id: string; reason: string }>(({ id, reason }) => lockPayrollRun(id, reason), 'Payroll period locked');

export const useUnlockPayrollRun = () => useRunAction<{ id: string; reason: string }>(({ id, reason }) => unlockPayrollRun(id, reason), 'Payroll period unlocked');

export function useMarkPayrollPaid() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  const idem = useIdempotency();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: { paid_on: string; reason?: string } }) => markPayrollRunPaid(id, body, idem.key()),
    onSuccess: () => {
      idem.reset();
      invalidate();
      push({ tone: 'success', title: 'Payroll marked as paid' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not mark as paid.' });
    }
  });
}