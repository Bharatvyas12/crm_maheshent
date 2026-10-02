'use client';

import { Suspense, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { ApiError } from '@/lib/api-client';
import { formatCountdown, formatDateTime, formatMoney } from '@/lib/format';
import { useAvailableOrders, useClaimOrder, useMyOrders } from '@/features/orders/hooks';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Tabs, TabPanel } from '@/components/ui/Tabs';
import { StatusPill } from '@/components/ui/StatusPill';
import { SkeletonList } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { Pagination } from '@/components/ui/Pagination';
import { ProblemAlert } from '@/components/ui/ProblemAlert';
import { ClaimConflictPanel } from '@/components/orders/ClaimConflictPanel';

function OrdersPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialTab = searchParams.get('tab') === 'mine' ? 'mine' : 'available';
  const [tab, setTab] = useState(initialTab);
  const [page, setPage] = useState(1);
  const [claimError, setClaimError] = useState<unknown>(null);
  const [claimingId, setClaimingId] = useState<string | null>(null);
  const [now, setNow] = useState(() => new Date());

  const available = useAvailableOrders({ page });
  const mine = useMyOrders({ page });
  const claim = useClaimOrder();

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const next = new URLSearchParams(searchParams.toString());
    next.set('tab', tab);
    router.replace(`/app/orders?${next.toString()}`);
  }, [tab, router, searchParams]);

  function handleClaim(orderId: string) {
    setClaimError(null);
    setClaimingId(orderId);
    claim.mutate(orderId, {
      onSuccess: () => {
        setClaimingId(null);
        setTab('mine');
      },
      onError: (error) => {
        setClaimingId(null);
        setClaimError(error);
      }
    });
  }

  const conflict = claimError instanceof ApiError && claimError.code === 'CLAIM_ALREADY_TAKEN';

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Orders</h1>
        <p className="text-sm text-content-muted">Claim available orders and update the ones you hold.</p>
      </div>

      <Tabs
        tabs={[
          { id: 'available', label: 'Available', badge: available.data?.total_items },
          { id: 'mine', label: 'Mine' }
        ]}
        activeId={tab}
        onChange={(id) => {
          setTab(id);
          setPage(1);
          setClaimError(null);
        }}
        ariaLabel="Order views"
      />

      {conflict ? <ClaimConflictPanel error={claimError} onRefresh={() => void available.refetch()} /> : null}
      {claimError && !conflict ? <ProblemAlert error={claimError} onRetry={() => setClaimError(null)} testId="order-claim-error" /> : null}

      <TabPanel id="available" activeId={tab}>
        {available.isLoading ? (
          <SkeletonList rows={3} />
        ) : available.error ? (
          <ProblemAlert error={available.error} onRetry={() => void available.refetch()} />
        ) : (available.data?.items.length ?? 0) === 0 ? (
          <EmptyState title="No orders available" hint="New broadcast orders will appear here." />
        ) : (
          <ul className="space-y-2">
            {available.data?.items.map((order) => (
              <li key={order.id}>
                <Card>
                  <CardHeader action={<StatusPill value={order.status} />}>
                    <CardTitle>{order.order_code}</CardTitle>
                    <p className="mt-0.5 truncate text-xs text-content-muted">{order.customer_name}</p>
                  </CardHeader>
                  <CardBody className="space-y-3">
                    {order.item_summary ? <p className="text-sm">{order.item_summary}</p> : null}
                    <div className="flex flex-wrap items-center gap-3 text-xs text-content-muted">
                      <span>{formatMoney(order.order_amount, order.currency)}</span>
                      {order.item_count ? <span>{order.item_count} item(s)</span> : null}
                      {order.broadcast_at ? <span>Broadcast {formatDateTime(order.broadcast_at)}</span> : null}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        onClick={() => handleClaim(order.id)}
                        loading={claimingId === order.id && claim.isPending}
                        disabled={claim.isPending}
                        data-testid="order-claim-button"
                      >
                        Claim order
                      </Button>
                      <Link
                        href={`/app/orders/${order.id}`}
                        className="inline-flex min-h-touch items-center rounded-md border border-surface-border px-4 text-sm font-medium"
                      >
                        Details
                      </Link>
                    </div>
                  </CardBody>
                </Card>
              </li>
            ))}
          </ul>
        )}
        {available.data ? (
          <Pagination
            page={available.data.page}
            pageSize={available.data.page_size}
            totalItems={available.data.total_items}
            totalPages={available.data.total_pages}
            onPageChange={setPage}
          />
        ) : null}
      </TabPanel>

      <TabPanel id="mine" activeId={tab}>
        {mine.isLoading ? (
          <SkeletonList rows={3} />
        ) : mine.error ? (
          <ProblemAlert error={mine.error} onRetry={() => void mine.refetch()} />
        ) : (mine.data?.items.length ?? 0) === 0 ? (
          <EmptyState title="You have no claimed orders" hint="Claim an order from the Available tab to get started." />
        ) : (
          <ul className="space-y-2">
            {mine.data?.items.map((order) => {
              const countdown = formatCountdown(order.claim_expires_at, now);
              return (
                <li key={order.id}>
                  <Link href={`/app/orders/${order.id}`} className="block">
                    <Card className="transition-shadow hover:shadow-md">
                      <CardBody className="space-y-2">
                        <div className="flex items-start justify-between gap-3">
                          <p className="text-sm font-semibold">{order.order_code}</p>
                          <StatusPill value={order.status} />
                        </div>
                        <p className="truncate text-xs text-content-muted">{order.customer_name}</p>
                        <div className="flex flex-wrap items-center gap-3 text-xs text-content-muted">
                          <span>{formatMoney(order.order_amount, order.currency)}</span>
                          {countdown ? <span data-testid="claim-countdown">Claim expires in {countdown}</span> : null}
                          {order.claim_expires_at && !countdown ? <span className="text-warning">Claim window elapsed</span> : null}
                          {order.allowed_transitions?.length ? <span>Next: {order.allowed_transitions.join(', ')}</span> : null}
                        </div>
                      </CardBody>
                    </Card>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
        {mine.data ? (
          <Pagination
            page={mine.data.page}
            pageSize={mine.data.page_size}
            totalItems={mine.data.total_items}
            totalPages={mine.data.total_pages}
            onPageChange={setPage}
          />
        ) : null}
      </TabPanel>
    </div>
  );
}

export default function EmployeeOrdersPage() {
  return (
    <Suspense fallback={<SkeletonList rows={3} />}>
      <OrdersPageInner />
    </Suspense>
  );
}