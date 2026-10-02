'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { formatDateTime, formatMoney, humanize } from '@/lib/format';
import {
  useBroadcastOrder,
  useCancelOrder,
  useOrder,
  useOrderHistory,
  useReassignOrder,
  useUpdateOrderStatus
} from '@/features/orders/hooks';
import { useEmployees } from '@/features/employees/hooks';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { TextField, TextAreaField, SelectField } from '@/components/ui/Form';
import { StatusPill } from '@/components/ui/StatusPill';
import { SkeletonList } from '@/components/ui/Skeleton';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { PermissionGate } from '@/components/PermissionGate';
import { OrderStatusStepper } from '@/components/orders/OrderStatusStepper';

export default function AdminOrderDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? '';
  const order = useOrder(id);
  const history = useOrderHistory(id);
  const employees = useEmployees({ status: 'ACTIVE', page: 1, page_size: 100 });

  const broadcast = useBroadcastOrder();
  const updateStatus = useUpdateOrderStatus();
  const reassign = useReassignOrder();
  const cancel = useCancelOrder();

  const [broadcastOpen, setBroadcastOpen] = useState(false);
  const [audienceScope, setAudienceScope] = useState('ALL_ACTIVE_EMPLOYEES');
  const [expiresAt, setExpiresAt] = useState('');
  const [reassignOpen, setReassignOpen] = useState(false);
  const [reassignReason, setReassignReason] = useState('');
  const [newAssignee, setNewAssignee] = useState('');
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState('');

  if (order.isLoading) return <SkeletonList rows={4} />;
  if (order.error) return <ProblemAlert error={order.error} onRetry={() => void order.refetch()} />;
  if (!order.data) return null;

  const data = order.data;

  return (
    <div className="space-y-4">
      <Link href="/admin/orders" className="inline-block text-sm text-primary underline">
        Back to orders
      </Link>

      <PageHeader
        title={data.order_code}
        description={`${data.customer_name} - created ${formatDateTime(data.created_at)}`}
        actions={
          <>
            <StatusPill value={data.status} />
            <PermissionGate anyOf={['order.broadcast']}>
              <Button variant="secondary" onClick={() => setBroadcastOpen(true)}>
                Broadcast
              </Button>
            </PermissionGate>
            <PermissionGate anyOf={['order.reassign']}>
              <Button variant="secondary" onClick={() => setReassignOpen(true)}>
                Reassign / release
              </Button>
            </PermissionGate>
            <PermissionGate anyOf={['order.cancel']}>
              <Button variant="danger" onClick={() => setCancelOpen(true)}>
                Cancel
              </Button>
            </PermissionGate>
          </>
        }
      />

      {updateStatus.error ? <ProblemAlert error={updateStatus.error} testId="admin-order-action-error" /> : null}

      <Card>
        <CardBody className="space-y-4">
          <OrderStatusStepper status={data.status} />
          <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-xs text-content-muted">Amount</dt>
              <dd>{formatMoney(data.order_amount, data.currency)}</dd>
            </div>
            <div>
              <dt className="text-xs text-content-muted">Assignee</dt>
              <dd>{data.current_assignee?.full_name ?? 'unassigned'}</dd>
            </div>
            <div>
              <dt className="text-xs text-content-muted">Claim expires</dt>
              <dd>{data.claim_expires_at ? formatDateTime(data.claim_expires_at) : '-'}</dd>
            </div>
            {data.customer_phone ? (
              <div>
                <dt className="text-xs text-content-muted">Phone</dt>
                <dd>{data.customer_phone}</dd>
              </div>
            ) : null}
            {data.payment_mode ? (
              <div>
                <dt className="text-xs text-content-muted">Payment mode</dt>
                <dd>{humanize(data.payment_mode)}</dd>
              </div>
            ) : null}
            {data.item_count ? (
              <div>
                <dt className="text-xs text-content-muted">Items</dt>
                <dd>{data.item_count}</dd>
              </div>
            ) : null}
            {data.delivery_address ? (
              <div className="sm:col-span-3">
                <dt className="text-xs text-content-muted">Delivery address</dt>
                <dd>{data.delivery_address}</dd>
              </div>
            ) : null}
            {data.item_summary ? (
              <div className="sm:col-span-3">
                <dt className="text-xs text-content-muted">Items</dt>
                <dd>{data.item_summary}</dd>
              </div>
            ) : null}
          </dl>

          <PermissionGate anyOf={['order.update.status.any']}>
            <div className="flex flex-wrap gap-2">
              {(data.allowed_transitions ?? []).map((target) => (
                <Button
                  key={target}
                  variant="secondary"
                  loading={updateStatus.isPending}
                  onClick={() => updateStatus.mutate({ id, body: { to_status: target } })}
                >
                  Mark {humanize(target).toLowerCase()}
                </Button>
              ))}
            </div>
          </PermissionGate>
        </CardBody>
      </Card>

      {data.attachments && data.attachments.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle as="h2">Proof</CardTitle>
          </CardHeader>
          <CardBody>
            <ul className="space-y-2 text-sm">
              {data.attachments.map((attachment) => (
                <li key={attachment.id} className="flex items-center justify-between gap-2 border-b border-surface-border/60 pb-2 last:border-0">
                  <span>
                    <span className="font-medium">{humanize(attachment.purpose)}</span>
                    {attachment.note ? <span className="ml-2 text-xs text-content-muted">{attachment.note}</span> : null}
                    {attachment.customer_confirmed ? <span className="ml-2 text-xs text-success">Customer confirmed</span> : null}
                  </span>
                  <span className="text-xs text-content-muted">{formatDateTime(attachment.created_at)}</span>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle as="h2">Status history</CardTitle>
        </CardHeader>
        <CardBody>
          {history.isLoading ? (
            <SkeletonList rows={3} />
          ) : (history.data?.items.length ?? 0) === 0 ? (
            <p className="text-sm text-content-muted">No transitions recorded.</p>
          ) : (
            <ol className="space-y-2 text-sm">
              {history.data?.items.map((entry) => (
                <li key={entry.id} className="flex items-start justify-between gap-3 border-b border-surface-border/60 pb-2 last:border-0">
                  <span>
                    <span className="font-medium">{humanize(entry.to_status)}</span>
                    {entry.from_status ? <span className="text-content-muted"> from {humanize(entry.from_status)}</span> : null}
                    {entry.reason ? <span className="block text-xs text-content-muted">{entry.reason}</span> : null}
                  </span>
                  <span className="shrink-0 text-xs text-content-muted">{formatDateTime(entry.created_at)}</span>
                </li>
              ))}
            </ol>
          )}
        </CardBody>
      </Card>

      <Dialog
        open={broadcastOpen}
        onClose={() => setBroadcastOpen(false)}
        title="Broadcast order"
        description="A new broadcast round replaces the active one and notifies the audience."
        footer={
          <>
            <Button variant="secondary" onClick={() => setBroadcastOpen(false)}>
              Cancel
            </Button>
            <Button
              loading={broadcast.isPending}
              onClick={() =>
                broadcast.mutate(
                  { id, body: { audience_scope: audienceScope, expires_at: expiresAt ? new Date(expiresAt).toISOString() : undefined } },
                  { onSuccess: () => setBroadcastOpen(false) }
                )
              }
            >
              Broadcast
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {broadcast.error ? <ProblemAlert error={broadcast.error} /> : null}
          <SelectField
            label="Audience"
            name="audience_scope"
            value={audienceScope}
            onChange={(e) => setAudienceScope(e.target.value)}
            options={[
              { value: 'ALL_ACTIVE_EMPLOYEES', label: 'All active employees' },
              { value: 'ROLE', label: 'By role' },
              { value: 'EXPLICIT', label: 'Specific employees' }
            ]}
          />
          <TextField label="Expires at" type="datetime-local" name="expires_at" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} />
        </div>
      </Dialog>

      <Dialog
        open={reassignOpen}
        onClose={() => setReassignOpen(false)}
        title="Reassign or release"
        description="Without a target the order returns to the pool; with a target it is assigned directly."
        footer={
          <>
            <Button variant="secondary" onClick={() => setReassignOpen(false)}>
              Cancel
            </Button>
            <Button
              loading={reassign.isPending}
              disabled={reassignReason.trim().length === 0}
              onClick={() =>
                reassign.mutate(
                  { id, body: { reason: reassignReason.trim(), new_assignee_employee_id: newAssignee || undefined } },
                  {
                    onSuccess: () => {
                      setReassignOpen(false);
                      setReassignReason('');
                      setNewAssignee('');
                    }
                  }
                )
              }
            >
              Apply
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {reassign.error ? <ProblemAlert error={reassign.error} /> : null}
          <SelectField
            label="New assignee (optional)"
            name="new_assignee_employee_id"
            placeholder="Return to the broadcast pool"
            value={newAssignee}
            onChange={(e) => setNewAssignee(e.target.value)}
            options={(employees.data?.items ?? []).map((employee) => ({ value: employee.id, label: `${employee.full_name} (${employee.employee_code})` }))}
          />
          <TextAreaField label="Reason" name="reason" required value={reassignReason} onChange={(e) => setReassignReason(e.target.value)} />
        </div>
      </Dialog>

      <Dialog
        open={cancelOpen}
        onClose={() => setCancelOpen(false)}
        title="Cancel order"
        description="Cancellation is subject to the configured allowed statuses."
        footer={
          <>
            <Button variant="secondary" onClick={() => setCancelOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={cancel.isPending}
              disabled={cancelReason.trim().length === 0}
              onClick={() =>
                cancel.mutate(
                  { id, body: { reason: cancelReason.trim() } },
                  {
                    onSuccess: () => {
                      setCancelOpen(false);
                      setCancelReason('');
                    }
                  }
                )
              }
            >
              Cancel order
            </Button>
          </>
        }
      >
        {cancel.error ? <ProblemAlert error={cancel.error} /> : null}
        <TextAreaField label="Reason" name="reason" required value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} />
      </Dialog>
    </div>
  );
}