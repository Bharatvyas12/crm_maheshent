'use client';

import { cn } from '@/lib/utils';
import { humanize } from '@/lib/format';

/**
 * Lifecycle stepper. The steps and their labels come from the documented order lifecycle
 * (docs/00_PRODUCT_SCOPE.md section 7 / docs/03_API_CONTRACT.md section 9.3); the ACTIONS still
 * come from the server's `allowed_transitions[]`.
 */
export const ORDER_STEPS = [
  'BROADCASTED',
  'CLAIMED',
  'PACKING',
  'PACKED',
  'READY_FOR_DELIVERY',
  'OUT_FOR_DELIVERY',
  'DELIVERED'
] as const;

const TERMINAL_ALTERNATIVES = ['CANCELLED', 'FAILED', 'REASSIGNED'];

export function OrderStatusStepper({ status }: { status: string }) {
  const isAlternative = TERMINAL_ALTERNATIVES.includes(status);
  const currentIndex = ORDER_STEPS.indexOf(status as (typeof ORDER_STEPS)[number]);

  return (
    <div data-testid="order-status-stepper">
      <ol className="flex flex-wrap gap-1.5">
        {ORDER_STEPS.map((step, index) => {
          const done = !isAlternative && currentIndex >= 0 && index < currentIndex;
          const current = step === status;
          return (
            <li
              key={step}
              aria-current={current ? 'step' : undefined}
              className={cn(
                'rounded-full border px-2 py-0.5 text-xs',
                current
                  ? 'border-primary bg-primary-soft font-semibold text-primary'
                  : done
                    ? 'border-success/40 bg-success-soft text-success'
                    : 'border-surface-border text-content-muted'
              )}
            >
              {humanize(step)}
            </li>
          );
        })}
      </ol>
      {isAlternative ? <p className="mt-2 text-xs font-medium text-warning">This order ended as {humanize(status)}.</p> : null}
    </div>
  );
}