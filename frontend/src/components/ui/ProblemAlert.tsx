'use client';

import { ApiError } from '@/lib/api-client';
import { describeProblem } from '@/lib/problem-details';
import { Alert } from './Alert';

const TONE_BY_KIND = {
  error: 'danger',
  conflict: 'warning',
  permission: 'warning',
  notfound: 'warning',
  'rate-limit': 'warning',
  validation: 'danger',
  offline: 'warning'
} as const;

/**
 * Single place that renders problem-details consistently (docs/07_UI_SPEC.md section 13).
 * Tests can assert on the server `code` via `data-code` without depending on copy.
 */
export function ProblemAlert({ error, onRetry, testId = 'problem-alert' }: { error: unknown; onRetry?: () => void; testId?: string }) {
  const apiError = error instanceof ApiError ? error : null;
  const presentation = describeProblem(apiError?.problem);
  const fieldErrors = apiError?.problem.errors ?? [];
  const code = apiError?.code ?? 'UNKNOWN';

  return (
    <Alert
      tone={TONE_BY_KIND[presentation.kind]}
      title={presentation.title}
      nextStep={presentation.nextStep}
      testId={testId}
      actions={
        onRetry && presentation.kind !== 'permission' && presentation.kind !== 'notfound' ? (
          <button type="button" onClick={onRetry} className="rounded border border-current px-3 py-1 text-xs font-medium">
            Retry
          </button>
        ) : null
      }
    >
      <div data-code={code}>
        {apiError?.problem.detail && apiError.problem.detail !== presentation.title ? <p>{apiError.problem.detail}</p> : null}
        {fieldErrors.length > 0 ? (
          <ul className="mt-1 list-inside list-disc">
            {fieldErrors.map((err) => (
              <li key={`${err.field}-${err.code}`}>
                <span className="font-medium">{err.field}</span>: {err.message}
              </li>
            ))}
          </ul>
        ) : null}
        {apiError?.requestId ? (
          <details className="mt-2">
            <summary className="cursor-pointer text-xs">Technical details</summary>
            <p className="mt-1 font-mono text-xs">
              {code} - request {apiError.requestId}
            </p>
          </details>
        ) : null}
      </div>
    </Alert>
  );
}