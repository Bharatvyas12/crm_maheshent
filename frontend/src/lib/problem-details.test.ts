import { describe, expect, it } from 'vitest';
import { describeProblem, fieldErrors } from './problem-details';
import type { ProblemDetails } from './types';

function problem(partial: Partial<ProblemDetails>): ProblemDetails {
  return { title: 'x', status: 400, code: 'INTERNAL_ERROR', ...partial };
}

describe('problem-details presentation', () => {
  it('maps the order-claim conflict to the conflict kind (docs/07 section 5.4)', () => {
    const view = describeProblem(problem({ code: 'CLAIM_ALREADY_TAKEN', status: 409 }));
    expect(view.kind).toBe('conflict');
    expect(view.title).toMatch(/another employee/i);
  });

  it('classifies every documented conflict code as a conflict', () => {
    for (const code of ['CLAIM_ALREADY_TAKEN', 'STATE_CONFLICT', 'CONFLICT_DUPLICATE', 'PERIOD_LOCKED']) {
      expect(describeProblem(problem({ code, status: 409 })).kind, code).toBe('conflict');
    }
  });

  it('offers a recovery step where the spec requires one', () => {
    for (const code of ['CLAIM_ALREADY_TAKEN', 'STATE_CONFLICT', 'PERIOD_LOCKED']) {
      expect(describeProblem(problem({ code, status: 409 })).nextStep, code).toBeTruthy();
    }
  });

  it('explains attendance verification failures in plain language', () => {
    expect(describeProblem(problem({ code: 'RULE_VIOLATION', rule_code: 'OUTSIDE_GEOFENCE', status: 422 })).title).toMatch(
      /outside the allowed distance/i
    );
    expect(describeProblem(problem({ code: 'RULE_VIOLATION', rule_code: 'ACCURACY_EXCEEDS_LIMIT' })).title).toMatch(/accuracy/i);
    expect(describeProblem(problem({ code: 'RULE_VIOLATION', rule_code: 'QR_EXPIRED', status: 422 })).title).toMatch(/expired/i);
    expect(describeProblem(problem({ code: 'RULE_VIOLATION', rule_code: 'QR_REPLAYED' })).title).toMatch(/already used/i);
  });

  it('prefers rule_code over the generic code', () => {
    const view = describeProblem(problem({ code: 'RULE_VIOLATION', rule_code: 'LEAVE_BALANCE_INSUFFICIENT' }));
    expect(view.title).toMatch(/enough leave balance/i);
  });

  it('treats a permission denial and a hidden record distinctly', () => {
    expect(describeProblem(problem({ code: 'PERMISSION_DENIED', status: 403 })).kind).toBe('permission');
    expect(describeProblem(problem({ code: 'RESOURCE_NOT_FOUND', status: 404 })).kind).toBe('notfound');
  });

  it('rate limiting and network failures are recoverable', () => {
    expect(describeProblem(problem({ code: 'RATE_LIMITED', status: 429 })).kind).toBe('rate-limit');
    expect(describeProblem(problem({ code: 'NETWORK_ERROR', status: 0 })).kind).toBe('offline');
  });

  it('never auto-retries an idempotency conflict', () => {
    const view = describeProblem(problem({ code: 'IDEMPOTENCY_CONFLICT', status: 409 }));
    expect(view.nextStep).toMatch(/refresh/i);
  });

  it('extracts field errors for form display', () => {
    const errors = fieldErrors(
      problem({
        code: 'VALIDATION_ERROR',
        status: 422,
        errors: [
          { field: 'latitude', code: 'OUT_OF_RANGE', message: 'Latitude must be between -90 and 90.' },
          { field: 'latitude', code: 'REQUIRED', message: 'duplicate, ignored' }
        ]
      })
    );
    expect(errors.latitude).toBe('Latitude must be between -90 and 90.');
    expect(Object.keys(errors)).toEqual(['latitude']);
  });

  it('degrades gracefully with no problem body', () => {
    expect(describeProblem(null).title).toBeTruthy();
    expect(fieldErrors(undefined)).toEqual({});
  });
});