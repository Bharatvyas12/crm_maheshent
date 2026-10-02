'use client';

import { useMemo, useState } from 'react';
import { PermissionGate } from '@/components/PermissionGate';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Dialog } from '@/components/ui/Dialog';
import { EmptyState } from '@/components/ui/EmptyState';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { TextAreaField, TextField } from '@/components/ui/Form';
import { SkeletonList } from '@/components/ui/Skeleton';
import {
  useCreateRole,
  useDeleteRole,
  usePermissionCatalog,
  useRole,
  useRoles,
  useSetRolePermissions
} from '@/features/rbac/hooks';
import { useEmployees, useSetUserRoles } from '@/features/employees/hooks';
import { humanize } from '@/lib/format';
import { SENSITIVE_PERMISSIONS } from '@/lib/permissions';
import type { PermissionCatalogItem } from '@/lib/types';

export default function AdminRolesPage() {
  const roles = useRoles({ include_system: true });
  const permissions = usePermissionCatalog();
  const createRole = useCreateRole();
  const deleteRole = useDeleteRole();
  const setPermissions = useSetRolePermissions();
  const setUserRoles = useSetUserRoles();
  const employees = useEmployees({ status: 'ACTIVE', page_size: 100 });

  const [selectedRoleId, setSelectedRoleId] = useState('');
  const role = useRole(selectedRoleId);
  const [draft, setDraft] = useState<string[] | null>(null);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [newRole, setNewRole] = useState({ code: '', name: '', description: '' });
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignEmployee, setAssignEmployee] = useState('');
  const [assignRoleCodes, setAssignRoleCodes] = useState<string[]>([]);
  const [assignReason, setAssignReason] = useState('');

  const byModule = useMemo(() => {
    const map = new Map<string, PermissionCatalogItem[]>();
    const items = Array.isArray(permissions.data?.items) ? permissions.data.items : [];
    for (const permission of items) {
      const list = map.get(permission.module) ?? [];
      list.push(permission);
      map.set(permission.module, list);
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [permissions.data]);

  const currentCodes = draft ?? (role.data?.permissions ?? []).map((permission) => permission.code);
  const dirty = draft !== null;

  function toggle(code: string) {
    setDraft((current) => {
      const base = current ?? (role.data?.permissions ?? []).map((permission) => permission.code);
      return base.includes(code) ? base.filter((item) => item !== code) : [...base, code];
    });
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Roles and permissions"
        description="Permission changes are audited with before/after code lists and take effect on the next request."
        actions={
          <div className="flex flex-wrap gap-2">
            <PermissionGate anyOf={['employee.manage.roles']}>
              <Button variant="secondary" onClick={() => { setAssignOpen(true); setAssignEmployee(''); setAssignRoleCodes([]); setAssignReason(''); }}>
                Assign roles to a user
              </Button>
            </PermissionGate>
            <PermissionGate anyOf={['role.manage']}>
              <Button onClick={() => setCreateOpen(true)}>New role</Button>
            </PermissionGate>
          </div>
        }
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[20rem_1fr]">
        <Card>
          <CardHeader>
            <CardTitle as="h2">Roles</CardTitle>
          </CardHeader>
          <CardBody>
            {roles.isLoading ? (
              <SkeletonList rows={4} />
            ) : roles.error ? (
              <ProblemAlert error={roles.error} onRetry={() => void roles.refetch()} />
            ) : (roles.data?.items.length ?? 0) === 0 ? (
              <EmptyState title="No roles" hint="Create a role to group permissions." />
            ) : (
              <ul className="space-y-1">
                {roles.data?.items.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => { setSelectedRoleId(item.id); setDraft(null); setReason(''); }}
                      aria-current={selectedRoleId === item.id ? 'true' : undefined}
                      className={`flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm ${
                        selectedRoleId === item.id ? 'bg-primary-soft text-primary' : 'hover:bg-surface-muted'
                      }`}
                    >
                      <span className="min-w-0">
                        <span className="block font-medium">{item.name}</span>
                        <span className="block text-xs text-content-muted">{item.code}</span>
                      </span>
                      <span className="flex shrink-0 items-center gap-1">
                        {item.is_system ? <Badge tone="neutral">System</Badge> : null}
                        <span className="text-xs text-content-muted">{item.permission_count ?? 0}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            action={
              role.data ? (
                <div className="flex flex-wrap gap-2">
                  <PermissionGate anyOf={['role.manage']}>
                    <Button
                      size="sm"
                      loading={setPermissions.isPending}
                      disabled={!dirty || !reason.trim() || setPermissions.isPending}
                      onClick={() => {
                        setError(null);
                        setPermissions.mutate(
                          { id: role.data!.id, body: { permission_codes: currentCodes, reason: reason.trim() } },
                          { onSuccess: () => { setDraft(null); setReason(''); void role.refetch(); }, onError: setError }
                        );
                      }}
                    >
                      Save permissions
                    </Button>
                  </PermissionGate>
                  {!role.data.is_system ? (
                    <PermissionGate anyOf={['role.manage']}>
                      <Button variant="danger" size="sm" onClick={() => deleteRole.mutate(role.data!.id, { onSuccess: () => setSelectedRoleId('') })}>
                        Delete
                      </Button>
                    </PermissionGate>
                  ) : null}
                </div>
              ) : null
            }
          >
            <CardTitle as="h2">{role.data ? role.data.name : 'Permission matrix'}</CardTitle>
          </CardHeader>
          <CardBody className="space-y-4">
            {!selectedRoleId ? (
              <EmptyState title="Select a role" hint="Choose a role to review and edit its permissions." />
            ) : role.isLoading ? (
              <SkeletonList rows={5} />
            ) : role.error ? (
              <ProblemAlert error={role.error} onRetry={() => void role.refetch()} />
            ) : (
              <>
                {error ? <ProblemAlert error={error} /> : null}
                {setPermissions.error ? <ProblemAlert error={setPermissions.error} /> : null}
                <TextAreaField
                  label="Reason for this change (required)"
                  name="reason"
                  required
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  help="Recorded in the audit log with the before/after permission codes."
                />
                <div className="space-y-4">
                  {byModule.map(([module, codes]) => (
                    <fieldset key={module} className="rounded-md border border-surface-border p-3">
                      <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-content-muted">
                        {humanize(module)}
                      </legend>
                      <ul className="grid grid-cols-1 gap-1 sm:grid-cols-2">
                        {codes.map((permission) => (
                          <li key={permission.code}>
                            <label className="flex items-start gap-2 text-sm">
                              <input
                                type="checkbox"
                                className="mt-0.5 h-4 w-4 rounded border-surface-border"
                                checked={currentCodes.includes(permission.code)}
                                onChange={() => toggle(permission.code)}
                              />
                              <span>
                                <span className="font-medium">{permission.code}</span>
                                {SENSITIVE_PERMISSIONS.has(permission.code) ? <Badge tone="warning">Sensitive</Badge> : null}
                                <span className="block text-xs text-content-muted">{permission.description}</span>
                              </span>
                            </label>
                          </li>
                        ))}
                      </ul>
                    </fieldset>
                  ))}
                </div>
              </>
            )}
          </CardBody>
        </Card>
      </div>

      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Create a role"
        description="Unknown permission codes are rejected by the server."
        footer={
          <>
            <Button variant="secondary" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button
              loading={createRole.isPending}
              disabled={!newRole.code.trim() || !newRole.name.trim() || createRole.isPending}
              onClick={() =>
                createRole.mutate(
                  {
                    code: newRole.code.trim().toUpperCase(),
                    name: newRole.name.trim(),
                    description: newRole.description.trim() || undefined,
                    permission_codes: []
                  },
                  { onSuccess: () => { setCreateOpen(false); setNewRole({ code: '', name: '', description: '' }); void roles.refetch(); } }
                )
              }
            >
              Create
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {createRole.error ? <ProblemAlert error={createRole.error} /> : null}
          <TextField label="Code" name="code" required value={newRole.code} onChange={(event) => setNewRole({ ...newRole, code: event.target.value })} />
          <TextField label="Name" name="name" required value={newRole.name} onChange={(event) => setNewRole({ ...newRole, name: event.target.value })} />
          <TextAreaField label="Description (optional)" name="description" value={newRole.description} onChange={(event) => setNewRole({ ...newRole, description: event.target.value })} />
        </div>
      </Dialog>

      <Dialog
        open={assignOpen}
        onClose={() => setAssignOpen(false)}
        title="Assign roles to a user"
        description="The server blocks self-escalation and protects the last remaining admin."
        footer={
          <>
            <Button variant="secondary" onClick={() => setAssignOpen(false)}>Cancel</Button>
            <Button
              loading={setUserRoles.isPending}
              disabled={!assignEmployee || !assignReason.trim() || setUserRoles.isPending}
              onClick={() => {
                const employee = (employees.data?.items ?? []).find((item) => item.id === assignEmployee);
                const userId = employee?.user_id;
                if (!userId) return;
                setUserRoles.mutate(
                  { id: userId, body: { role_codes: assignRoleCodes, reason: assignReason.trim() } },
                  { onSuccess: () => setAssignOpen(false) }
                );
              }}
            >
              Assign
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {setUserRoles.error ? <ProblemAlert error={setUserRoles.error} /> : null}
          <label className="block text-sm font-medium" htmlFor="assign-employee">Employee</label>
          <select
            id="assign-employee"
            className="h-11 w-full rounded-md border border-surface-border bg-surface px-3 text-base"
            value={assignEmployee}
            onChange={(event) => setAssignEmployee(event.target.value)}
          >
            <option value="">Select an employee</option>
            {(employees.data?.items ?? []).map((employee) => (
              <option key={employee.id} value={employee.id}>
                {employee.full_name} ({employee.employee_code})
              </option>
            ))}
          </select>
          <fieldset className="space-y-1">
            <legend className="text-sm font-medium">Roles</legend>
            {(roles.data?.items ?? []).filter((item) => item.is_assignable).map((item) => (
              <label key={item.id} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-surface-border"
                  checked={assignRoleCodes.includes(item.code)}
                  onChange={() =>
                    setAssignRoleCodes((current) =>
                      current.includes(item.code) ? current.filter((code) => code !== item.code) : [...current, item.code]
                    )
                  }
                />
                {item.name}
              </label>
            ))}
          </fieldset>
          <TextAreaField label="Reason (required)" name="assign_reason" required value={assignReason} onChange={(event) => setAssignReason(event.target.value)} />
        </div>
      </Dialog>


    </div>
  );
}