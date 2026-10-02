'use client';

import { Suspense, useEffect } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/lib/api-client';
import { fieldErrors, describeProblem } from '@/lib/problem-details';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { TextField } from '@/components/ui/Form';
import { Button } from '@/components/ui/Button';
import { Alert } from '@/components/ui/Alert';
import { login } from '@/features/auth/api';
import { prefersAdminExperience, useSession } from '@/features/auth/session';

/** Advisory client-side checks only; the server is authoritative (docs/07_UI_SPEC.md section 1). */
const schema = z.object({
  username: z.string().min(1, 'Enter your username or email.'),
  password: z.string().min(1, 'Enter your password.')
});

type FormValues = z.infer<typeof schema>;

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { isAuthenticated, isLoading, isAdminExperience, mustChangePassword } = useSession();

  const nextParam = searchParams.get('next');

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors }
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { username: '', password: '' } });

  useEffect(() => {
    if (isLoading || !isAuthenticated) return;
    if (mustChangePassword) {
      router.replace('/change-password');
      return;
    }
    // Only preserve same-origin, safe (GET) destinations (docs/07_UI_SPEC.md section 10).
    if (nextParam && nextParam.startsWith('/') && !nextParam.startsWith('//')) {
      router.replace(nextParam);
      return;
    }
    router.replace(isAdminExperience ? '/admin' : '/app');
  }, [isLoading, isAuthenticated, mustChangePassword, nextParam, isAdminExperience, router]);

  const mutation = useMutation({
    mutationFn: login,
    onSuccess: async (session) => {
      queryClient.setQueryData(['session'], session);
      await queryClient.invalidateQueries({ queryKey: ['session'] });
      const target =
        nextParam && nextParam.startsWith('/') && !nextParam.startsWith('//')
          ? nextParam
          : prefersAdminExperience(session.permissions)
            ? '/admin'
            : '/app';
      router.replace(session.user.must_change_password ? '/change-password' : target);
    },
    onError: (error) => {
      const problem = error instanceof ApiError ? error.problem : null;
      for (const [field, message] of Object.entries(fieldErrors(problem))) {
        if (field === 'username' || field === 'password') setError(field, { message });
      }
    }
  });

  const problem = mutation.error instanceof ApiError ? mutation.error : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle as="h1">Sign in to Workforce CRM</CardTitle>
      </CardHeader>
      <CardBody>
        {problem ? (
          <div className="mb-4">
            <Alert
              tone={problem.code === 'RATE_LIMITED' ? 'warning' : 'danger'}
              title={describeProblem(problem.problem).title}
              nextStep={describeProblem(problem.problem).nextStep}
              testId="login-error"
            >
              {problem.problem.detail ? <p>{problem.problem.detail}</p> : null}
            </Alert>
          </div>
        ) : null}

        <form
          noValidate
          className="space-y-4"
          onSubmit={handleSubmit((values) => mutation.mutate(values))}
          data-testid="login-form"
        >
          <TextField
            label="Username or email"
            autoComplete="username"
            autoFocus
            required
            error={errors.username?.message}
            {...register('username')}
          />
          <TextField
            label="Password"
            type="password"
            autoComplete="current-password"
            required
            error={errors.password?.message}
            {...register('password')}
          />
          <Button type="submit" size="lg" className="w-full" loading={mutation.isPending} loadingLabel="Signing in">
            Sign in
          </Button>
        </form>

        <p className="mt-4 text-xs text-content-muted">
          There is no public sign-up. Accounts are created by an administrator.
        </p>
      </CardBody>
    </Card>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="h-64" />}>
      <LoginForm />
    </Suspense>
  );
}