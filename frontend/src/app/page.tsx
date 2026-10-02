'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useSession } from '@/features/auth/session';
import { Spinner } from '@/components/ui/Spinner';

/** Role-aware entry point: sends the user to the experience their permissions select. */
export default function RootPage() {
  const { isLoading, isAuthenticated, isAdminExperience, mustChangePassword } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) return;
    if (!isAuthenticated) {
      router.replace('/login');
      return;
    }
    if (mustChangePassword) {
      router.replace('/change-password');
      return;
    }
    router.replace(isAdminExperience ? '/admin' : '/app');
  }, [isLoading, isAuthenticated, isAdminExperience, mustChangePassword, router]);

  return (
    <main className="flex min-h-screen items-center justify-center">
      <Spinner className="text-primary" label="Preparing your workspace" />
    </main>
  );
}