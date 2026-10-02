'use client';

import { humanize } from '@/lib/format';

/** Render a JSON value compactly for an audit/diff view. */
function asText(value: unknown): string {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'string') return value;
  if (typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value);
}

function normalise(value: unknown): string {
  return JSON.stringify(value ?? null);
}

/**
 * Before/after diff for audit records (docs/07_UI_SPEC.md section 7.5). Only changed keys are
 * highlighted; unchanged keys are still shown so the reviewer sees the full snapshot.
 */
export function SelectiveFields({
  before,
  after,
  testId = 'audit-diff'
}: {
  before: Record<string, unknown> | null | undefined;
  after: Record<string, unknown> | null | undefined;
  testId?: string;
}) {
  const keys = Array.from(new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})])).sort();

  if (keys.length === 0) {
    return <p className="text-sm text-content-muted">This record has no before/after payload.</p>;
  }

  return (
    <div data-testid={testId} className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-content-muted">Changed values</p>
      <ul className="space-y-2">
        {keys.map((key) => {
          const oldValue = before?.[key];
          const newValue = after?.[key];
          const changed = normalise(oldValue) !== normalise(newValue);
          return (
            <li key={key} className={changed ? 'rounded-md border border-warning/40 bg-warning-soft p-2' : 'rounded-md border border-surface-border p-2'}>
              <p className="text-xs font-medium">{humanize(key)}</p>
              {changed ? (
                <div className="mt-1 grid grid-cols-1 gap-1 text-xs sm:grid-cols-2">
                  <div>
                    <p className="text-content-muted">Before</p>
                    <pre className="whitespace-pre-wrap break-words font-mono">{asText(oldValue)}</pre>
                  </div>
                  <div>
                    <p className="text-content-muted">After</p>
                    <pre className="whitespace-pre-wrap break-words font-mono">{asText(newValue)}</pre>
                  </div>
                </div>
              ) : (
                <pre className="mt-1 whitespace-pre-wrap break-words font-mono text-xs text-content-muted">{asText(newValue)}</pre>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}