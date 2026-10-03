'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ApiError } from '@/lib/api-client';
import { describeProblem } from '@/lib/problem-details';
import { formatBusinessDate, humanize } from '@/lib/format';
import { useCreateEmployee, useEmployees } from '@/features/employees/hooks';
import { Card, CardBody } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { DataTable, type Column } from '@/components/ui/DataTable';
import { Pagination } from '@/components/ui/Pagination';
import { StatusPill } from '@/components/ui/StatusPill';
import { Dialog } from '@/components/ui/Dialog';
import { TextField, SelectField } from '@/components/ui/Form';
import { Alert } from '@/components/ui/Alert';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import type { Employee } from '@/lib/types';

const EMPLOYMENT_TYPES = ['FULL_TIME', 'PART_TIME', 'CONTRACT', 'INTERN'];

export default function AdminEmployeesPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [department, setDepartment] = useState('');
  const [q, setQ] = useState('');
  const [applied, setApplied] = useState({ status: '', department: '', q: '' });
  const [sort, setSort] = useState('employee_code');
  const [open, setOpen] = useState(false);

  const query = useEmployees({ ...applied, sort, page });
  const create = useCreateEmployee();

  const [form, setForm] = useState({
    employee_code: '',
    full_name: '',
    phone: '',
    email: '',
    date_of_joining: '',
    employment_type: 'FULL_TIME',
    department: '',
    designation: '',
    address_line: '',
    emergency_contact_name: '',
    emergency_contact_phone: '',
    username: '',
    initial_password: '',
    role_codes: 'EMPLOYEE'
  });
  const [formError, setFormError] = useState<string | null>(null);

  const createError = create.error instanceof ApiError ? create.error : null;

  function submit() {
    setFormError(null);
    if (!form.employee_code.trim()) return setFormError('Employee code is required.');
    if (!form.full_name.trim()) return setFormError('Full name is required.');
    if (!form.date_of_joining) return setFormError('Date of joining is required.');
    if (!form.username.trim()) return setFormError('Username is required.');

    create.mutate(
      {
        employee_code: form.employee_code.trim(),
        full_name: form.full_name.trim(),
        phone: form.phone || undefined,
        email: form.email || undefined,
        date_of_joining: form.date_of_joining,
        employment_type: form.employment_type,
        department: form.department || undefined,
        designation: form.designation || undefined,
        address_line: form.address_line || undefined,
        emergency_contact_name: form.emergency_contact_name || undefined,
        emergency_contact_phone: form.emergency_contact_phone || undefined,
        username: form.username.trim(),
        initial_password: form.initial_password || undefined,
        roles: form.role_codes.split(',').map((code) => code.trim()).filter(Boolean)
      },
      {
        onSuccess: () => {
          setOpen(false);
          setForm({
            employee_code: '',
            full_name: '',
            phone: '',
            email: '',
            date_of_joining: '',
            employment_type: 'FULL_TIME',
            department: '',
            designation: '',
            address_line: '',
            emergency_contact_name: '',
            emergency_contact_phone: '',
            username: '',
            initial_password: '',
            role_codes: 'EMPLOYEE'
          });
        }
      }
    );
  }

  const columns: Array<Column<Employee>> = [
    {
      key: 'employee_code',
      header: 'Code',
      sortable: true,
      render: (row) => (
        <Link href={`/admin/employees/${row.id}`} className="font-medium text-primary underline">
          {row.employee_code}
        </Link>
      )
    },
    { key: 'full_name', header: 'Name', sortable: true, render: (row) => row.full_name },
    { key: 'department', header: 'Department', render: (row) => row.department ?? '-' },
    { key: 'designation', header: 'Designation', render: (row) => row.designation ?? '-' },
    { key: 'employment_type', header: 'Type', render: (row) => humanize(row.employment_type) },
    { key: 'employment_status', header: 'Status', sortable: true, render: (row) => <StatusPill value={row.employment_status} /> },
    { key: 'date_of_joining', header: 'Joined', sortable: true, render: (row) => formatBusinessDate(row.date_of_joining) },
    { key: 'phone', header: 'Phone', render: (row) => row.phone ?? '-' }
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Employees"
        description="Create, filter and open employee records. Deactivation never deletes history."
        actions={<Button onClick={() => setOpen(true)}>Add employee</Button>}
      />

      <Card>
        <CardBody className="grid gap-3 md:grid-cols-4">
          <SelectField
            label="Status"
            name="status"
            placeholder="Any"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            options={['ACTIVE', 'INACTIVE', 'EXITED'].map((value) => ({ value, label: humanize(value) }))}
          />
          <TextField label="Department" name="department" value={department} onChange={(e) => setDepartment(e.target.value)} />
          <TextField label="Search" name="q" value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="flex items-end gap-2">
            <Button
              onClick={() => {
                setApplied({ status, department, q });
                setPage(1);
              }}
            >
              Apply
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setStatus('');
                setDepartment('');
                setQ('');
                setApplied({ status: '', department: '', q: '' });
                setPage(1);
              }}
            >
              Clear
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
            emptyTitle="No employees"
            emptyHint="Create the first employee or adjust the filters."
            sort={sort}
            onSortChange={(next) => {
              setSort(next);
              setPage(1);
            }}
            caption="Employees"
            testId="employees-table"
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
        title="Add employee"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={submit} loading={create.isPending} disabled={create.isPending}>
              Create employee
            </Button>
          </>
        }
      >
        <div className="grid gap-3 sm:grid-cols-2">
          {createError ? (
            <div className="sm:col-span-2">
              <Alert tone="danger" title={createError.problem.detail || describeProblem(createError.problem).title} nextStep={describeProblem(createError.problem).nextStep}>
                {createError.problem.detail && describeProblem(createError.problem).title !== createError.problem.detail ? (
                  <p>{createError.problem.detail}</p>
                ) : null}
              </Alert>
            </div>
          ) : null}
          {formError ? (
            <div className="sm:col-span-2">
              <Alert tone="danger" title={formError} />
            </div>
          ) : null}

          <TextField label="Employee code" name="employee_code" required value={form.employee_code} onChange={(e) => setForm({ ...form, employee_code: e.target.value })} />
          <TextField label="Full name" name="full_name" required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          <TextField label="Phone" name="phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          <TextField label="Email" type="email" name="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <TextField label="Date of joining" type="date" name="date_of_joining" required value={form.date_of_joining} onChange={(e) => setForm({ ...form, date_of_joining: e.target.value })} />
          <SelectField
            label="Employment type"
            name="employment_type"
            value={form.employment_type}
            onChange={(e) => setForm({ ...form, employment_type: e.target.value })}
            options={EMPLOYMENT_TYPES.map((value) => ({ value, label: humanize(value) }))}
          />
          <TextField label="Department" name="department" value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} />
          <TextField label="Designation" name="designation" value={form.designation} onChange={(e) => setForm({ ...form, designation: e.target.value })} />
          <TextField label="Address" name="address_line" value={form.address_line} onChange={(e) => setForm({ ...form, address_line: e.target.value })} />
          <TextField label="Emergency contact name" name="emergency_contact_name" value={form.emergency_contact_name} onChange={(e) => setForm({ ...form, emergency_contact_name: e.target.value })} />
          <TextField label="Emergency contact phone" name="emergency_contact_phone" value={form.emergency_contact_phone} onChange={(e) => setForm({ ...form, emergency_contact_phone: e.target.value })} />
          <TextField label="Username" name="username" required value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
          <TextField
            label="Initial password"
            name="initial_password"
            help="Leave blank to let the server generate a one-time password, shown once."
            value={form.initial_password}
            onChange={(e) => setForm({ ...form, initial_password: e.target.value })}
          />
          <TextField
            label="Roles (comma separated)"
            name="role_codes"
            value={form.role_codes}
            onChange={(e) => setForm({ ...form, role_codes: e.target.value })}
            help="The server rejects roles the caller may not grant."
          />
        </div>
      </Dialog>
    </div>
  );
}