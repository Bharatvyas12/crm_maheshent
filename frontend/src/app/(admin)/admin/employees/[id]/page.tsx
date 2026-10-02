'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import {
  useCompensation,
  useCreateCompensation,
  useDeactivateEmployee,
  useEmployee,
  useReactivateEmployee,
  useResetPassword,
  useSetUserRoles,
  useUpdateEmployee,
  useUpdateEmployeeSensitive
} from '@/features/employees/hooks';
import { useRoles } from '@/features/rbac/hooks';
import { formatBusinessDate, formatDateTime, formatMoney, humanize } from '@/lib/format';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { TextField, TextAreaField, SelectField } from '@/components/ui/Form';
import { StatusPill } from '@/components/ui/StatusPill';
import { SkeletonList } from '@/components/ui/Skeleton';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { PermissionGate } from '@/components/PermissionGate';

export default function AdminEmployeeDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? '';

  const employee = useEmployee(id);
  const compensation = useCompensation(id, true);
  const compList = compensation.data?.items ?? [];
  const roles = useRoles({ include_system: true, page: 1 });

  const updateEmployee = useUpdateEmployee();
  const updateSensitive = useUpdateEmployeeSensitive();
  const createCompensation = useCreateCompensation();
  const setRoles = useSetUserRoles();
  const deactivate = useDeactivateEmployee();
  const reactivate = useReactivateEmployee();
  const resetPassword = useResetPassword();

  const [profile, setProfile] = useState<Record<string, string>>({});
  const [sensitive, setSensitive] = useState({ bank_account_name: '', bank_account_ifsc: '', bank_account_number: '' });
  const [sensitiveReason, setSensitiveReason] = useState('');
  const [roleCodes, setRoleCodes] = useState('');
  const [roleReason, setRoleReason] = useState('');
  const [deactivateOpen, setDeactivateOpen] = useState(false);
  const [exitDate, setExitDate] = useState('');
  const [deactivateReason, setDeactivateReason] = useState('');
  const [compensationOpen, setCompensationOpen] = useState(false);
  const [comp, setComp] = useState({ compensation_type: 'MONTHLY', rate: '', currency: 'INR', effective_from: '', reason: '' });

  useEffect(() => {
    if (!employee.data) return;
    setProfile({
      full_name: employee.data.full_name ?? '',
      phone: employee.data.phone ?? '',
      email: employee.data.email ?? '',
      department: employee.data.department ?? '',
      designation: employee.data.designation ?? '',
      address_line: employee.data.address_line ?? '',
      emergency_contact_name: employee.data.emergency_contact_name ?? '',
      emergency_contact_phone: employee.data.emergency_contact_phone ?? ''
    });
  }, [employee.data]);

  if (employee.isLoading) return <SkeletonList rows={5} />;
  if (employee.error) return <ProblemAlert error={employee.error} onRetry={() => void employee.refetch()} />;
  if (!employee.data) return null;

  const data = employee.data;

  return (
    <div className="space-y-4">
      <Link href="/admin/employees" className="inline-block text-sm text-primary underline">
        Back to employees
      </Link>

      <PageHeader
        title={data.full_name}
        description={`${data.employee_code} - ${data.designation ?? 'no designation'} - joined ${formatBusinessDate(data.date_of_joining)}`}
        actions={
          <>
            <StatusPill value={data.employment_status} />
            <PermissionGate anyOf={['employee.deactivate']}>
              {data.employment_status === 'ACTIVE' ? (
                <Button variant="danger" onClick={() => setDeactivateOpen(true)}>
                  Deactivate
                </Button>
              ) : (
                <Button variant="secondary" onClick={() => reactivate.mutate({ id, reason: 'Reactivated by admin' })}>
                  Reactivate
                </Button>
              )}
            </PermissionGate>
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle as="h2">Profile and employment</CardTitle>
          </CardHeader>
          <CardBody className="space-y-3">
            {updateEmployee.error ? <ProblemAlert error={updateEmployee.error} /> : null}
            <div className="grid gap-3 sm:grid-cols-2">
              <TextField label="Full name" name="full_name" value={profile.full_name ?? ''} onChange={(e) => setProfile({ ...profile, full_name: e.target.value })} />
              <TextField label="Phone" name="phone" value={profile.phone ?? ''} onChange={(e) => setProfile({ ...profile, phone: e.target.value })} />
              <TextField label="Email" name="email" value={profile.email ?? ''} onChange={(e) => setProfile({ ...profile, email: e.target.value })} />
              <TextField label="Department" name="department" value={profile.department ?? ''} onChange={(e) => setProfile({ ...profile, department: e.target.value })} />
              <TextField label="Designation" name="designation" value={profile.designation ?? ''} onChange={(e) => setProfile({ ...profile, designation: e.target.value })} />
              <TextField label="Address" name="address_line" value={profile.address_line ?? ''} onChange={(e) => setProfile({ ...profile, address_line: e.target.value })} />
              <TextField
                label="Emergency contact name"
                name="emergency_contact_name"
                value={profile.emergency_contact_name ?? ''}
                onChange={(e) => setProfile({ ...profile, emergency_contact_name: e.target.value })}
              />
              <TextField
                label="Emergency contact phone"
                name="emergency_contact_phone"
                value={profile.emergency_contact_phone ?? ''}
                onChange={(e) => setProfile({ ...profile, emergency_contact_phone: e.target.value })}
              />
            </div>
            <PermissionGate anyOf={['employee.update']}>
              <Button loading={updateEmployee.isPending} onClick={() => updateEmployee.mutate({ id, body: profile })}>
                Save profile
              </Button>
            </PermissionGate>
          </CardBody>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle as="h2">Roles</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3">
              {setRoles.error ? <ProblemAlert error={setRoles.error} /> : null}
              <p className="text-xs text-content-muted">
                Available roles: {(roles.data?.items ?? []).map((role) => role.code).join(', ') || 'none'}
              </p>
              <TextField
                label="Role codes (comma separated)"
                name="role_codes"
                value={roleCodes}
                onChange={(e) => setRoleCodes(e.target.value)}
                help="Privilege-escalation guards are enforced server-side."
              />
              <TextField label="Reason" name="role_reason" value={roleReason} onChange={(e) => setRoleReason(e.target.value)} />
              <PermissionGate anyOf={['employee.manage.roles']}>
                <Button
                  variant="secondary"
                  loading={setRoles.isPending}
                  disabled={!roleCodes.trim() || roleReason.trim().length === 0}
                  onClick={() =>
                    setRoles.mutate({
                      id: data.user_id,
                      body: { role_codes: roleCodes.split(',').map((code) => code.trim()).filter(Boolean), reason: roleReason }
                    })
                  }
                >
                  Update roles
                </Button>
              </PermissionGate>
              <PermissionGate anyOf={['employee.manage.credentials']}>
                <Button
                  variant="secondary"
                  loading={resetPassword.isPending}
                  onClick={() => resetPassword.mutate({ user_id: data.user_id, reason: 'Admin-initiated reset' })}
                >
                  Issue password reset token
                </Button>
              </PermissionGate>
            </CardBody>
          </Card>

          <PermissionGate anyOf={['employee.read.sensitive']}>
            <Card>
              <CardHeader>
                <CardTitle as="h2">Sensitive details</CardTitle>
              </CardHeader>
              <CardBody className="space-y-3">
                {updateSensitive.error ? <ProblemAlert error={updateSensitive.error} /> : null}
                <dl className="text-sm">
                  <dt className="text-xs text-content-muted">Bank account name</dt>
                  <dd>{data.sensitive?.bank_account_name ?? 'not on file'}</dd>
                  <dt className="mt-2 text-xs text-content-muted">Bank account number</dt>
                  <dd>{data.sensitive?.bank_account_number_masked ?? 'not on file'}</dd>
                  <dt className="mt-2 text-xs text-content-muted">IFSC</dt>
                  <dd>{data.sensitive?.bank_ifsc ?? 'not on file'}</dd>
                </dl>
                <PermissionGate anyOf={['employee.update.sensitive']}>
                  <div className="grid gap-3">
                    <TextField label="Bank account name" name="bank_account_name" value={sensitive.bank_account_name} onChange={(e) => setSensitive({ ...sensitive, bank_account_name: e.target.value })} />
                    <TextField label="Bank account number" name="bank_account_number" value={sensitive.bank_account_number} onChange={(e) => setSensitive({ ...sensitive, bank_account_number: e.target.value })} />
                    <TextField label="IFSC" name="bank_ifsc" value={sensitive.bank_account_ifsc} onChange={(e) => setSensitive({ ...sensitive, bank_account_ifsc: e.target.value })} />
                    <TextField label="Reason (required)" name="sensitive_reason" value={sensitiveReason} onChange={(e) => setSensitiveReason(e.target.value)} />
                    <Button
                      variant="secondary"
                      loading={updateSensitive.isPending}
                      disabled={sensitiveReason.trim().length === 0}
                      onClick={() =>
                        updateSensitive.mutate({
                          id,
                          body: {
                            bank_account_name: sensitive.bank_account_name || undefined,
                            bank_account_number: sensitive.bank_account_number || undefined,
                            bank_ifsc: sensitive.bank_account_ifsc || undefined,
                            reason: sensitiveReason
                          }
                        })
                      }
                    >
                      Save sensitive details
                    </Button>
                  </div>
                </PermissionGate>
              </CardBody>
            </Card>
          </PermissionGate>
        </div>
      </div>

      <PermissionGate anyOf={['employee.read.sensitive']}>
        <Card>
          <CardHeader
            action={
              <PermissionGate anyOf={['employee.update.sensitive']}>
                <Button variant="secondary" onClick={() => setCompensationOpen(true)}>
                  Add compensation
                </Button>
              </PermissionGate>
            }
          >
            <CardTitle as="h2">Compensation history</CardTitle>
          </CardHeader>
          <CardBody>
            {compensation.isLoading ? (
              <SkeletonList rows={2} />
            ) : compensation.error ? (
              <ProblemAlert error={compensation.error} onRetry={() => void compensation.refetch()} />
            ) : compList.length === 0 ? (
              <p className="text-sm text-content-muted">No compensation records. Payroll cannot compute this employee without one.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {compList.map((row) => (
                  <li key={row.id} className="flex items-center justify-between gap-3 border-b border-surface-border/60 pb-2 last:border-0">
                    <span>
                      <span className="font-medium">{formatMoney(row.rate, row.currency)}</span>
                      <span className="ml-2 text-xs text-content-muted">{humanize(row.compensation_type)}</span>
                    </span>
                    <span className="text-xs text-content-muted">
                      {formatBusinessDate(row.effective_from)} - {row.effective_to ? formatBusinessDate(row.effective_to) : 'open'}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </PermissionGate>

      <Dialog
        open={deactivateOpen}
        onClose={() => setDeactivateOpen(false)}
        title="Deactivate employee"
        description="Sessions are revoked. Attendance, orders, ledger and audit history are preserved."
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeactivateOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={deactivate.isPending}
              disabled={!exitDate || deactivateReason.trim().length === 0}
              onClick={() =>
                deactivate.mutate(
                  { id, body: { date_of_exit: exitDate, reason: deactivateReason, revoke_sessions: true } },
                  {
                    onSuccess: () => {
                      setDeactivateOpen(false);
                      setExitDate('');
                      setDeactivateReason('');
                    }
                  }
                )
              }
            >
              Deactivate
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {deactivate.error ? <ProblemAlert error={deactivate.error} testId="deactivate-error" /> : null}
          <TextField label="Date of exit" type="date" name="date_of_exit" required value={exitDate} onChange={(e) => setExitDate(e.target.value)} />
          <TextAreaField label="Reason" name="reason" required value={deactivateReason} onChange={(e) => setDeactivateReason(e.target.value)} />
          <p className="text-xs text-content-muted">
            If the employee holds an active order or open task, the server rejects this unless the force option is used by
            a caller holding the reassignment permissions.
          </p>
        </div>
      </Dialog>

      <Dialog
        open={compensationOpen}
        onClose={() => setCompensationOpen(false)}
        title="Add compensation"
        footer={
          <>
            <Button variant="secondary" onClick={() => setCompensationOpen(false)}>
              Cancel
            </Button>
            <Button
              loading={createCompensation.isPending}
              disabled={!comp.rate || !comp.effective_from || !comp.reason}
              onClick={() =>
                createCompensation.mutate(
                  {
                    id,
                    body: {
                      compensation_type: comp.compensation_type,
                      rate: comp.rate,
                      currency: comp.currency,
                      effective_from: comp.effective_from,
                      reason: comp.reason
                    }
                  },
                  {
                    onSuccess: () => {
                      setCompensationOpen(false);
                      setComp({ compensation_type: 'MONTHLY', rate: '', currency: 'INR', effective_from: '', reason: '' });
                    }
                  }
                )
              }
            >
              Save
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {createCompensation.error ? <ProblemAlert error={createCompensation.error} /> : null}
          <SelectField
            label="Compensation type"
            name="compensation_type"
            value={comp.compensation_type}
            onChange={(e) => setComp({ ...comp, compensation_type: e.target.value })}
            options={['MONTHLY', 'DAILY', 'HOURLY'].map((value) => ({ value, label: humanize(value) }))}
          />
          <TextField label="Rate" name="rate" required help="Decimal string, e.g. 25000.00" value={comp.rate} onChange={(e) => setComp({ ...comp, rate: e.target.value })} />
          <TextField label="Currency" name="currency" value={comp.currency} onChange={(e) => setComp({ ...comp, currency: e.target.value })} />
          <TextField label="Effective from" type="date" name="effective_from" required value={comp.effective_from} onChange={(e) => setComp({ ...comp, effective_from: e.target.value })} />
          <TextField label="Reason" name="reason" required value={comp.reason} onChange={(e) => setComp({ ...comp, reason: e.target.value })} />
        </div>
      </Dialog>

      <p className="text-xs text-content-muted">Last updated {formatDateTime(data.updated_at)}</p>
    </div>
  );
}