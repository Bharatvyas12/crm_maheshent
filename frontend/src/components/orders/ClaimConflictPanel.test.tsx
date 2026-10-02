import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ApiError } from '@/lib/api-client';
import { ClaimConflictPanel } from './ClaimConflictPanel';

function conflict(overrides: Record<string, unknown> = {}): ApiError {
  return new ApiError(
    {
      title: 'Order already claimed',
      status: 409,
      code: 'CLAIM_ALREADY_TAKEN',
      detail: 'Another employee holds this order.',
      current_status: 'CLAIMED',
      claimed_at: '2026-09-25T10:00:00Z',
      claimed_by: { id: 'e2', full_name: 'Ravi Kumar' },
      ...overrides
    } as never,
    'req-conflict-9'
  );
}

describe('ClaimConflictPanel (docs/07 section 5.4)', () => {
  it('states that another employee won and reveals who and when', () => {
    render(<ClaimConflictPanel error={conflict()} onRefresh={() => {}} />);
    expect(screen.getByTestId('order-claim-conflict-panel')).toBeInTheDocument();
    expect(screen.getByText(/another employee claimed this order/i)).toBeInTheDocument();
    expect(screen.getByText(/Ravi Kumar/)).toBeInTheDocument();
    expect(screen.getByText(/Current status: CLAIMED/)).toBeInTheDocument();
  });

  it('still renders a usable conflict state when the server withholds the winner', () => {
    render(<ClaimConflictPanel error={conflict({ claimed_by: null, claimed_at: null, current_status: null })} onRefresh={() => {}} />);
    expect(screen.getByText(/another employee claimed this order/i)).toBeInTheDocument();
    expect(screen.queryByText(/Current status/)).toBeNull();
  });

  it('lets the user refresh the order and the available list again', async () => {
    const onRefresh = vi.fn();
    render(<ClaimConflictPanel error={conflict()} onRefresh={onRefresh} />);
    await userEvent.click(screen.getByRole('button', { name: /refresh again/i }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it('degrades safely for a non-ApiError value', () => {
    render(<ClaimConflictPanel error={new Error('boom')} onRefresh={() => {}} />);
    expect(screen.getByTestId('order-claim-conflict-panel')).toBeInTheDocument();
  });
});