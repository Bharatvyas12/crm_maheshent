'use client';

import { useCallback, useRef } from 'react';

/**
 * Idempotency-Key handling (docs/07_UI_SPEC.md section 5.3, docs/01_ARCHITECTURE.md section 13.6).
 *
 * The key is generated per user intent, reused on retry of the same intent, and regenerated for
 * a genuinely new intent. Operations that require a key are listed in
 * docs/03_API_CONTRACT.md section 18.
 */
export function newIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  // Fallback for environments without crypto.randomUUID (should not happen in supported browsers).
  return `idem-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export interface IdempotencyHandle {
  /** Current key for the in-flight intent. */
  key: () => string;
  /** Call after a success or a definitive (non-retryable) failure to start a fresh intent. */
  reset: () => void;
}

/**
 * Returns a stable idempotency key for the lifetime of one user intent. Retries of the same
 * intent reuse it; call `reset()` when the user starts a new intent (or after success).
 */
export function useIdempotency(): IdempotencyHandle {
  const keyRef = useRef<string>(newIdempotencyKey());

  const key = useCallback(() => {
    if (!keyRef.current) {
      keyRef.current = newIdempotencyKey();
    }
    return keyRef.current;
  }, []);

  const reset = useCallback(() => {
    keyRef.current = newIdempotencyKey();
  }, []);

  return { key, reset };
}