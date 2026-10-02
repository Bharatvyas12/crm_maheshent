'use client';

import { Suspense, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCreateOrder, useOrders } from '@/features/orders/hooks';
import { useEmployees } from '@/features/employees/hooks';
import { formatDateTime, formatMoney, humanize } from '@/lib/format';
import { Card, CardBody } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { DataTable, type Column } from '@/components/ui/DataTable';
import { Pagination } from '@/components/ui/Pagination';
import { StatusPill } from '@/components/ui/StatusPill';
import { Dialog } from '@/components/ui/Dialog';
import { TextField, TextAreaField, SelectField, CheckboxField } from '@/components/ui/Form';
import { Alert } from '@/components/ui/Alert';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { FileUploadField, type UploadedFile } from '@/components/FileUploadField';
import type { Order } from '@/lib/types';

const AUDIENCE_SCOPES = [
  { value: 'ALL_ACTIVE_EMPLOYEES', label: 'All active employees' },
  { value: 'EXPLICIT', label: 'Specific employees' },
  { value: 'ROLE', label: 'By role' }
];

function OrdersList() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState('-created_at');
  const [status, setStatus] = useState(searchParams.get('status') ?? '');
  const [q, setQ] = useState('');
  const [applied, setApplied] = useState({ status: searchParams.get('status') ?? '', q: '' });
  const [open, setOpen] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);

  const query = useOrders({ ...applied, sort, page });
  const employees = useEmployees({ status: 'ACTIVE', page: 1, page_size: 100 });
  const create = useCreateOrder();

  const [form, setForm] = useState({
    order_code: '',
    customer_name: '',
    customer_phone: '',
    delivery_address: '',
    delivery_notes: '',
    item_summary: '',
    item_count: '',
    order_amount: '',
    currency: 'INR',
    payment_mode: 'CASH',
    notes: '',
    broadcast: true,
    audience_scope: 'ALL_ACTIVE_EMPLOYEES',
    audienceEmployeeIds: [] as string[],
    audience_roles: ''
  });
  const [formError, setFormError] = useState<string | null>(null);

  function submit() {
    setFormError(null);
    if (!form.customer_name.trim()) return setFormError('Customer name is required.');

    let audience_payload: Record<string, unknown> | undefined;
    if (form.broadcast && form.audience_scope === 'EXPLICIT') {
      if (form.audienceEmployeeIds.length === 0) return setFormError('Choose at least one employee for an explicit broadcast.');
      audience_payload = { employee_ids: form.audienceEmployeeIds };
    }
    if (form.broadcast && form.audience_scope === 'ROLE') {
      if (!form.audience_roles.trim()) return setFormError('Enter at least one role code.');
      audience_payload = { role_codes: form.audience_roles.split(',').map((code) => code.trim()).filter(Boolean) };
    }

    create.mutate(
      {
        order_code: form.order_code || undefined,
        customer_name: form.customer_name.trim(),
        customer_phone: form.customer_phone || undefined,
        delivery_address: form.delivery_address || undefined,
        delivery_notes: form.delivery_notes || undefined,
        item_summary: form.item_summary || undefined,
        item_count: form.item_count ? Number(form.item_count) : null,
        order_amount: form.order_amount.trim() || '0.00',
        currency: form.currency,
        payment_mode: form.payment_mode || undefined,
        notes: form.notes || undefined,
        proof_file_ids: uploadedFiles.map((file) => file.id),
        broadcast: form.broadcast ? { audience_scope: form.audience_scope, audience_payload } : undefined
      },
      {
        onSuccess: () => {
          setOpen(false);
          setUploadedFiles([]);
          setForm({ ...form, order_code: '', customer_name: '', customer_phone: '', delivery_address: '', delivery_notes: '', item_summary: '', item_count: '', order_amount: '', notes: '', audienceEmployeeIds: [], audience_roles: '' });
        }
      }
    );
  }

  const columns: Array<Column<Order>> = [
    {
      key: 'order_code',
      header: 'Order',
      sortable: true,
      render: (row) => (
        <Link href={`/admin/orders/${row.id}`} className="font-medium text-primary underline">
          {row.order_code}
        </Link>
      )
    },
    { key: 'customer_name', header: 'Customer', sortable: true, render: (row) => row.customer_name },
    { key: 'order_amount', header: 'Amount', align: 'right', sortable: true, render: (row) => formatMoney(row.order_amount, row.currency) },
    { key: 'status', header: 'Status', sortable: true, render: (row) => <StatusPill value={row.status} /> },
    { key: 'current_assignee', header: 'Assignee', render: (row) => row.current_assignee?.full_name ?? '-' },
    { key: 'broadcast_at', header: 'Broadcast', sortable: true, render: (row) => (row.broadcast_at ? formatDateTime(row.broadcast_at) : '-') },
    { key: 'created_at', header: 'Created', sortable: true, render: (row) => formatDateTime(row.created_at) }
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Orders"
        description="Register, broadcast and manage orders. Employees claim from their own screen."
        actions={<Button onClick={() => setOpen(true)}>Register order</Button>}
      />

      <Card>
        <CardBody className="grid gap-3 md:grid-cols-4">
          <SelectField
            label="Status"
            name="status"
            placeholder="Any"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            options={['BROADCASTED', 'CLAIMED', 'PACKING', 'PACKED', 'READY_FOR_DELIVERY', 'OUT_FOR_DELIVERY', 'DELIVERED', 'CANCELLED', 'FAILED', 'REASSIGNED'].map((value) => ({ value, label: humanize(value) }))}
          />
          <TextField label="Search code or customer" name="q" value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="flex items-end gap-2 md:col-span-2">
            <Button
              onClick={() => {
                setApplied({ status, q });
                setPage(1);
                router.replace(status ? `/admin/orders?status=${status}` : '/admin/orders');
              }}
            >
              Apply
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setStatus('');
                setQ('');
                setApplied({ status: '', q: '' });
                setPage(1);
                router.replace('/admin/orders');
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
            emptyTitle="No orders"
            emptyHint="Register an order to broadcast it to employees."
            sort={sort}
            onSortChange={(next) => {
              setSort(next);
              setPage(1);
            }}
            caption="Orders"
            testId="admin-orders-table"
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
        title="Register order"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={submit} loading={create.isPending} disabled={create.isPending}>
              Create
            </Button>
          </>
        }
      >
        <div className="grid gap-3 sm:grid-cols-2">
          {create.error ? (
            <div className="sm:col-span-2">
              <ProblemAlert error={create.error} testId="create-order-error" />
            </div>
          ) : null}
          {formError ? (
            <div className="sm:col-span-2">
              <Alert tone="danger" title={formError} />
            </div>
          ) : null}
          <TextField label="Order code" name="order_code" help="Leave blank to let the server generate one." value={form.order_code} onChange={(e) => setForm({ ...form, order_code: e.target.value })} />
          <TextField label="Customer name" name="customer_name" required value={form.customer_name} onChange={(e) => setForm({ ...form, customer_name: e.target.value })} />
          <TextField label="Customer phone" name="customer_phone" value={form.customer_phone} onChange={(e) => setForm({ ...form, customer_phone: e.target.value })} />
          <TextField label="Amount (Optional)" name="order_amount" help="Decimal string, e.g. 1499.00 (leave blank if not set)" value={form.order_amount} onChange={(e) => setForm({ ...form, order_amount: e.target.value })} />
          <TextField label="Item count" type="number" name="item_count" value={form.item_count} onChange={(e) => setForm({ ...form, item_count: e.target.value })} />
          <SelectField
            label="Payment mode"
            name="payment_mode"
            value={form.payment_mode}
            onChange={(e) => setForm({ ...form, payment_mode: e.target.value })}
            options={['CASH', 'CARD', 'UPI', 'COD', 'OTHER'].map((value) => ({ value, label: humanize(value) }))}
          />
          <div className="sm:col-span-2">
            <FileUploadField
              purpose="ORDER_PACKING_PROOF"
              label="Order Photo / Receipt Slip (Parchi Photo Upload)"
              help="Upload photo of paper parchi/receipt so you don't need to write long items list"
              accept="image/*,.pdf"
              multiple
              onUploaded={(files) => setUploadedFiles(files)}
            />
          </div>
          <div className="sm:col-span-2">
            <TextField label="Items text summary (Optional)" name="item_summary" value={form.item_summary} onChange={(e) => setForm({ ...form, item_summary: e.target.value })} />
          </div>
          <div className="sm:col-span-2">
            <TextAreaField label="Delivery address" name="delivery_address" rows={2} value={form.delivery_address} onChange={(e) => setForm({ ...form, delivery_address: e.target.value })} />
          </div>
          <div className="sm:col-span-2">
            <TextAreaField label="Delivery notes" name="delivery_notes" rows={2} value={form.delivery_notes} onChange={(e) => setForm({ ...form, delivery_notes: e.target.value })} />
          </div>
          <div className="sm:col-span-2">
            <CheckboxField label="Broadcast immediately" checked={form.broadcast} onChange={(e) => setForm({ ...form, broadcast: e.target.checked })} help="Orders are invisible to employees until broadcast." />
          </div>
          {form.broadcast ? (
            <>
              <SelectField
                label="Audience"
                name="audience_scope"
                value={form.audience_scope}
                onChange={(e) => setForm({ ...form, audience_scope: e.target.value })}
                options={AUDIENCE_SCOPES}
              />
              {form.audience_scope === 'ROLE' ? (
                <TextField label="Role codes (comma separated)" name="audience_roles" value={form.audience_roles} onChange={(e) => setForm({ ...form, audience_roles: e.target.value })} />
              ) : null}
              {form.audience_scope === 'EXPLICIT' ? (
                <div className="sm:col-span-2">
                  <p className="mb-1 text-sm font-medium">Employees</p>
                  <div className="max-h-40 space-y-1 overflow-y-auto rounded-md border border-surface-border p-2">
                    {(employees.data?.items ?? []).map((employee) => (
                      <label key={employee.id} className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          className="h-4 w-4"
                          checked={form.audienceEmployeeIds.includes(employee.id)}
                          onChange={() =>
                            setForm((current) => ({
                              ...current,
                              audienceEmployeeIds: current.audienceEmployeeIds.includes(employee.id)
                                ? current.audienceEmployeeIds.filter((value) => value !== employee.id)
                                : [...current.audienceEmployeeIds, employee.id]
                            }))
                          }
                        />
                        {employee.full_name} ({employee.employee_code})
                      </label>
                    ))}
                  </div>
                </div>
              ) : null}
            </>
          ) : null}
        </div>
      </Dialog>
    </div>
  );
}

export default function AdminOrdersPage() {
  return (
    <Suspense fallback={<div className="h-40" />}>
      <OrdersList />
    </Suspense>
  );
}