import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api-client';
import { applyLeave } from './leaves/api';
import { createComplaint } from './complaints/api';
import { startAssignment, submitAssignment } from './tasks/api';
import { addOrderAttachment, claimOrder, releaseOrder, updateOrderStatus } from './orders/api';

/**
 * Contract conformance: the frontend must call the paths, methods and idempotency requirements
 * fixed by docs/03_API_CONTRACT.md. These tests fail if a screen starts inventing endpoints.
 */

const API = '/api/v1';

interface Call {
  path: string;
  method: string;
  headers: Record<string, string>;
  body?: unknown;
}

let calls: Call[] = [];

function respond(body: unknown, status = 200): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-Id': 'req-1' }
  });
}

beforeEach(() => {
  calls = [];
  vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
    const headers: Record<string, string> = {};
    for (const [key, value] of Object.entries((init.headers as Record<string, string>) ?? {})) headers[key] = String(value);
    calls.push({
      path: String(url),
      method: init.method ?? 'GET',
      headers,
      body: init.body ? JSON.parse(String(init.body)) : undefined
    });
    return respond({ id: 'x' });
  });
});

afterEach(() => vi.unstubAllGlobals());

describe('documented endpoint paths', () => {
  it('claims through POST /orders/{id}/claim with a required Idempotency-Key (section 9.1, 18)', async () => {
    await claimOrder('order-1', 'idem-claim');
    expect(calls[0].method).toBe('POST');
    expect(calls[0].path).toBe(`${API}/orders/order-1/claim`);
    expect(calls[0].headers['Idempotency-Key']).toBe('idem-claim');
  });

  it('releases with a reason so the order can return to the pool', async () => {
    await releaseOrder('order-1', 'Could not deliver');
    expect(calls[0].path).toBe(`${API}/orders/order-1/release`);
    expect(calls[0].body).toEqual({ reason: 'Could not deliver' });
  });

  it('posts lifecycle transitions and proof ids to POST /orders/{id}/status', async () => {
    await updateOrderStatus('order-1', { to_status: 'PACKED', proof_file_ids: ['file-1'], reason: 'Packed' });
    expect(calls[0].path).toBe(`${API}/orders/order-1/status`);
    expect(calls[0].body).toEqual({ to_status: 'PACKED', proof_file_ids: ['file-1'], reason: 'Packed' });
  });

  it('uploads order proof through POST /orders/{id}/attachments with a documented purpose', async () => {
    await addOrderAttachment('order-1', {
      file_id: 'file-1',
      purpose: 'DELIVERY_PROOF',
      customer_confirmed: true,
      customer_confirmation_method: 'SIGNATURE'
    });
    expect(calls[0].path).toBe(`${API}/orders/order-1/attachments`);
    expect(calls[0].body).toMatchObject({ purpose: 'DELIVERY_PROOF', customer_confirmed: true });
  });

  it('starts and submits task assignments on the documented sub-resources', async () => {
    await startAssignment('assign-1');
    expect(calls[0].path).toBe(`${API}/task-assignments/assign-1/start`);
    await submitAssignment('assign-1', { description: 'done', attachment_file_ids: ['file-2'] }, 'idem-submit');
    expect(calls[1].path).toBe(`${API}/task-assignments/assign-1/submissions`);
    expect(calls[1].headers['Idempotency-Key']).toBe('idem-submit');
  });

  it('applies leave at POST /leaves with a required Idempotency-Key', async () => {
    await applyLeave(
      { leave_type_id: 'lt-1', start_date: '2026-10-01', end_date: '2026-10-02', reason: 'Family' },
      'idem-leave'
    );
    expect(calls[0].path).toBe(`${API}/leaves`);
    expect(calls[0].headers['Idempotency-Key']).toBe('idem-leave');
  });

  it('creates a complaint at POST /complaints with the documented body', async () => {
    await createComplaint({ category_id: 'cat-1', title: 'AC broken', description: 'No cooling since Monday' });
    expect(calls[0].path).toBe(`${API}/complaints`);
    expect(calls[0].body).toEqual({ category_id: 'cat-1', title: 'AC broken', description: 'No cooling since Monday' });
  });

  it('does not invent a per-run salary-records path (section 11.3 uses /salary-records)', async () => {
    const { listSalaryRecords } = await import('./ledger/api');
    await listSalaryRecords({ payroll_run_id: 'run-1' });
    expect(calls[0].path).toBe(`${API}/salary-records?payroll_run_id=run-1`);
  });
});

describe('conflict semantics for the claim edge', () => {
  it('raises a typed CLAIM_ALREADY_TAKEN error the UI renders as a conflict panel', async () => {
    vi.stubGlobal('fetch', async () =>
      new Response(
        JSON.stringify({
          title: 'Order already claimed',
          status: 409,
          code: 'CLAIM_ALREADY_TAKEN',
          current_status: 'CLAIMED',
          claimed_at: '2026-09-25T10:00:00Z',
          claimed_by: { id: 'e2', full_name: 'Ravi' }
        }),
        { status: 409, headers: { 'Content-Type': 'application/problem+json' } }
      )
    );
    const error = (await claimOrder('order-1', 'idem').catch((e: unknown) => e)) as ApiError;
    expect(error.code).toBe('CLAIM_ALREADY_TAKEN');
  });
});