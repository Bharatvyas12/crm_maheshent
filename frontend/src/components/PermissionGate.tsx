'use client';

import type { ReactNode } from 'react';
import { usePermissions } from '@/features/auth/session';
import { hasAllPermissions, type PermissionCode } from '@/lib/permissions';

interface PermissionGateProps {
  /** Render children only when the user holds any of these permissions. */
  anyOf?: PermissionCode[];
  /** Render children only when the user holds all of these permissions. */
  allOf?: PermissionCode[];
  fallback?: ReactNode;
  children: ReactNode;
}

/**
 * Hides UI the user cannot use. This is UX-only: the backend enforces every protected
 * operation regardless of what is rendered (docs/05_PERMISSIONS.md section 1).
 */
export function PermissionGate({ anyOf, allOf, fallback = null, children }: PermissionGateProps) {
  const { permissions } = usePermissions();

  if (allOf && allOf.length > 0 && !hasAllPermissions(permissions, allOf)) {
    return <>{fallback}</>;
  }
  if (anyOf && anyOf.length > 0 && !anyOf.some((code) => permissions.includes(code))) {
    return <>{fallback}</>;
  }
  return <>{children}</>;
}