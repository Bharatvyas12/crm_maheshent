import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiFetch, buildQuery } from './api-client';

interface Call {
  url: string;
  method: string;
  headers: Record<string, string>;
  body?: string;
}

let calls: Call[] = [];

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-Id': 'req-test-1', ...headers }
  });
}

function problemResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/problem+json', 'X-Request-Id': 'req-conflict-9' }
  });
}

beforeEach(() => {
  calls = [];
  vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
    const headers: Record<string, string> = {};
    for (const [key, value] of Object.entries((init.headers as Record<string, string>) ?? {})) headers[key] = String(value);
    calls.push({ url: String(url), method: init.method ?? 'GET', headers, body: init.body as string | undefined });
    return jsonResponse({ ok: true });
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('buildQuery', () => {
  it('drops empty values and repeats arrays', () => {
    expect(buildQuery({ a: 1, b: '', c: undefined, d: null, e: ['x', 'y'] })).toBe('?a=1&e=x&e=y');
    expect(buildQuery({})).toBe('');
  });
});

describe('apiFetch', () => {
  it('sends the documented Idempotency-Key header for keyed mutations', async () => {
    await apiFetch('/orders/1/claim', { method: 'POST', body: {}, idempotencyKey: 'key-123' });
    expect(calls[0].headers['Idempotency-Key']).toBe('key-123');
  });

  it('reuses the same key when a request is retried after a network error', async () => {
    let attempt = 0;
    vi.stubGlobal('fetch', async (_url: string, init: RequestInit) => {
      attempt += 1;
      const headers: Record<string, string> = {};
      for (const [key, value] of Object.entries((init.headers as Record<string, string>) ?? {})) headers[key] = String(value);
      calls.push({ url: String(_url), method: init.method ?? 'GET', headers });
      if (attempt === 1) throw new TypeError('network down');
      return jsonResponse({ ok: true });
    });

    const key = 'stable-intent-key';
    await expect(apiFetch('/attendance/check-in', { method: 'POST', body: {}, idempotencyKey: key })).rejects.toBeInstanceOf(ApiError);
    await apiFetch('/attendance/check-in', { method: 'POST', body: {}, idempotencyKey: key });
    expect(calls).toHaveLength(2);
    expect(calls[0].headers['Idempotency-Key']).toBe(key);
    expect(calls[1].headers['Idempotency-Key']).toBe(key);
  });

  it('never sends a body on GET', async () => {
    await apiFetch('/orders', { method: 'GET', query: { status: 'BROADCASTED' } });
    expect(calls[0].body).toBeUndefined();
    expect(calls[0].url).toContain('/orders?status=BROADCASTED');
  });

  it('does not add a CSRF header to a GET', async () => {
    await apiFetch('/orders');
    expect(calls[0].headers['X-CSRF-Token']).toBeUndefined();
  });

  it('surfaces a lost claim as a typed ApiError carrying the winning claim', async () => {
    vi.stubGlobal('fetch', async () =>
      problemResponse(
        {
          title: 'Order already claimed',
          status: 409,
          code: 'CLAIM_ALREADY_TAKEN',
          detail: 'Another employee holds this order.',
          current_status: 'CLAIMED',
          claimed_at: '2026-09-25T10:00:00Z',
          claimed_by: { id: 'e2', full_name: 'Ravi' }
        },
        409
      )
    );

    const error = (await apiFetch('/orders/1/claim', { method: 'POST', body: {}, idempotencyKey: 'k' }).catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe('CLAIM_ALREADY_TAKEN');
    expect(error.requestId).toBe('req-conflict-9');
    expect(error.problem.current_status).toBe('CLAIMED');
    expect(error.problem.claimed_at).toBe('2026-09-25T10:00:00Z');
  });

  it('keeps validation field errors from the problem body', async () => {
    vi.stubGlobal('fetch', async () =>
      problemResponse(
        {
          title: 'Request validation failed',
          status: 422,
          code: 'VALIDATION_ERROR',
          errors: [{ field: 'latitude', code: 'OUT_OF_RANGE', message: 'Latitude must be between -90 and 90.' }]
        },
        422
      )
    );
    const error = (await apiFetch('/attendance/check-in', { method: 'POST', body: {}, idempotencyKey: 'k' }).catch((e: unknown) => e)) as ApiError;
    expect(error.problem.errors?.[0].field).toBe('latitude');
  });

  it('turns an unreachable server into a NETWORK_ERROR problem', async () => {
    vi.stubGlobal('fetch', async () => {
      throw new TypeError('Failed to fetch');
    });
    const error = (await apiFetch('/orders', { method: 'GET' }).catch((e: unknown) => e)) as ApiError;
    expect(error.code).toBe('NETWORK_ERROR');
    expect(error.status).toBe(0);
  });

  it('classifies authorization failures for the UI', async () => {
    vi.stubGlobal('fetch', async () => problemResponse({ title: 'Forbidden', status: 403, code: 'PERMISSION_DENIED' }, 403));
    const error = (await apiFetch('/audit-logs', { method: 'GET' }).catch((e: unknown) => e)) as ApiError;
    expect(error.isPermissionDenied).toBe(true);
  });

  it('returns undefined for 204 without parsing a body', async () => {
    vi.stubGlobal('fetch', async () => new Response(null, { status: 204 }));
    await expect(apiFetch('/notifications/1/read', { method: 'POST' })).resolves.toBeUndefined();
  });
});