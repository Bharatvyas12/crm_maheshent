'use client';

import { useState, type ReactNode } from 'react';
import { QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiError } from '@/lib/api-client';
import { SessionProvider } from '@/features/auth/session';
import { ToastProvider } from '@/components/ui/Toast';

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 15_000,
            gcTime: 5 * 60_000,
            refetchOnWindowFocus: false,
            retry: (failureCount, error) => {
              // Never retry authorization/validation failures; retry transient conditions once.
              if (error instanceof ApiError) {
                if (error.status === 0) return failureCount < 2;
                if ([401, 403, 404, 422, 409, 423].includes(error.status)) return false;
                return failureCount < 1;
              }
              return failureCount < 1;
            }
          },
          mutations: {
            retry: false
          }
        },
        queryCache: new QueryCache({
          onError: (error) => {
            if (error instanceof ApiError && error.isUnauthenticated) {
              // Session revoked/expired server-side; the SessionProvider refetch will redirect.
              void queryClient.invalidateQueries({ queryKey: ['session'] });
            }
          }
        })
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <ToastProvider>{children}</ToastProvider>
      </SessionProvider>
    </QueryClientProvider>
  );
}