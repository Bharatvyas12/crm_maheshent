'use client';

import { useState } from 'react';
import { PermissionGate } from '@/components/PermissionGate';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Alert } from '@/components/ui/Alert';
import { Switch } from '@/components/ui/Form';
import { TextAreaField, TextField } from '@/components/ui/Form';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { SkeletonList } from '@/components/ui/Skeleton';
import { useBroadcastNotification, useNotificationPreferences, useUpdateNotificationPreferences } from '@/features/notifications/hooks';
import { useEmployees } from '@/features/employees/hooks';
import { humanize } from '@/lib/format';

const SCOPES = ['ALL_ACTIVE_EMPLOYEES', 'ROLE', 'SPECIFIC_EMPLOYEES'] as const;

export default function AdminNotificationsPage() {
  const broadcast = useBroadcastNotification();
  const preferences = useNotificationPreferences();
  const updatePreferences = useUpdateNotificationPreferences();
  const employees = useEmployees({ status: 'ACTIVE', page_size: 100 });

  const [form, setForm] = useState({ title: '', body: '', scope: 'ALL_ACTIVE_EMPLOYEES', priority: 'NORMAL' });
  const [employeeIds, setEmployeeIds] = useState<string[]>([]);

  const invalid = !form.title.trim() || !form.body.trim() || (form.scope === 'SPECIFIC_EMPLOYEES' && employeeIds.length === 0);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Notifications"
        description="Broadcast an announcement to a server-validated audience and manage your own delivery preferences."
      />

      <PermissionGate anyOf={['notification.manage']} fallback={<Alert tone="warning" title="You cannot broadcast notifications." />}>
        <Card>
          <CardHeader>
            <CardTitle as="h2">Broadcast</CardTitle>
          </CardHeader>
          <CardBody className="space-y-3">
            {broadcast.error ? <ProblemAlert error={broadcast.error} /> : null}
            {broadcast.isSuccess ? <Alert tone="success" title="Broadcast sent" /> : null}
            <TextField label="Title" name="title" required value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} />
            <TextAreaField label="Body" name="body" required value={form.body} onChange={(event) => setForm({ ...form, body: event.target.value })} />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <label htmlFor="audience-scope" className="block text-sm font-medium">Audience</label>
                <select
                  id="audience-scope"
                  className="h-11 w-full rounded-md border border-surface-border bg-surface px-3 text-base"
                  value={form.scope}
                  onChange={(event) => setForm({ ...form, scope: event.target.value })}
                >
                  {SCOPES.map((scope) => (
                    <option key={scope} value={scope}>{humanize(scope)}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <label htmlFor="priority" className="block text-sm font-medium">Priority</label>
                <select
                  id="priority"
                  className="h-11 w-full rounded-md border border-surface-border bg-surface px-3 text-base"
                  value={form.priority}
                  onChange={(event) => setForm({ ...form, priority: event.target.value })}
                >
                  {['LOW', 'NORMAL', 'HIGH', 'URGENT'].map((priority) => (
                    <option key={priority} value={priority}>{humanize(priority)}</option>
                  ))}
                </select>
              </div>
            </div>
            {form.scope === 'SPECIFIC_EMPLOYEES' ? (
              <fieldset className="max-h-56 space-y-1 overflow-y-auto rounded-md border border-surface-border p-3">
                <legend className="px-1 text-sm font-medium">Employees</legend>
                {(employees.data?.items ?? []).map((employee) => (
                  <label key={employee.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-surface-border"
                      checked={employeeIds.includes(employee.id)}
                      onChange={() =>
                        setEmployeeIds((current) =>
                          current.includes(employee.id) ? current.filter((id) => id !== employee.id) : [...current, employee.id]
                        )
                      }
                    />
                    {employee.full_name}
                  </label>
                ))}
              </fieldset>
            ) : null}
            <Button
              loading={broadcast.isPending}
              disabled={invalid || broadcast.isPending}
              onClick={() =>
                broadcast.mutate(
                  {
                    title: form.title.trim(),
                    body: form.body.trim(),
                    priority: form.priority,
                    audience: {
                      scope: form.scope,
                      employee_ids: form.scope === 'SPECIFIC_EMPLOYEES' ? employeeIds : undefined
                    }
                  },
                  { onSuccess: () => { setForm({ ...form, title: '', body: '' }); setEmployeeIds([]); } }
                )
              }
            >
              Send broadcast
            </Button>
          </CardBody>
        </Card>
      </PermissionGate>

      <Card>
        <CardHeader>
          <CardTitle as="h2">My delivery preferences</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          {preferences.isLoading ? (
            <SkeletonList rows={3} />
          ) : preferences.error ? (
            <ProblemAlert error={preferences.error} onRetry={() => void preferences.refetch()} />
          ) : (preferences.data?.items.length ?? 0) === 0 ? (
            <p className="text-sm text-content-muted">No per-channel preferences are exposed for your account.</p>
          ) : (
            <ul className="space-y-2">
              {preferences.data?.items.map((preference) => (
                <li key={`${preference.event_type}-${preference.channel}`} className="rounded-md border border-surface-border p-2">
                  <Switch
                    label={`${humanize(preference.event_type)} - ${humanize(preference.channel)}`}
                    checked={preference.is_enabled}
                    disabled={!preference.can_disable}
                    onChange={(next) =>
                      updatePreferences.mutate([{ event_type: preference.event_type, channel: preference.channel, is_enabled: next }])
                    }
                  />
                  {!preference.can_disable ? (
                    <p className="mt-1 text-xs text-content-muted">Security notifications cannot be disabled.</p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <Alert tone="info" title="Per-channel delivery status is not exposed by the API contract.">
        The documented surface returns the number of created notifications. Delivery receipts per channel are
        not part of docs/03_API_CONTRACT.md section 13, so this screen does not fabricate them.
      </Alert>
    </div>
  );
}