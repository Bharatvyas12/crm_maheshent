import type { DashboardSummary } from './types';

/**
 * Defensive reader for `GET /reports/dashboard-summary`.
 *
 * The API contract fixes the ENDPOINT but not the field names of the summary block, so the UI
 * reads a small set of documented-style candidate keys and renders nothing when the server does
 * not provide the value. It never computes the number itself (docs/07_UI_SPEC.md section 7.1).
 */
export function pickNumber(source: unknown, keys: string[]): number | null {
  if (!source || typeof source !== 'object') return null;
  const record = source as Record<string, unknown>;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value))) return Number(value);
  }
  // Some summaries nest the counters under a sub-object.
  for (const nested of Object.values(record)) {
    if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
      const found = pickNumber(nested, keys);
      if (found !== null) return found;
    }
  }
  return null;
}

export function pickString(source: unknown, keys: string[]): string | null {
  if (!source || typeof source !== 'object') return null;
  const record = source as Record<string, unknown>;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string' && value !== '') return value;
  }
  return null;
}

export function summaryHasData(summary: DashboardSummary | undefined): boolean {
  return Boolean(summary && Object.keys(summary).length > 0);
}