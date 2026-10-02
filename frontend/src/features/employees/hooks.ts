'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/lib/api-client';
import { describeProblem } from '@/lib/problem-details';
import { useToast } from '@/components/ui/Toast';
import {
  createCompensation,
  createEmployee,
  deactivateEmployee,
  getEmployee,
  listCompensation,
  listEmployees,
  listUsers,
  reactivateEmployee,
  resetUserPassword,
  setUserRoles,
  updateEmployee,
  updateEmployeeSensitive,
  type CreateEmployeeInput
} from './api';

const KEY = 'employees';

function useInvalidate() {
  const queryClient = useQueryClient();
  return () => void queryClient.invalidateQueries({ queryKey: [KEY] });
}

function useErrorToast() {
  const { push } = useToast();
  return (error: unknown, fallback: string) => {
    push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : fallback });
  };
}

export const useEmployees = (params: Parameters<typeof listEmployees>[0] = {}) =>
  useQuery({ queryKey: [KEY, 'list', params], queryFn: () => listEmployees(params) });

export const useEmployee = (id: string) =>
  useQuery({ queryKey: [KEY, 'detail', id], queryFn: () => getEmployee(id), enabled: Boolean(id) });

export const useUsers = (params: { status?: string; q?: string; page?: number } = {}) =>
  useQuery({ queryKey: [KEY, 'users', params], queryFn: () => listUsers(params) });

export const useCompensation = (id: string, enabled = true) =>
  useQuery({ queryKey: [KEY, 'compensation', id], queryFn: () => listCompensation(id), enabled: Boolean(id) && enabled });

export function useCreateEmployee() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: createEmployee,
    onSuccess: (result) => {
      invalidate();
      push({
        tone: 'success',
        title: `Employee ${result.employee.employee_code} created`,
        description: result.initial_password ? `One-time password: ${result.initial_password} (shown once)` : undefined
      });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not create the employee.' });
    }
  });
}

export function useUpdateEmployee() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<CreateEmployeeInput> }) => updateEmployee(id, body),
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Employee updated' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Update failed.' });
    }
  });
}

export function useUpdateEmployeeSensitive() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: { bank_account_name?: string; bank_account_number?: string; bank_ifsc?: string; reason: string } }) =>
      updateEmployeeSensitive(id, body),
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Sensitive details updated' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Update failed.' });
    }
  });
}

export function useDeactivateEmployee() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: { date_of_exit: string; reason: string; revoke_sessions?: boolean; force?: boolean } }) =>
      deactivateEmployee(id, body),
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Employee deactivated; history preserved' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not deactivate the employee.' });
    }
  });
}

export function useReactivateEmployee() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => reactivateEmployee(id, reason),
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Employee reactivated' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not reactivate the employee.' });
    }
  });
}

export function useCreateCompensation() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof createCompensation>[1] }) => createCompensation(id, body),
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Compensation row added' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not add compensation.' });
    }
  });
}

export function useSetUserRoles() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: { role_codes: string[]; reason: string } }) => setUserRoles(id, body),
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Roles updated' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not update roles.' });
    }
  });
}

export function useResetPassword() {
  const { push } = useToast();
  const toastError = useErrorToast();
  return useMutation({
    mutationFn: resetUserPassword,
    onSuccess: (data) => push({ tone: 'success', title: 'Reset token issued', description: 'It is shown once and never logged.' }),
    onError: (error) => toastError(error, 'Could not reset the password.')
  });
}