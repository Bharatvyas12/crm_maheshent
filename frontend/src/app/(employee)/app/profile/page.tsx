'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/lib/api-client';
import { describeProblem } from '@/lib/problem-details';
import { formatDateTime } from '@/lib/format';
import { fetchMyProfile, fetchMySessions, revokeSession, updateMyProfile, type SelfServiceProfileFields } from '@/features/auth/api';
import { useSession } from '@/features/auth/session';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { TextField } from '@/components/ui/Form';
import { Alert } from '@/components/ui/Alert';
import { SkeletonList } from '@/components/ui/Skeleton';
import { ProblemAlert } from '@/components/ui/ProblemAlert';

export default function EmployeeProfilePage() {
  const { user, employee, permissions } = useSession();
  const queryClient = useQueryClient();

  const profile = useQuery({ queryKey: ['me', 'profile'], queryFn: fetchMyProfile });
  const sessions = useQuery({ queryKey: ['me', 'sessions'], queryFn: fetchMySessions });

  const [form, setForm] = useState<Partial<SelfServiceProfileFields>>({});

  useEffect(() => {
    if (profile.data?.employee) {
      setForm({
        phone: profile.data.employee.phone ?? '',
        email: profile.data.employee.email ?? '',
        address_line: profile.data.employee.address_line ?? '',
        emergency_contact_name: profile.data.employee.emergency_contact_name ?? '',
        emergency_contact_phone: profile.data.employee.emergency_contact_phone ?? ''
      });
    }
  }, [profile.data]);

  const save = useMutation({
    mutationFn: (values: Partial<SelfServiceProfileFields>) => updateMyProfile(values),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['me', 'profile'] });
      await queryClient.invalidateQueries({ queryKey: ['session'] });
    }
  });

  const revoke = useMutation({
    mutationFn: revokeSession,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['me', 'sessions'] })
  });

  const canEdit = permissions.includes('profile.update.self');

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Profile</h1>
        <p className="text-sm text-content-muted">{employee?.full_name ?? user?.username}</p>
      </div>

      <Card>
        <CardHeader
          action={
            <Link href="/change-password" className="text-sm text-primary underline">
              Change password
            </Link>
          }
        >
          <CardTitle as="h2">My details</CardTitle>
        </CardHeader>
        <CardBody>
          {profile.isLoading ? (
            <SkeletonList rows={3} />
          ) : profile.error ? (
            <ProblemAlert error={profile.error} onRetry={() => void profile.refetch()} />
          ) : (
            <div className="space-y-3">
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <dt className="text-xs text-content-muted">Employee code</dt>
                  <dd>{profile.data?.employee?.employee_code ?? '-'}</dd>
                </div>
                <div>
                  <dt className="text-xs text-content-muted">Department</dt>
                  <dd>{profile.data?.employee?.department ?? '-'}</dd>
                </div>
                <div>
                  <dt className="text-xs text-content-muted">Designation</dt>
                  <dd>{profile.data?.employee?.designation ?? '-'}</dd>
                </div>
                <div>
                  <dt className="text-xs text-content-muted">Joined</dt>
                  <dd>{profile.data?.employee?.date_of_joining ?? '-'}</dd>
                </div>
              </dl>

              {!canEdit ? (
                <Alert tone="info" title="You cannot edit these details." nextStep="Ask the admin to update them." />
              ) : null}

              <form
                className="space-y-3"
                onSubmit={(event) => {
                  event.preventDefault();
                  save.mutate(form);
                }}
              >
                {save.error ? <ProblemAlert error={save.error} testId="profile-save-error" /> : null}
                {save.isSuccess ? <Alert tone="success" title="Profile updated" testId="profile-save-success" /> : null}
                <TextField label="Phone" name="phone" value={form.phone ?? ''} onChange={(e) => setForm({ ...form, phone: e.target.value })} disabled={!canEdit} />
                <TextField label="Email" type="email" name="email" value={form.email ?? ''} onChange={(e) => setForm({ ...form, email: e.target.value })} disabled={!canEdit} />
                <TextField
                  label="Address"
                  name="address_line"
                  value={form.address_line ?? ''}
                  onChange={(e) => setForm({ ...form, address_line: e.target.value })}
                  disabled={!canEdit}
                />
                <TextField
                  label="Emergency contact name"
                  name="emergency_contact_name"
                  value={form.emergency_contact_name ?? ''}
                  onChange={(e) => setForm({ ...form, emergency_contact_name: e.target.value })}
                  disabled={!canEdit}
                />
                <TextField
                  label="Emergency contact phone"
                  name="emergency_contact_phone"
                  value={form.emergency_contact_phone ?? ''}
                  onChange={(e) => setForm({ ...form, emergency_contact_phone: e.target.value })}
                  disabled={!canEdit}
                />
                <Button type="submit" size="lg" className="w-full" loading={save.isPending} disabled={!canEdit || save.isPending}>
                  Save changes
                </Button>
                <p className="text-xs text-content-muted">
                  Server-side validation is authoritative; these checks are only a convenience.
                </p>
              </form>
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle as="h2">Active sessions</CardTitle>
        </CardHeader>
        <CardBody>
          {sessions.isLoading ? (
            <SkeletonList rows={2} />
          ) : sessions.error ? (
            <ProblemAlert error={sessions.error} onRetry={() => void sessions.refetch()} />
          ) : (
            <ul className="space-y-2">
              {sessions.data?.items.map((session) => (
                <li key={session.id} className="flex items-start justify-between gap-3 border-b border-surface-border/60 pb-2 text-sm last:border-0">
                  <span className="min-w-0">
                    <span className="block truncate">{session.user_agent ?? 'Unknown device'}</span>
                    <span className="block text-xs text-content-muted">
                      {session.ip ?? 'unknown ip'} - last seen {formatDateTime(session.last_seen_at)}
                      {session.is_current ? ' - this device' : ''}
                    </span>
                  </span>
                  {!session.is_current && permissions.includes('auth.session.revoke.self') ? (
                    <Button variant="secondary" size="sm" loading={revoke.isPending} onClick={() => revoke.mutate(session.id)}>
                      Revoke
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </div>
  );
}