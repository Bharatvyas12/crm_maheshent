'use client';

import type { ProblemDetails } from './types';
import { newIdempotencyKey } from './idempotency';

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, '') || '/api/v1';

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly problem: ProblemDetails;
  readonly requestId: string | null;

  constructor(problem: ProblemDetails, requestId: string | null) {
    super(problem.detail || problem.title || problem.code || 'Request failed');
    this.name = 'ApiError';
    this.problem = problem;
    this.status = problem.status ?? 0;
    this.code = problem.code ?? 'INTERNAL_ERROR';
    this.requestId = requestId ?? problem.request_id ?? null;
  }

  get isUnauthenticated(): boolean {
    return this.status === 401 || this.code === 'AUTHENTICATION_REQUIRED' || this.code === 'SESSION_EXPIRED';
  }

  get isPermissionDenied(): boolean {
    return this.status === 403 || this.code === 'PERMISSION_DENIED';
  }

  get isNotFound(): boolean {
    return this.status === 404 || this.code === 'RESOURCE_NOT_FOUND';
  }
}

export type QueryValue = string | number | boolean | null | undefined | Array<string | number>;

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  /** JSON body. Ignored for multipart requests. */
  body?: unknown;
  query?: Record<string, QueryValue>;
  /** Required for operations in docs/03_API_CONTRACT.md section 18. */
  idempotencyKey?: string;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  /** Set for FormData uploads; do not set Content-Type manually. */
  formData?: FormData;
}

export function buildQuery(query?: Record<string, QueryValue>): string {
  if (!query) return '';
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue;
    if (Array.isArray(value)) {
      for (const item of value) params.append(key, String(item));
    } else {
      params.append(key, String(value));
    }
  }
  const encoded = params.toString();
  return encoded ? `?${encoded}` : '';
}

/** Read the non-HttpOnly `csrf_token` cookie for the double-submit CSRF scheme. */
function readCsrfToken(): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.split('; ').find((row) => row.startsWith('csrf_token='));
  return match ? decodeURIComponent(match.slice('csrf_token='.length)) : null;
}

const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

async function parseProblem(response: Response, requestId: string | null): Promise<ApiError> {
  let problem: ProblemDetails | null = null;
  try {
    problem = (await response.json()) as ProblemDetails;
  } catch {
    problem = null;
  }
  if (!problem || typeof problem !== 'object') {
    problem = {
      title: response.statusText || 'Request failed',
      status: response.status,
      code: response.status === 401 ? 'AUTHENTICATION_REQUIRED' : 'INTERNAL_ERROR'
    };
  }
  if (!problem.status) problem.status = response.status;
  if (!problem.code) {
    problem.code = response.status === 403 ? 'PERMISSION_DENIED' : response.status === 404 ? 'RESOURCE_NOT_FOUND' : 'INTERNAL_ERROR';
  }
  return new ApiError(problem, requestId);
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? 'GET';
  const url = `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}${buildQuery(options.query)}`;

  const headers: Record<string, string> = { Accept: 'application/json', ...options.headers };

  if (UNSAFE_METHODS.has(method)) {
    const csrf = readCsrfToken();
    if (csrf) headers['X-CSRF-Token'] = csrf;
  }
  if (options.idempotencyKey) {
    headers['Idempotency-Key'] = options.idempotencyKey;
  } else if (options.formData) {
    headers['Idempotency-Key'] = newIdempotencyKey();
  }

  let body: BodyInit | undefined;
  if (options.formData) {
    body = options.formData;
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(options.body);
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body,
      credentials: 'include',
      signal: options.signal,
      cache: 'no-store'
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError(
      {
        title: 'Network error',
        status: 0,
        code: 'NETWORK_ERROR',
        detail: 'We could not reach the server.'
      },
      null
    );
  }

  const requestId = response.headers.get('X-Request-Id');

  if (response.status === 204) {
    return undefined as T;
  }

  if (!response.ok) {
    const error = await parseProblem(response, requestId);
    if (response.status === 429) {
      const retryAfter = response.headers.get('Retry-After');
      if (retryAfter) error.problem.retry_after_seconds = Number(retryAfter) || undefined;
    }
    throw error;
  }

  const contentType = response.headers.get('Content-Type') ?? '';
  if (contentType.includes('application/json')) {
    return (await response.json()) as T;
  }
  return (await response.text()) as unknown as T;
}

export const api = {
  get: <T>(path: string, query?: Record<string, QueryValue>, signal?: AbortSignal) =>
    apiFetch<T>(path, { method: 'GET', query, signal }),
  post: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    apiFetch<T>(path, { ...options, method: 'POST', body }),
  patch: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    apiFetch<T>(path, { ...options, method: 'PATCH', body }),
  put: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    apiFetch<T>(path, { ...options, method: 'PUT', body }),
  delete: <T>(path: string, options?: Omit<RequestOptions, 'method'>) =>
    apiFetch<T>(path, { ...options, method: 'DELETE' })
};