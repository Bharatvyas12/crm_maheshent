'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { formatDateTime, formatMoney, humanize } from '@/lib/format';
import { useAddOrderAttachment, useFailOrder, useOrder, useOrderHistory, useReleaseOrder, useUpdateOrderStatus } from '@/features/orders/hooks';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { StatusPill } from '@/components/ui/StatusPill';
import { SkeletonList } from '@/components/ui/Skeleton';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { Alert } from '@/components/ui/Alert';
import { SelectField, TextAreaField } from '@/components/ui/Form';
import { OrderStatusStepper } from '@/components/orders/OrderStatusStepper';
import { FileUploadField, type UploadedFile } from '@/components/FileUploadField';
import { useIdempotency } from '@/lib/idempotency';

const PROOF_PURPOSES = [
  { value: 'PACKING_PROOF', label: 'Packing proof', filePurpose: 'ORDER_PACKING_PROOF' },
  { value: 'DELIVERY_PROOF', label: 'Delivery proof', filePurpose: 'ORDER_DELIVERY_PROOF' },
  { value: 'CUSTOMER_CONFIRMATION', label: 'Customer confirmation', filePurpose: 'ORDER_CUSTOMER_CONFIRMATION' },
  { value: 'OTHER', label: 'Other', filePurpose: 'ORDER_DELIVERY_PROOF' }
];

export default function EmployeeOrderDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? '';
  const idem = useIdempotency();

  const order = useOrder(id);
  const history = useOrderHistory(id);
  const updateStatus = useUpdateOrderStatus();
  const release = useReleaseOrder();
  const fail = useFailOrder();
  const attach = useAddOrderAttachment();

  const [purpose, setPurpose] = useState('DELIVERY_PROOF');
  const [note, setNote] = useState('');
  const [customerConfirmed, setCustomerConfirmed] = useState(false);
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [reason, setReason] = useState('');
  const [actionError, setActionError] = useState<unknown>(null);

  if (order.isLoading) return <SkeletonList rows={4} />;
  if (order.error) return <ProblemAlert error={order.error} onRetry={() => void order.refetch()} />;
  if (!order.data) return null;

  const data = order.data;
  const transitions = data.allowed_transitions ?? [];
  const proofs = (data.attachments ?? []).filter((attachment) => attachment.purpose !== 'OTHER').length;
  const proofRequiredForDelivery = transitions.includes('DELIVERED') && proofs === 0;
  const isFieldWork = ['READY_FOR_DELIVERY', 'OUT_FOR_DELIVERY'].includes(data.status);

  const selectedPurpose = PROOF_PURPOSES.find((option) => option.value === purpose) ?? PROOF_PURPOSES[1];

  return (
    <div className="space-y-4">
      <Link href="/app/orders" className="inline-block text-sm text-primary underline">
        Back to orders
      </Link>

      <Card>
        <CardHeader action={<StatusPill value={data.status} />}>
          <CardTitle as="h1">{data.order_code}</CardTitle>
          <p className="mt-0.5 text-xs text-content-muted">
            {formatMoney(data.order_amount, data.currency)}
            {data.item_count ? ` - ${data.item_count} item(s)` : ''}
          </p>
        </CardHeader>
        <CardBody className="space-y-4">
          <OrderStatusStepper status={data.status} />
          <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-xs text-content-muted">Customer</dt>
              <dd>{data.customer_name}</dd>
            </div>
            {data.customer_phone ? (
              <div>
                <dt className="text-xs text-content-muted">Phone</dt>
                <dd>{data.customer_phone}</dd>
              </div>
            ) : null}
            {data.delivery_address ? (
              <div className="sm:col-span-2">
                <dt className="text-xs text-content-muted">Delivery address</dt>
                <dd>{data.delivery_address}</dd>
              </div>
            ) : null}
            {data.item_summary ? (
              <div className="sm:col-span-2">
                <dt className="text-xs text-content-muted">Items</dt>
                <dd>{data.item_summary}</dd>
              </div>
            ) : null}
            {data.delivery_notes ? (
              <div className="sm:col-span-2">
                <dt className="text-xs text-content-muted">Delivery notes</dt>
                <dd>{data.delivery_notes}</dd>
              </div>
            ) : null}
          </dl>
          {isFieldWork ? (
            <Alert tone="info" title="You are expected to be outside the shop for this stage." nextStep="No location check is applied to field work." />
          ) : null}
        </CardBody>
      </Card>

      {actionError ? <ProblemAlert error={actionError} onRetry={() => setActionError(null)} testId="order-action-error" /> : null}

      {transitions.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle as="h2">Advance status</CardTitle>
          </CardHeader>
          <CardBody className="space-y-3">
            {proofRequiredForDelivery ? (
              <Alert tone="warning" title="Delivery proof is required before this order can be marked delivered." nextStep="Attach the proof below first." />
            ) : null}
            <div className="flex flex-wrap gap-2">
              {transitions.map((target) => (
                <Button
                  key={target}
                  loading={updateStatus.isPending && updateStatus.variables?.body.to_status === target}
                  disabled={updateStatus.isPending || (target === 'DELIVERED' && proofs === 0)}
                  data-testid={`order-transition-${target.toLowerCase()}`}
                  onClick={() => {
                    setActionError(null);
                    updateStatus.mutate(
                      {
                        id,
                        body: {
                          to_status: target,
                          proof_file_ids: target === 'DELIVERED' ? (data.attachments ?? []).map((attachment) => attachment.file_id) : undefined
                        }
                      },
                      { onError: setActionError }
                    );
                  }}
                >
                  Mark {humanize(target).toLowerCase()}
                </Button>
              ))}
            </div>
          </CardBody>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle as="h2">Attach proof</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <SelectField
            label="Proof purpose"
            name="purpose"
            value={purpose}
            onChange={(event) => setPurpose(event.target.value)}
            options={PROOF_PURPOSES.map((option) => ({ value: option.value, label: option.label }))}
          />
          <FileUploadField
            purpose={selectedPurpose.filePurpose}
            label="Photo or file"
            help="A photo of the packing or the delivered order."
            accept="image/*"
            onUploaded={setFiles}
            testId="order-proof-upload"
          />
          <TextAreaField label="Note" name="proof_note" rows={2} value={note} onChange={(event) => setNote(event.target.value)} />
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="h-5 w-5 rounded border-surface-border"
              checked={customerConfirmed}
              onChange={(event) => setCustomerConfirmed(event.target.checked)}
            />
            Customer confirmed receipt
          </label>
          <Button
            variant="secondary"
            loading={attach.isPending}
            disabled={files.length === 0 || attach.isPending}
            onClick={() => {
              setActionError(null);
              attach.mutate(
                {
                  id,
                  body: {
                    file_id: files[files.length - 1].id,
                    purpose,
                    note: note || undefined,
                    customer_confirmed: customerConfirmed || undefined,
                    customer_confirmation_method: customerConfirmed ? 'IN_PERSON' : undefined
                  }
                },
                {
                  onSuccess: () => {
                    setFiles([]);
                    setNote('');
                    setCustomerConfirmed(false);
                    idem.reset();
                  },
                  onError: setActionError
                }
              );
            }}
          >
            Attach proof
          </Button>
        </CardBody>
      </Card>

      {data.attachments && data.attachments.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle as="h2">Proof already attached</CardTitle>
          </CardHeader>
          <CardBody>
            <ul className="space-y-1 text-sm">
              {data.attachments.map((attachment) => (
                <li key={attachment.id} className="flex items-center justify-between gap-2">
                  <span>
                    {humanize(attachment.purpose)}
                    {attachment.note ? ` - ${attachment.note}` : ''}
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
          <CardTitle as="h2">Need to hand this order back?</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <TextAreaField label="Reason" name="release_reason" rows={2} value={reason} onChange={(event) => setReason(event.target.value)} />
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              loading={release.isPending}
              disabled={reason.trim().length === 0 || release.isPending}
              onClick={() => {
                setActionError(null);
                release.mutate({ id, reason }, { onError: setActionError });
              }}
            >
              Release order
            </Button>
            <Button
              variant="danger"
              loading={fail.isPending}
              disabled={reason.trim().length === 0 || fail.isPending}
              onClick={() => {
                setActionError(null);
                fail.mutate({ id, body: { failure_reason: reason } }, { onError: setActionError });
              }}
            >
              Mark as failed
            </Button>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle as="h2">History</CardTitle>
        </CardHeader>
        <CardBody>
          {history.isLoading ? (
            <SkeletonList rows={3} />
          ) : (history.data?.items.length ?? 0) === 0 ? (
            <p className="text-sm text-content-muted">No transitions recorded yet.</p>
          ) : (
            <ol className="space-y-2 text-sm">
              {history.data?.items.map((entry) => (
                <li key={entry.id} className="border-b border-surface-border/60 pb-2 last:border-0">
                  <p>
                    <span className="font-medium">{humanize(entry.to_status)}</span>
                    {entry.from_status ? <span className="text-content-muted"> from {humanize(entry.from_status)}</span> : null}
                  </p>
                  <p className="text-xs text-content-muted">
                    {formatDateTime(entry.created_at)}
                    {entry.reason ? ` - ${entry.reason}` : ''}
                  </p>
                </li>
              ))}
            </ol>
          )}
        </CardBody>
      </Card>
    </div>
  );
}