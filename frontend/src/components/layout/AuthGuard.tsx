'use client';

import { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useSession } from '@/features/auth/session';
import { Spinner } from '@/components/ui/Spinner';

export function FullPageSpinner({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <Spinner className="text-primary" label={label} />
    </div>
  );
}

/**
 * Client-side auth/experience guard. UX only - the backend enforces every operation
 * (docs/05_PERMISSIONS.md section 1). Redirects preserve the intended destination for safe
 * navigation (docs/07_UI_SPEC.md section 10).
 */
export function AuthGuard({ requireAdmin = false, children }: { requireAdmin?: boolean; children: React.ReactNode }) {
  const { isLoading, isAuthenticated, isAdminExperience, mustChangePassword } = useSession();
  const pathname = usePathname();
  const router = useRouter();

  const blockedByRole = requireAdmin && isAuthenticated && !isAdminExperience;
  const blockedByPassword = isAuthenticated && mustChangePassword;

  useEffect(() => {
    if (isLoading) return;
    if (!isAuthenticated) {
      router.replace(`/login?next=${encodeURIComponent(pathname || '/')}`);
      return;
    }
    if (blockedByPassword) {
      router.replace('/change-password');
      return;
    }
    if (blockedByRole) {
      router.replace('/app');
    }
  }, [isLoading, isAuthenticated, blockedByPassword, blockedByRole, router, pathname]);

  if (isLoading || !isAuthenticated || blockedByPassword || blockedByRole) {
    return <FullPageSpinner label="Checking your access" />;
  }

  return <>{children}</>;
}