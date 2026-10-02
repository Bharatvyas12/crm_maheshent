import { describe, expect, it } from 'vitest';
import { renderHook } from '@testing-library/react';
import { newIdempotencyKey, useIdempotency } from './idempotency';

describe('idempotency keys (docs/07 section 5.3)', () => {
  it('generates a distinct key for each new intent', () => {
    const keys = new Set(Array.from({ length: 50 }, () => newIdempotencyKey()));
    expect(keys.size).toBe(50);
  });

  it('reuses the same key across retries of one intent', () => {
    const { result } = renderHook(() => useIdempotency());
    const first = result.current.key();
    const retry = result.current.key();
    expect(retry).toBe(first);
  });

  it('issues a fresh key after the intent completes', () => {
    const { result } = renderHook(() => useIdempotency());
    const first = result.current.key();
    result.current.reset();
    expect(result.current.key()).not.toBe(first);
  });

  it('keeps the key stable across a re-render (not regenerated per render)', () => {
    const { result, rerender } = renderHook(() => useIdempotency());
    const first = result.current.key();
    rerender();
    rerender();
    expect(result.current.key()).toBe(first);
  });
});