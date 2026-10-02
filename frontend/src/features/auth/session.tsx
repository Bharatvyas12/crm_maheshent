'use client';

import { createContext, useCallback, useContext, useMemo, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/lib/api-client';
import { EMPLOYEE_PERMISSIONS, hasAnyPermission } from '@/lib/permissions';
import type { Employee, SessionPayload, SessionSettings, User } from '@/lib/types';
import { fetchSession, logout as logoutRequest } from './api';

interface SessionContextValue {
  user: User | null;
  employee: Employee | null;
  roles: string[];
  permissions: string[];
  settings: SessionSettings;
  isLoading: boolean;
  isAuthenticated: boolean;
  isAdminExperience: boolean;
  mustChangePassword: boolean;
  refetch: () => void;
  signOut: () => Promise<void>;
}

const EMPTY_SETTINGS: SessionSettings = { business_timezone: 'UTC', currency: 'INR' };

const SessionContext = createContext<SessionContextValue | null>(null);

const EMPLOYEE_PERMISSION_SET = new Set<string>(EMPLOYEE_PERMISSIONS);

/**
 * A user is shown the admin experience when they hold at least one permission outside the
 * seeded EMPLOYEE set (docs/05_PERMISSIONS.md section 4.2). This is a navigation decision only.
 */
export function prefersAdminExperience(permissions: readonly string[]): boolean {
  return permissions.some((code) => !EMPLOYEE_PERMISSION_SET.has(code)) || permissions.length === 0;
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  const query = useQuery<SessionPayload | null>({
    queryKey: ['session'],
    queryFn: async () => {
      try {
        return await fetchSession();
      } catch (error) {
        if (error instanceof ApiError && error.isUnauthenticated) return null;
        throw error;
      }
    },
    staleTime: 30_000,
    retry: false,
    refetchOnWindowFocus: false
  });

  const mutation = useMutation({
    mutationFn: logoutRequest,
    onSettled: () => {
      queryClient.clear();
    }
  });

  const signOut = useCallback(async () => {
    try {
      await mutation.mutateAsync();
    } finally {
      queryClient.clear();
    }
  }, [mutation, queryClient]);

  const session = query.data ?? null;

  const value = useMemo<SessionContextValue>(() => {
    const permissions = session?.permissions ?? [];
    return {
      user: session?.user ?? null,
      employee: session?.employee ?? null,
      roles: session?.roles ?? [],
      permissions,
      settings: session?.settings ?? EMPTY_SETTINGS,
      isLoading: query.isLoading,
      isAuthenticated: Boolean(session?.user),
      isAdminExperience: prefersAdminExperience(permissions),
      mustChangePassword: session?.user?.must_change_password ?? false,
      refetch: () => {
        void query.refetch();
      },
      signOut
    };
  }, [session, query.isLoading, query, signOut]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) throw new Error('useSession must be used within a SessionProvider');
  return context;
}

/** Permission helper bound to the current session. UX only. */
export function usePermissions() {
  const { permissions } = useSession();
  return useMemo(
    () => ({
      permissions,
      can: (code: string) => permissions.includes(code),
      canAny: (codes: readonly string[]) => hasAnyPermission(permissions, codes)
    }),
    [permissions]
  );
}