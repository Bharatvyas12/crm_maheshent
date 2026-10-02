import type { ProblemDetails } from './types';

/**
 * Presentation map for server conditions (docs/07_UI_SPEC.md section 11 and
 * docs/03_API_CONTRACT.md section 19). Screens render from the stable machine `code`, never by
 * string-matching the human-readable detail.
 */
export interface ProblemPresentation {
  /** Short headline shown to the user. */
  title: string;
  /** What the user should do next. */
  nextStep?: string;
  /** Conflict handling category (docs/07 section 5.4). */
  kind: 'error' | 'conflict' | 'permission' | 'notfound' | 'rate-limit' | 'validation' | 'offline';
}

const MAP: Record<string, ProblemPresentation> = {
  AUTHENTICATION_REQUIRED: { title: 'Please sign in again.', kind: 'permission', nextStep: 'Redirecting to login.' },
  SESSION_EXPIRED: { title: 'Your session expired.', kind: 'permission', nextStep: 'Redirecting to login.' },
  INVALID_CREDENTIALS: { title: 'Incorrect username or password.', kind: 'error', nextStep: 'Please check your username and password for typos (e.g. ChangeMe123!).' },
  ACCOUNT_LOCKED: { title: 'This account is temporarily locked.', kind: 'error', nextStep: 'Try again later or contact the admin.' },
  ACCOUNT_DISABLED: { title: 'This account is disabled.', kind: 'error', nextStep: 'Contact the admin.' },
  CSRF_INVALID: { title: 'Your session token is no longer valid.', kind: 'error', nextStep: 'Refresh the page and try again.' },
  PERMISSION_DENIED: { title: 'You do not have permission for this action.', kind: 'permission' },
  RESOURCE_NOT_FOUND: { title: 'This record is not available.', kind: 'notfound' },
  VALIDATION_ERROR: { title: 'Please correct the highlighted fields.', kind: 'validation' },
  RULE_VIOLATION: { title: 'This action is not allowed right now.', kind: 'error' },
  STATE_CONFLICT: { title: 'The record changed since you opened it.', kind: 'conflict', nextStep: 'Refresh and continue.' },
  CONFLICT_DUPLICATE: { title: 'This record already exists.', kind: 'conflict' },
  CLAIM_ALREADY_TAKEN: { title: 'Another employee claimed this order.', kind: 'conflict', nextStep: 'The order and available list were refreshed.' },
  IDEMPOTENCY_CONFLICT: { title: 'This request conflicts with an earlier one.', kind: 'error', nextStep: 'Refresh the page before trying again.' },
  RATE_LIMITED: { title: 'Too many attempts.', kind: 'rate-limit', nextStep: 'Wait and try again.' },
  FILE_TOO_LARGE: { title: 'This file is too large.', kind: 'error', nextStep: 'Choose a smaller file.' },
  UNSUPPORTED_FILE_TYPE: { title: 'This file type is not supported.', kind: 'error' },
  STORAGE_UNAVAILABLE: { title: 'File storage is temporarily unavailable.', kind: 'error', nextStep: 'Try again shortly.' },
  DEPENDENCY_UNAVAILABLE: { title: 'A service is temporarily unavailable.', kind: 'error', nextStep: 'Retry; contact support if it persists.' },
  INTERNAL_ERROR: { title: 'Something went wrong.', kind: 'error', nextStep: 'Retry; quote the request id if you contact support.' },
  PERIOD_LOCKED: { title: 'This period is locked.', kind: 'conflict', nextStep: 'Use an adjustment instead of changing locked history.' },
  NETWORK_ERROR: { title: 'We could not reach the server.', kind: 'offline', nextStep: 'Check your connection and try again.' }
};

/**
 * Rule-code specific guidance, e.g. attendance verification failures
 * (docs/07_UI_SPEC.md section 11). These codes arrive as `rule_code` or `failure_code`.
 */
const RULE_MAP: Record<string, ProblemPresentation> = {
  LOCATION_UNAVAILABLE: { title: 'We could not read your location.', kind: 'error', nextStep: 'Enable location permission, then retry.' },
  LOCATION_STALE: { title: 'Your location reading was too old.', kind: 'error', nextStep: 'Retry to get a fresh reading.' },
  ACCURACY_EXCEEDS_LIMIT: { title: 'Your location accuracy is not good enough.', kind: 'error', nextStep: 'Move to a spot with a better signal and retry.' },
  OUTSIDE_GEOFENCE: { title: 'You are outside the allowed distance from the shop.', kind: 'error', nextStep: 'Move closer and retry.' },
  QR_EXPIRED: { title: 'This code has expired.', kind: 'error', nextStep: 'Refresh the shop display and scan the current code.' },
  QR_REPLAYED: { title: 'This code was already used.', kind: 'error', nextStep: 'Scan the current code on the shop display.' },
  QR_INVALID: { title: 'This is not a valid shop code.', kind: 'error', nextStep: 'Scan the code shown on the shop display.' },
  METHOD_NOT_ALLOWED: { title: 'Attendance verification is not configured yet.', kind: 'error', nextStep: 'Contact the admin.' },
  ORDER_PROOF_REQUIRED: { title: 'Delivery proof is required.', kind: 'error', nextStep: 'Upload the missing proof.' },
  ORDER_INVALID_TRANSITION: { title: 'That status change is not allowed from here.', kind: 'conflict', nextStep: 'Refresh the order to see the allowed next step.' },
  LEAVE_OVERLAP: { title: 'You already have leave covering these dates.', kind: 'error', nextStep: 'Adjust the dates.' },
  LEAVE_BALANCE_INSUFFICIENT: { title: 'You do not have enough leave balance.', kind: 'error', nextStep: 'Adjust the dates or contact the admin.' },
  TASK_EVIDENCE_REQUIRED: { title: 'Add a description or evidence before submitting.', kind: 'validation' },
  ADVANCE_LIMIT_EXCEEDED: { title: 'This exceeds the allowed outstanding advance.', kind: 'error', nextStep: 'Reduce the amount.' },
  BREAK_WITHOUT_SESSION: { title: 'Start work before taking a break.', kind: 'conflict', nextStep: 'Check in first.' },
  SELF_APPROVAL_NOT_ALLOWED: { title: 'You cannot approve your own request.', kind: 'permission' },
  ACTIVE_CLAIM_LIMIT_REACHED: { title: 'You have reached your active order limit.', kind: 'error', nextStep: 'Complete or release an order first.' }
};

export function describeProblem(problem: ProblemDetails | null | undefined): ProblemPresentation {
  if (!problem) {
    return { title: 'Something went wrong.', kind: 'error', nextStep: 'Retry.' };
  }
  const ruleCode = problem.rule_code ?? problem.code;
  if (ruleCode && RULE_MAP[ruleCode]) {
    return RULE_MAP[ruleCode];
  }
  if (problem.code && MAP[problem.code]) {
    return MAP[problem.code];
  }
  return {
    title: problem.title ?? 'Something went wrong.',
    kind: 'error',
    nextStep: problem.detail ?? undefined
  };
}

/** Field-keyed validation errors, ready to feed into a form. */
export function fieldErrors(problem: ProblemDetails | null | undefined): Record<string, string> {
  const out: Record<string, string> = {};
  if (!problem?.errors) return out;
  for (const err of problem.errors) {
    if (!out[err.field]) out[err.field] = err.message;
  }
  return out;
}