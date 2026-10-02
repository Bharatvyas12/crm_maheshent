'use client';

import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useAdminAttendance } from '@/features/attendance/hooks';
import { useEmployees } from '@/features/employees/hooks';
import { useSession } from '@/features/auth/session';
import { formatBusinessDate, formatDuration, formatTime, humanize } from '@/lib/format';
import { Card, CardBody } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { DataTable, type Column } from '@/components/ui/DataTable';
import { Pagination } from '@/components/ui/Pagination';
import { StatusPill } from '@/components/ui/StatusPill';
import { TextField, SelectField } from '@/components/ui/Form';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { PermissionGate } from '@/components/PermissionGate';
import type { AttendanceRecord } from '@/lib/types';

function AttendanceRegister() {
  const { settings } = useSession();
  const searchParams = useSearchParams();
  const router = useRouter();

  const [page, setPage] = useState(1);
  const [sort, setSort] = useState('-business_date');
  const [from, setFrom] = useState(searchParams.get('from') ?? '');
  const [to, setTo] = useState(searchParams.get('to') ?? '');
  const [status, setStatus] = useState(searchParams.get('status') ?? '');
  const [employeeId, setEmployeeId] = useState('');
  const [q, setQ] = useState('');
  const [applied, setApplied] = useState({ from: searchParams.get('from') ?? '', to: searchParams.get('to') ?? '', status: searchParams.get('status') ?? '' });

  const employees = useEmployees({ page: 1, page_size: 100 });
  const query = useAdminAttendance({ ...applied, employee_id: employeeId || undefined, q: q || undefined, sort, page });

  function applyFilters() {
    setApplied({ from, to, status });
    setPage(1);
    const params = new URLSearchParams();
    if (from) params.set('from', from);
    if (to) params.set('to', to);
    if (status) params.set('status', status);
    router.replace(`/admin/attendance?${params.toString()}`);
  }

  function clearFilters() {
    setFrom('');
    setTo('');
    setStatus('');
    setEmployeeId('');
    setQ('');
    setApplied({ from: '', to: '', status: '' });
    setPage(1);
    router.replace('/admin/attendance');
  }

  const columns: Array<Column<AttendanceRecord>> = [
    {
      key: 'employee',
      header: 'Employee',
      render: (row) => (
        <span>
          <span className="font-medium">{row.employee?.full_name ?? '-'}</span>
          <span className="block text-xs text-content-muted">{row.employee?.employee_code ?? ''}</span>
        </span>
      )
    },
    { key: 'business_date', header: 'Date', sortable: true, render: (row) => formatBusinessDate(row.business_date) },
    { key: 'status', header: 'Status', sortable: true, render: (row) => <StatusPill value={row.status} /> },
    { key: 'day_classification', header: 'Classification', render: (row) => humanize(row.day_classification) },
    { key: 'worked', header: 'Worked', align: 'right', render: (row) => formatDuration(row.worked_seconds) },
    { key: 'break', header: 'Break', align: 'right', render: (row) => formatDuration(row.break_seconds) },
    { key: 'overtime', header: 'Overtime', align: 'right', render: (row) => formatDuration(row.overtime_seconds) },
    { key: 'first_check_in_at', header: 'In', render: (row) => formatTime(row.first_check_in_at, settings.business_timezone) },
    { key: 'last_check_out_at', header: 'Out', render: (row) => formatTime(row.last_check_out_at, settings.business_timezone) },
    { key: 'late_minutes', header: 'Late', align: 'right', sortable: true, render: (row) => `${row.late_minutes} min` },
    {
      key: 'anomalies',
      header: 'Anomalies',
      render: (row) =>
        row.anomalies && row.anomalies.length > 0 ? (
          <span className="text-xs font-medium text-warning">{row.anomalies.length} flag(s)</span>
        ) : (
          <span className="text-xs text-content-muted">-</span>
        )
    }
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Attendance register"
        description="Every recorded day with verification evidence available on the detail view."
        actions={
          <PermissionGate anyOf={['report.export']}>
            <Link
              href="/admin/reports?type=attendance"
              className="inline-flex min-h-touch items-center rounded-md border border-surface-border px-4 text-sm font-medium"
            >
              Reports &amp; export
            </Link>
          </PermissionGate>
        }
      />

      <Card>
        <CardBody className="grid gap-3 md:grid-cols-3 lg:grid-cols-5">
          <TextField label="From" type="date" name="from" value={from} onChange={(e) => setFrom(e.target.value)} />
          <TextField label="To" type="date" name="to" value={to} onChange={(e) => setTo(e.target.value)} />
          <SelectField
            label="Status"
            name="status"
            placeholder="Any"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            options={['NOT_MARKED', 'PRESENT', 'INCOMPLETE', 'ABSENT', 'ON_LEAVE', 'HOLIDAY', 'WEEKLY_OFF'].map((value) => ({ value, label: humanize(value) }))}
          />
          <SelectField
            label="Employee"
            name="employee_id"
            placeholder="All employees"
            value={employeeId}
            onChange={(e) => setEmployeeId(e.target.value)}
            options={(employees.data?.items ?? []).map((employee) => ({ value: employee.id, label: `${employee.full_name} (${employee.employee_code})` }))}
          />
          <TextField label="Search" name="q" value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="flex items-end gap-2 lg:col-span-5">
            <Button onClick={applyFilters}>Apply filters</Button>
            <Button variant="secondary" onClick={clearFilters}>
              Clear filters
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
            emptyTitle="No attendance records"
            emptyHint="Adjust the filters or date range."
            sort={sort}
            onSortChange={(next) => {
              setSort(next);
              setPage(1);
            }}
            caption="Attendance register"
            testId="attendance-register-table"
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
    </div>
  );
}

export default function AdminAttendancePage() {
  return (
    <Suspense fallback={<div className="h-40" />}>
      <AttendanceRegister />
    </Suspense>
  );
}