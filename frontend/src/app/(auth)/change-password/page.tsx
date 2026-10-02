'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/lib/api-client';
import { fieldErrors, describeProblem } from '@/lib/problem-details';
import { useSession } from '@/features/auth/session';
import { changePassword } from '@/features/auth/api';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { TextField } from '@/components/ui/Form';
import { Button } from '@/components/ui/Button';
import { Alert } from '@/components/ui/Alert';
import { FullPageSpinner } from '@/components/layout/AuthGuard';

const schema = z
  .object({
    current_password: z.string().min(1, 'Enter your current password.'),
    new_password: z.string().min(1, 'Enter a new password.'),
    confirm_password: z.string().min(1, 'Re-enter the new password.')
  })
  .refine((values) => values.new_password === values.confirm_password, {
    path: ['confirm_password'],
    message: 'The two passwords do not match.'
  });

type FormValues = z.infer<typeof schema>;

export default function ChangePasswordPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { isLoading, isAuthenticated, mustChangePassword, isAdminExperience } = useSession();
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) router.replace('/login?next=%2Fchange-password');
  }, [isLoading, isAuthenticated, router]);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors }
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { current_password: '', new_password: '', confirm_password: '' }
  });

  const mutation = useMutation({
    mutationFn: (values: FormValues) => changePassword({ current_password: values.current_password, new_password: values.new_password }),
    onSuccess: async () => {
      setDone(true);
      await queryClient.invalidateQueries({ queryKey: ['session'] });
      window.setTimeout(() => router.replace(isAdminExperience ? '/admin' : '/app'), 1200);
    },
    onError: (error) => {
      const problem = error instanceof ApiError ? error.problem : null;
      for (const [field, message] of Object.entries(fieldErrors(problem))) {
        if (field === 'current_password' || field === 'new_password') setError(field, { message });
      }
    }
  });

  if (isLoading || !isAuthenticated) return <FullPageSpinner label="Checking your session" />;

  const problem = mutation.error instanceof ApiError ? mutation.error : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle as="h1">Change your password</CardTitle>
      </CardHeader>
      <CardBody>
        {mustChangePassword ? (
          <div className="mb-4">
            <Alert tone="warning" title="You must set a new password before continuing." />
          </div>
        ) : null}

        {done ? (
          <Alert tone="success" title="Password updated." nextStep="Redirecting to your dashboard." testId="change-password-success" />
        ) : (
          <form noValidate className="space-y-4" onSubmit={handleSubmit((values) => mutation.mutate(values))}>
            {problem ? (
              <Alert tone="danger" title={describeProblem(problem.problem).title} nextStep={describeProblem(problem.problem).nextStep}>
                {problem.problem.detail ? <p>{problem.problem.detail}</p> : null}
              </Alert>
            ) : null}
            <TextField
              label="Current password"
              type="password"
              autoComplete="current-password"
              required
              error={errors.current_password?.message}
              {...register('current_password')}
            />
            <TextField
              label="New password"
              type="password"
              autoComplete="new-password"
              required
              error={errors.new_password?.message}
              help="The server enforces the password policy; this form only checks that a value is present."
              {...register('new_password')}
            />
            <TextField
              label="Confirm new password"
              type="password"
              autoComplete="new-password"
              required
              error={errors.confirm_password?.message}
              {...register('confirm_password')}
            />
            <Button type="submit" size="lg" className="w-full" loading={mutation.isPending}>
              Update password
            </Button>
          </form>
        )}
      </CardBody>
    </Card>
  );
}