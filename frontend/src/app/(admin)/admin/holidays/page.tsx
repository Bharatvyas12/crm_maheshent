'use client';

import { useState } from 'react';
import { useBreakTypes, useCreateHoliday, useDeleteHoliday, useHolidays } from '@/features/attendance/hooks';
import { createBreakType, updateBreakType } from '@/features/attendance/api';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useToast } from '@/components/ui/Toast';
import { ApiError } from '@/lib/api-client';
import { describeProblem } from '@/lib/problem-details';
import { formatBusinessDate } from '@/lib/format';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { TextField, CheckboxField } from '@/components/ui/Form';
import { Alert } from '@/components/ui/Alert';
import { SkeletonList } from '@/components/ui/Skeleton';
import { Badge } from '@/components/ui/Badge';
import { ProblemAlert } from '@/components/ui/ProblemAlert';

export default function AdminHolidaysPage() {
  const queryClient = useQueryClient();
  const { push } = useToast();
  const currentYear = new Date().getUTCFullYear();
  const [year, setYear] = useState(currentYear);
  const [date, setDate] = useState('');
  const [name, setName] = useState('');
  const [isPaid, setIsPaid] = useState(true);
  const [isWorkingDay, setIsWorkingDay] = useState(false);

  const holidays = useHolidays(year);
  const breakTypes = useBreakTypes(true);
  const createHoliday = useCreateHoliday();
  const deleteHoliday = useDeleteHoliday();

  const saveBreakType = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof updateBreakType>[1] }) => updateBreakType(id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['attendance'] });
      push({ tone: 'success', title: 'Break type updated' });
    },
    onError: (error) =>
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not update the break type.' })
  });

  const addBreakType = useMutation({
    mutationFn: (body: Parameters<typeof createBreakType>[0]) => createBreakType(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['attendance'] });
      push({ tone: 'success', title: 'Break type created' });
    },
    onError: (error) =>
      push({ tone: 'error', title: error instanceof ApiError ? describeProblem(error.problem).title : 'Could not create the break type.' })
  });

  const [newBreakCode, setNewBreakCode] = useState('');
  const [newBreakName, setNewBreakName] = useState('');
  const [newBreakPaid, setNewBreakPaid] = useState(false);
  const [newBreakMax, setNewBreakMax] = useState('');

  return (
    <div className="space-y-5">
      <PageHeader title="Holidays and break types" description="Working-day overrides and the break types employees can select." />

      <Card>
        <CardHeader
          action={
            <TextField
              label="Year"
              type="number"
              name="year"
              containerClassName="w-28"
              value={String(year)}
              onChange={(e) => setYear(Number(e.target.value) || currentYear)}
            />
          }
        >
          <CardTitle as="h2">Holiday calendar</CardTitle>
        </CardHeader>
        <CardBody className="space-y-4">
          <div className="grid gap-3 md:grid-cols-4">
            <TextField label="Date" type="date" name="holiday_date" value={date} onChange={(e) => setDate(e.target.value)} />
            <TextField label="Name" name="name" value={name} onChange={(e) => setName(e.target.value)} />
            <div className="flex flex-col justify-end gap-1">
              <CheckboxField label="Paid holiday" checked={isPaid} onChange={(e) => setIsPaid(e.target.checked)} />
              <CheckboxField label="Working day override" checked={isWorkingDay} onChange={(e) => setIsWorkingDay(e.target.checked)} />
            </div>
            <div className="flex items-end">
              <Button
                loading={createHoliday.isPending}
                disabled={!date || !name || createHoliday.isPending}
                onClick={() =>
                  createHoliday.mutate(
                    { holiday_date: date, name, is_paid: isPaid, is_working_day: isWorkingDay },
                    {
                      onSuccess: () => {
                        setDate('');
                        setName('');
                      }
                    }
                  )
                }
              >
                Add holiday
              </Button>
            </div>
          </div>

          {holidays.isLoading ? (
            <SkeletonList rows={3} />
          ) : holidays.error ? (
            <ProblemAlert error={holidays.error} onRetry={() => void holidays.refetch()} />
          ) : (holidays.data?.items?.length ?? 0) === 0 ? (
            <p className="text-sm text-content-muted">No holidays configured for {year}.</p>
          ) : (
            <ul className="space-y-2">
              {holidays.data?.items?.map((holiday) => (
                <li key={holiday.id} className="flex items-center justify-between gap-3 border-b border-surface-border/60 pb-2 text-sm last:border-0">
                  <span>
                    <span className="font-medium">{holiday.name}</span>
                    <span className="ml-2 text-xs text-content-muted">{formatBusinessDate(holiday.holiday_date)}</span>
                    {holiday.is_paid ? <Badge tone="success" className="ml-2">Paid</Badge> : <Badge className="ml-2">Unpaid</Badge>}
                    {holiday.is_working_day ? <Badge tone="warning" className="ml-2">Working day</Badge> : null}
                  </span>
                  <Button variant="ghost" size="sm" onClick={() => deleteHoliday.mutate(holiday.id)}>
                    Remove
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle as="h2">Break types</CardTitle>
        </CardHeader>
        <CardBody className="space-y-4">
          <div className="grid gap-3 md:grid-cols-5">
            <TextField label="Code" name="code" value={newBreakCode} onChange={(e) => setNewBreakCode(e.target.value)} />
            <TextField label="Name" name="name" value={newBreakName} onChange={(e) => setNewBreakName(e.target.value)} />
            <TextField label="Max minutes" type="number" name="max_minutes" value={newBreakMax} onChange={(e) => setNewBreakMax(e.target.value)} />
            <div className="flex items-end">
              <CheckboxField label="Paid" checked={newBreakPaid} onChange={(e) => setNewBreakPaid(e.target.checked)} />
            </div>
            <div className="flex items-end">
              <Button
                loading={addBreakType.isPending}
                disabled={!newBreakCode || !newBreakName || addBreakType.isPending}
                onClick={() =>
                  addBreakType.mutate(
                    {
                      code: newBreakCode,
                      name: newBreakName,
                      is_paid: newBreakPaid,
                      max_minutes: newBreakMax ? Number(newBreakMax) : null,
                      requires_approval: false,
                      counts_toward_max_per_day: true
                    },
                    {
                      onSuccess: () => {
                        setNewBreakCode('');
                        setNewBreakName('');
                        setNewBreakMax('');
                      }
                    }
                  )
                }
              >
                Add break type
              </Button>
            </div>
          </div>

          {breakTypes.isLoading ? (
            <SkeletonList rows={3} />
          ) : (breakTypes.data?.items?.length ?? 0) === 0 ? (
            <p className="text-sm text-content-muted">No break types configured.</p>
          ) : (
            <ul className="space-y-2">
              {breakTypes.data?.items?.map((type) => (
                <li key={type.id} className="flex flex-wrap items-center justify-between gap-3 border-b border-surface-border/60 pb-2 text-sm last:border-0">
                  <span>
                    <span className="font-medium">{type.name}</span>
                    <span className="ml-2 text-xs text-content-muted">
                      {type.code} - {type.is_paid ? 'paid' : 'unpaid'}
                      {type.max_minutes ? ` - max ${type.max_minutes} min` : ''}
                    </span>
                    {!type.is_active ? <Badge tone="neutral" className="ml-2">Inactive</Badge> : null}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      loading={saveBreakType.isPending}
                      onClick={() => saveBreakType.mutate({ id: type.id, body: { is_paid: !type.is_paid } })}
                    >
                      Toggle paid
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      loading={saveBreakType.isPending}
                      onClick={() => saveBreakType.mutate({ id: type.id, body: { is_active: !type.is_active } })}
                    >
                      {type.is_active ? 'Deactivate' : 'Activate'}
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <Alert tone="info" title="Break caps and approval rules come from settings." nextStep="Change them in Settings, not here." />
        </CardBody>
      </Card>
    </div>
  );
}