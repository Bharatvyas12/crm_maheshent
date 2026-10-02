import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ApiError } from '@/lib/api-client';
import type { AttendanceRecord, BreakType } from '@/lib/types';
import { AttendanceActionPanel } from './AttendanceActionPanel';

// --- controllable mocks -----------------------------------------------------

const state = {
  checkIn: vi.fn(),
  checkOut: vi.fn(),
  startBreak: vi.fn(),
  endBreak: vi.fn(),
  refetch: vi.fn(),
  breakTypes: { items: [] as BreakType[] },
  permission: 'granted' as 'granted' | 'denied' | 'prompt' | 'unsupported',
  location: vi.fn()
};

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={typeof href === 'string' ? href : String(href)} {...rest}>
      {children}
    </a>
  )
}));

vi.mock('@/features/auth/session', () => ({
  useSession: () => ({
    settings: { business_timezone: 'Asia/Kolkata', currency: 'INR' },
    permissions: [],
    user: null,
    employee: null
  })
}));

vi.mock('@/features/attendance/geolocation', async () => {
  const actual = await vi.importActual<typeof import('@/features/attendance/geolocation')>('@/features/attendance/geolocation');
  return {
    ...actual,
    locationPermissionState: () => Promise.resolve(state.permission),
    getCurrentLocation: (...args: unknown[]) => state.location(...args)
  };
});

vi.mock('@/features/attendance/hooks', () => ({
  useTodayAttendance: () => ({ refetch: state.refetch, data: undefined, isLoading: false }),
  useBreakTypes: () => ({ data: state.breakTypes, isLoading: false }),
  useCheckIn: () => ({ mutateAsync: state.checkIn, isPending: false }),
  useCheckOut: () => ({ mutateAsync: state.checkOut, isPending: false }),
  useStartBreak: () => ({ mutateAsync: state.startBreak, isPending: false }),
  useEndBreak: () => ({ mutateAsync: state.endBreak, isPending: false })
}));

import { LocationError } from '@/features/attendance/geolocation';

const FIX = { latitude: 12.9716, longitude: 77.5946, accuracy_meters: 12, location_captured_at: '2026-09-25T09:30:00Z' };

function record(overrides: Partial<AttendanceRecord> = {}): AttendanceRecord {
  return {
    id: 'att-1',
    employee_id: 'emp-1',
    business_date: '2026-09-25',
    status: 'NOT_MARKED',
    day_classification: 'NONE',
    first_check_in_at: null,
    last_check_out_at: null,
    worked_seconds: 0,
    worked_hours: '0.00',
    break_seconds: 0,
    unpaid_break_seconds: 0,
    overtime_seconds: 0,
    late_minutes: 0,
    early_checkout_minutes: 0,
    is_open: false,
    is_corrected: false,
    computed_at: null,
    version: 1,
    next_allowed_action: 'CHECK_IN',
    required_evidence: { mode: 'GPS', location_required: true, qr_required: false },
    ...overrides
  };
}

beforeEach(() => {
  state.checkIn.mockReset().mockResolvedValue({ ...record({ status: 'PRESENT', first_check_in_at: '2026-09-25T09:30:00Z' }), verification: { method: 'GPS', result: 'PASS', distance_meters: 20, accuracy_meters: 12, geofence_radius_meters: 100, qr_result: null, failure_code: null, failure_reason: null } });
  state.checkOut.mockReset().mockResolvedValue(record({ status: 'PRESENT' }));
  state.startBreak.mockReset().mockResolvedValue({ id: 'b1' });
  state.endBreak.mockReset().mockResolvedValue({ id: 'b1' });
  state.refetch.mockReset().mockResolvedValue(undefined);
  state.permission = 'granted';
  state.location.mockReset().mockResolvedValue(FIX);
  state.breakTypes = { items: [] };
});

describe('AttendanceActionPanel - server-driven action mapping', () => {
  it('renders the single action the server allows, never deciding locally', () => {
    const { unmount } = render(<AttendanceActionPanel record={record({ next_allowed_action: 'CHECK_IN' })} />);
    expect(screen.getByTestId('attendance-check-in-button')).toHaveTextContent('Check in');
    unmount();

    render(<AttendanceActionPanel record={record({ next_allowed_action: 'CHECK_OUT' })} />);
    expect(screen.getByTestId('attendance-check-out-button')).toHaveTextContent('Check out');
  });

  it('offers a correction link and no action button when the server says REQUEST_CORRECTION', () => {
    render(<AttendanceActionPanel record={record({ next_allowed_action: 'REQUEST_CORRECTION', is_open: false })} />);
    expect(screen.getByRole('link', { name: /request an attendance correction/i })).toHaveAttribute('href', '/app/attendance/corrections');
    expect(screen.queryByTestId('attendance-check-in-button')).toBeNull();
    expect(screen.queryByTestId('attendance-check-out-button')).toBeNull();
  });

  it('requests location only at the moment of the action, then submits one-shot evidence', async () => {
    render(<AttendanceActionPanel record={record()} />);
    expect(state.location).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId('attendance-check-in-button'));
    await waitFor(() => expect(state.checkIn).toHaveBeenCalledTimes(1));
    expect(state.location).toHaveBeenCalledTimes(1);

    const payload = state.checkIn.mock.calls[0][0] as { evidence: Record<string, unknown>; idempotencyKey: string };
    expect(payload.evidence.latitude).toBe(12.9716);
    expect(payload.evidence.longitude).toBe(77.5946);
    expect(payload.evidence.accuracy_meters).toBe(12);
    expect(payload.evidence.location_captured_at).toBe('2026-09-25T09:30:00Z');
    expect(payload.idempotencyKey).toBeTruthy();
  });

  it('never collects a location when the server mode does not require it', async () => {
    render(
      <AttendanceActionPanel record={record({ required_evidence: { mode: 'NONE', location_required: false, qr_required: false } })} />
    );
    await userEvent.click(screen.getByTestId('attendance-check-in-button'));
    await waitFor(() => expect(state.checkIn).toHaveBeenCalledTimes(1));
    expect(state.location).not.toHaveBeenCalled();
  });

  it('opens the QR scanner when the server requires a shop code', async () => {
    render(
      <AttendanceActionPanel record={record({ required_evidence: { mode: 'QR', location_required: false, qr_required: true } })} />
    );
    await userEvent.click(screen.getByTestId('attendance-check-in-button'));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/scan the shop qr code/i)).toBeInTheDocument();
    expect(state.checkIn).not.toHaveBeenCalled();
  });

  it('shows the server confirmation and the verification summary on success', async () => {
    render(<AttendanceActionPanel record={record()} />);
    await userEvent.click(screen.getByTestId('attendance-check-in-button'));
    expect(await screen.findByTestId('attendance-success')).toBeInTheDocument();
    expect(screen.getByText(/confirmed by the server/i)).toBeInTheDocument();
    expect(screen.getByText(/20 m from shop/)).toBeInTheDocument();
    expect(state.refetch).toHaveBeenCalled();
  });

  it('surfaces a geofence rejection with the server reason and a corrective step', async () => {
    state.checkIn.mockRejectedValue(
      new ApiError(
        { title: 'Not allowed', status: 422, code: 'RULE_VIOLATION', rule_code: 'OUTSIDE_GEOFENCE', detail: 'You are 240 m away.' } as never,
        'req-1'
      )
    );
    render(<AttendanceActionPanel record={record()} />);
    await userEvent.click(screen.getByTestId('attendance-check-in-button'));
    expect(await screen.findByTestId('attendance-error')).toBeInTheDocument();
    expect(screen.getByText(/outside the allowed distance from the shop/i)).toBeInTheDocument();
    expect(screen.getByText(/move closer and retry/i)).toBeInTheDocument();
    expect(screen.queryByTestId('attendance-success')).toBeNull();
    // The unresolved state is re-read from the server rather than assumed.
    expect(state.refetch).toHaveBeenCalled();
  });

  it('maps a denied browser permission to a plain-language failure without inventing success', async () => {
    state.permission = 'denied';
    state.location.mockRejectedValue(new LocationError('PERMISSION_DENIED', 'Location permission was denied.'));
    render(<AttendanceActionPanel record={record()} />);
    await userEvent.click(screen.getByTestId('attendance-check-in-button'));
    expect(await screen.findByTestId('attendance-error')).toBeInTheDocument();
    expect(state.checkIn).not.toHaveBeenCalled();
  });

  it('never shows a checked-in state when the request never reached the server', async () => {
    state.checkIn.mockRejectedValue(new ApiError({ title: 'Network error', status: 0, code: 'NETWORK_ERROR' } as never, null));
    render(<AttendanceActionPanel record={record()} />);
    await userEvent.click(screen.getByTestId('attendance-check-in-button'));
    expect(await screen.findByTestId('attendance-error')).toBeInTheDocument();
    expect(screen.queryByTestId('attendance-success')).toBeNull();
  });

  it('disables the primary control while the request is in flight (duplicate-click protection)', async () => {
    let release: (value: unknown) => void = () => {};
    state.checkIn.mockImplementation(() => new Promise((resolve) => { release = resolve; }));
    render(<AttendanceActionPanel record={record()} />);
    const button = screen.getByTestId('attendance-check-in-button');
    await userEvent.click(button);
    await waitFor(() => expect(button).toBeDisabled());
    await userEvent.click(button).catch(() => undefined);
    expect(state.checkIn).toHaveBeenCalledTimes(1);
    release(record({ status: 'PRESENT' }));
    await waitFor(() => expect(state.checkIn).toHaveBeenCalledTimes(1));
  });

  it('reuses one idempotency key when retrying the same intent, then issues a new one after success', async () => {
    state.checkIn.mockRejectedValueOnce(new ApiError({ title: 'Network', status: 0, code: 'NETWORK_ERROR' } as never, null));
    render(<AttendanceActionPanel record={record()} />);
    await userEvent.click(screen.getByTestId('attendance-check-in-button'));
    await screen.findByTestId('attendance-error');

    // Retry the same intent: the panel clears the failure and the user re-taps the action, which
    // must reuse the original key so a request that actually succeeded is not duplicated.
    await userEvent.click(screen.getByRole('button', { name: /retry/i }));
    await userEvent.click(screen.getByTestId('attendance-check-in-button'));
    await waitFor(() => expect(state.checkIn).toHaveBeenCalledTimes(2));
    const first = state.checkIn.mock.calls[0][0].idempotencyKey;
    const second = state.checkIn.mock.calls[1][0].idempotencyKey;
    expect(second).toBe(first);

    // After a confirmed success the next intent gets a fresh key.
    await screen.findByTestId('attendance-success');
    await userEvent.click(screen.getByTestId('attendance-check-in-button'));
    await waitFor(() => expect(state.checkIn).toHaveBeenCalledTimes(3));
    expect(state.checkIn.mock.calls[2][0].idempotencyKey).not.toBe(first);
  });

  it('ends a break through the server and confirms on success', async () => {
    render(
      <AttendanceActionPanel
        record={record({
          status: 'PRESENT',
          next_allowed_action: 'END_BREAK',
          open_break: { id: 'b1', attendance_record_id: 'att-1', break_type_id: 'bt1', started_at: '2026-09-25T13:00:00Z', ended_at: null, duration_seconds: null, is_paid: false, close_reason: null }
        })}
      />
    );
    await userEvent.click(screen.getByTestId('attendance-end-break-button'));
    await waitFor(() => expect(state.endBreak).toHaveBeenCalledTimes(1));
    expect(await screen.findByTestId('attendance-success')).toBeInTheDocument();
  });

  it('requires a break type from the server list before starting a break', async () => {
    state.breakTypes = {
      items: [
        { id: 'bt1', code: 'LUNCH', name: 'Lunch', is_paid: false, max_minutes: 60, requires_approval: false, counts_toward_max_per_day: true, is_active: true }
      ]
    };
    render(<AttendanceActionPanel record={record({ status: 'PRESENT', next_allowed_action: 'START_BREAK' })} />);
    await userEvent.click(screen.getByTestId('attendance-start-break-button'));
    const dialog = await screen.findByRole('dialog');
    await userEvent.selectOptions(screen.getByLabelText(/break type/i), 'bt1');
    await userEvent.click(within(dialog).getByRole('button', { name: /^start break$/i }));
    await waitFor(() => expect(state.startBreak).toHaveBeenCalledTimes(1));
    expect(state.startBreak.mock.calls[0][0]).toMatchObject({ breakTypeId: 'bt1' });
  });
});