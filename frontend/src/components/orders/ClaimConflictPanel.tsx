'use client';

import { ApiError } from '@/lib/api-client';
import { formatDateTime, formatMoney } from '@/lib/format';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';

/**
 * Conflict panel for `CLAIM_ALREADY_TAKEN` (docs/07_UI_SPEC.md section 5.4).
 * Shows who won and when when the server provides it, and refreshes the order/available list.
 */
export function ClaimConflictPanel({ error, onRefresh }: { error: unknown; onRefresh: () => void }) {
  const apiError = error instanceof ApiError ? error : null;
  const claimedAt = apiError?.problem.claimed_at ?? null;
  const claimedBy = apiError?.problem.claimed_by ?? null;
  const currentStatus = apiError?.problem.current_status ?? null;

  return (
    <div data-testid="order-claim-conflict-panel">
      <Alert
        tone="warning"
        title="Another employee claimed this order."
        nextStep="The order and the available list were refreshed."
        actions={
          <Button variant="secondary" size="sm" onClick={onRefresh}>
            Refresh again
          </Button>
        }
      >
        <ul className="space-y-0.5 text-xs">
          {claimedBy?.full_name ? <li>Claimed by {claimedBy.full_name}</li> : null}
          {claimedAt ? <li>Claimed at {formatDateTime(claimedAt)}</li> : null}
          {currentStatus ? <li>Current status: {currentStatus}</li> : null}
        </ul>
      </Alert>
    </div>
  );
}

export function OrderAmount({ amount, currency }: { amount: string; currency: string }) {
  return <span className="font-medium">{formatMoney(amount, currency)}</span>;
}