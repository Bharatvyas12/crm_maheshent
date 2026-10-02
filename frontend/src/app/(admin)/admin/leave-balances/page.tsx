'use client';

import { useState } from 'react';
import { useAdjustLeaveBalance, useLeaveBalances, useLeaveTypes } from '@/features/leaves/hooks';
import { useEmployees } from '@/features/employees/hooks';
import { Card, CardBody } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { TextField, TextAreaField, SelectField } from '@/components/ui/Form';
import { DataTable, type Column } from '@/components/ui/DataTable';
import { Pagination } from '@/components/ui/Pagination';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { PermissionGate } from '@/components/PermissionGate';
import type { LeaveBalance } from '@/lib/types';

export default function AdminLeaveBalancesPage() {
  const currentYear = new Date().getUTCFullYear();
  const [year, setYear] = useState(currentYear);
  const [employeeId, setEmployeeId] = useState('');
  const [leaveTypeId, setLeaveTypeId] = useState('');
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);

  const employees = useEmployees({ page: 1, page_size: 100 });
  const types = useLeaveTypes(true);
  const query = useLeaveBalances({
    period_year: year,
    employee_id: employeeId || undefined,
    leave_type_id: leaveTypeId || undefined,
    page
  });
  const adjust = useAdjustLeaveBalance();

  const [form, setForm] = useState({ employee_id: '', leave_type_id: '', days: '', reason: '' });

  const columns: Array<Column<LeaveBalance>> = [
    { key: 'employee', header: 'Employee', render: (row) => row.leave_type ? (row.employee_id ? row.employee_id.slice(0, 8) : '-') : row.employee_id.slice(0, 8) },
    { key: 'leave_type', header: 'Type', render: (row) => row.leave_type?.name ?? '-' },
    { key: 'entitled', header: 'Entitled', align: 'right', render: (row) => row.entitled_days },
    { key: 'accrued', header: 'Accrued', align: 'right', render: (row) => row.accrued_days },
    { key: 'used', header: 'Used', align: 'right', render: (row) => row.used_days },
    { key: 'pending', header: 'Pending', align: 'right', render: (row) => row.pending_days },
    { key: 'carried', header: 'Carried fwd', align: 'right', render: (row) => row.carried_forward_days },
    { key: 'adjustment', header: 'Adjustments', align: 'right', render: (row) => row.adjustment_days },
    { key: 'available', header: 'Available', align: 'right', render: (row) => <span className="font-semibold">{row.available_days}</span> }
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Leave balances"
        description="Every change is a dated movement so the balance always explains itself."
        actions={
          <PermissionGate anyOf={['leave.balance.manage']}>
            <Button onClick={() => setOpen(true)}>Adjust balance</Button>
          </PermissionGate>
        }
      />

      <Card>
        <CardBody className="grid gap-3 md:grid-cols-4">
          <TextField label="Year" type="number" name="period_year" value={String(year)} onChange={(e) => setYear(Number(e.target.value) || currentYear)} />
          <SelectField
            label="Employee"
            name="employee_id"
            placeholder="All"
            value={employeeId}
            onChange={(e) => {
              setEmployeeId(e.target.value);
              setPage(1);
            }}
            options={(employees.data?.items ?? []).map((employee) => ({ value: employee.id, label: `${employee.full_name} (${employee.employee_code})` }))}
          />
          <SelectField
            label="Leave type"
            name="leave_type_id"
            placeholder="All"
            value={leaveTypeId}
            onChange={(e) => {
              setLeaveTypeId(e.target.value);
              setPage(1);
            }}
            options={(types.data?.items ?? []).map((type) => ({ value: type.id, label: type.name }))}
          />
          <div className="flex items-end">
            <Button variant="secondary" onClick={() => void query.refetch()}>
              Refresh
            </Button>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardBody>
          <DataTable
            columns={columns}
            rows={query.data?.items ?? []}
            getRowId={(row) => row.id}
            loading={query.isLoading}
            error={query.error ? <ProblemAlert error={query.error} onRetry={() => void query.refetch()} /> : undefined}
            emptyTitle="No balances"
            emptyHint="Balances are created when leave types are configured or leave is applied."
            caption="Leave balances"
            testId="leave-balances-table"
          />
          {query.data ? (
            <Pagination
              page={query.data.page}
              pageSize={query.data.page_size}
              totalItems={query.data.total_items}
              totalPages={query.data.total_pages}
              onPageChange={setPage}
            />
          ) : null}
        </CardBody>
      </Card>

      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Adjust leave balance"
        description="A signed day count is posted as an ADJUSTMENT movement with your reason."
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              loading={adjust.isPending}
              disabled={!form.employee_id || !form.leave_type_id || !form.days || !form.reason}
              onClick={() =>
                adjust.mutate(
                  { employee_id: form.employee_id, leave_type_id: form.leave_type_id, period_year: year, days: form.days, reason: form.reason },
                  {
                    onSuccess: () => {
                      setOpen(false);
                      setForm({ employee_id: '', leave_type_id: '', days: '', reason: '' });
                    }
                  }
                )
              }
            >
              Post adjustment
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {adjust.error ? <ProblemAlert error={adjust.error} /> : null}
          <SelectField
            label="Employee"
            name="employee_id"
            required
            placeholder="Select"
            value={form.employee_id}
            onChange={(e) => setForm({ ...form, employee_id: e.target.value })}
            options={(employees.data?.items ?? []).map((employee) => ({ value: employee.id, label: `${employee.full_name} (${employee.employee_code})` }))}
          />
          <SelectField
            label="Leave type"
            name="leave_type_id"
            required
            placeholder="Select"
            value={form.leave_type_id}
            onChange={(e) => setForm({ ...form, leave_type_id: e.target.value })}
            options={(types.data?.items ?? []).map((type) => ({ value: type.id, label: type.name }))}
          />
          <TextField label="Days (signed, e.g. -1.5)" name="days" required value={form.days} onChange={(e) => setForm({ ...form, days: e.target.value })} />
          <TextAreaField label="Reason" name="reason" required value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
        </div>
      </Dialog>
    </div>
  );
}