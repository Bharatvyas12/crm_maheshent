'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/lib/api-client';
import { describeProblem } from '@/lib/problem-details';
import { useToast } from '@/components/ui/Toast';
import { createRole, deleteRole, getRole, listPermissions, listRoles, setRolePermissions, updateRole } from './api';

const KEY = 'rbac';

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

export const useRoles = (params: { include_system?: boolean; page?: number } = {}) =>
  useQuery({ queryKey: [KEY, 'roles', params], queryFn: () => listRoles(params) });

export const useRole = (id: string) =>
  useQuery({ queryKey: [KEY, 'role', id], queryFn: () => getRole(id), enabled: Boolean(id) });

export const usePermissionCatalog = (module?: string) =>
  useQuery({ queryKey: [KEY, 'permissions', module ?? 'all'], queryFn: () => listPermissions(module), staleTime: 5 * 60_000 });

export function useCreateRole() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: createRole,
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Role created' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not create the role.' });
    }
  });
}

export function useUpdateRole() {
  const invalidate = useInvalidate();
  const toastError = useErrorToast();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof updateRole>[1] }) => updateRole(id, body),
    onSuccess: invalidate,
    onError: (error) => toastError(error, 'Could not update the role.')
  });
}

export function useSetRolePermissions() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: { permission_codes: string[]; reason: string } }) => setRolePermissions(id, body),
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Role permissions updated' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not update permissions.' });
    }
  });
}

export function useDeleteRole() {
  const invalidate = useInvalidate();
  const { push } = useToast();
  return useMutation({
    mutationFn: deleteRole,
    onSuccess: () => {
      invalidate();
      push({ tone: 'success', title: 'Role deleted' });
    },
    onError: (error) => {
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not delete the role.' });
    }
  });
}