import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ApiError } from '@/lib/api-client';
import { ProblemAlert } from './ProblemAlert';

function apiError(problem: Record<string, unknown>, status = 422): ApiError {
  return new ApiError({ title: 't', status, code: 'RULE_VIOLATION', ...problem } as never, 'req-1');
}

describe('ProblemAlert', () => {
  it('exposes the stable server code without depending on copy', () => {
    render(<ProblemAlert error={apiError({ code: 'CLAIM_ALREADY_TAKEN', status: 409 })} />);
    const alert = screen.getByTestId('problem-alert');
    expect(alert).toBeInTheDocument();
    expect(alert.querySelector('[data-code]')?.getAttribute('data-code')).toBe('CLAIM_ALREADY_TAKEN');
  });

  it('renders the specific attendance failure reason and its corrective step', () => {
    render(<ProblemAlert error={apiError({ code: 'RULE_VIOLATION', rule_code: 'OUTSIDE_GEOFENCE', status: 422 })} />);
    expect(screen.getByText(/outside the allowed distance from the shop/i)).toBeInTheDocument();
    expect(screen.getByText(/move closer/i)).toBeInTheDocument();
  });

  it('lists validation field errors', () => {
    render(
      <ProblemAlert
        error={apiError({
          code: 'VALIDATION_ERROR',
          errors: [{ field: 'longitude', code: 'OUT_OF_RANGE', message: 'Longitude must be between -180 and 180.' }]
        })}
      />
    );
    expect(screen.getByText(/Longitude must be between -180 and 180\./)).toBeInTheDocument();
  });

  it('offers retry for recoverable failures', async () => {
    const onRetry = vi.fn();
    render(<ProblemAlert error={apiError({ code: 'INTERNAL_ERROR', status: 500 })} onRetry={onRetry} />);
    await userEvent.click(screen.getByRole('button', { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('does not offer retry for a permission denial or a hidden record', () => {
    const { unmount } = render(<ProblemAlert error={apiError({ code: 'PERMISSION_DENIED', status: 403 })} onRetry={() => {}} />);
    expect(screen.queryByRole('button', { name: /retry/i })).toBeNull();
    unmount();
    render(<ProblemAlert error={apiError({ code: 'RESOURCE_NOT_FOUND', status: 404 })} onRetry={() => {}} />);
    expect(screen.queryByRole('button', { name: /retry/i })).toBeNull();
  });

  it('shows the request id only inside the technical-details expander', () => {
    render(<ProblemAlert error={apiError({ code: 'INTERNAL_ERROR', status: 500 })} />);
    expect(screen.getByText(/Technical details/)).toBeInTheDocument();
    expect(screen.getByText(/req-1/)).toBeInTheDocument();
  });
});