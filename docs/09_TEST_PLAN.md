# 09 - Test Plan

| Field | Value |
| --- | --- |
| Document owner | Agent 1 - Architect / Tech Lead |
| Status | Baseline (implementation-ready) |
| Version | 1.0 |
| Source-of-truth rank | 10 |
| Applies to | Agent 2 (backend tests), Agent 3 (frontend tests), Agent 4 (domain verification), Agent 5 (QA, security, integration) |

This document defines the test strategy, the required test categories, the mandatory cases
(including every edge case and reconciliation rule from the other documents), the tooling, and the
quality gates a module must pass before it is considered done.

A module is not complete because code exists. Per `AGENTS.md` section 7 it is complete when
implementation, API documentation, authorization, validation, edge cases, passing tests, error
handling, audit behavior and UI integration exist and no known critical defect remains.

---

## 1. Scope and Objectives

Objectives, in priority order:

1. Prove the backend is authoritative (no client-supplied value can change a protected outcome).
2. Prove invariant safety under concurrency (especially order claiming, duplicate attendance
   events, balance updates and financial writes).
3. Prove authorization holds on every endpoint, including negative cases and IDOR attempts.
4. Prove business-rule calculations (work hours, day classification, overtime, leave balances,
   salary, advances) are correct, configurable and reproducible.
5. Prove reports reconcile with the database.
6. Prove failure paths degrade safely (network, storage, GPS, QR, locked periods).
7. Prove the employee and admin experiences work on the required devices and are accessible.

Out of scope for automated testing at MVP: cross-browser visual regression on every browser,
load testing beyond the small-business scale, and penetration testing by an external party
(recommended but not an MVP deliverable).

---

## 2. Test Layers

| Layer | What it covers | Runs in | Owner |
| --- | --- | --- | --- |
| L1 Unit | Pure functions and rules: settings resolution, work-hour math, day classification, overtime, salary components, ledger sign rules, state machines, permission checks, validators, redaction, money/duration helpers | Fast, no database | Agent 2 |
| L2 Integration (API + DB) | Endpoint behavior against a real PostgreSQL: transactions, constraints, status codes, error bodies, idempotency, audit records, outbox events | Testcontainers/real DB | Agent 2 |
| L3 Database integrity | Constraints, partial/exclusion indexes, triggers (salary immutability), append-only enforcement, generated columns | Real DB | Agent 2, verified by Agent 5 |
| L4 Concurrency | Races: order claiming, duplicate attendance, concurrent approvals, concurrent balance changes, concurrent financial writes | Real DB, parallel connections | Agent 2, re-verified by Agent 5 |
| L5 Security | Authentication, authorization, IDOR, privilege escalation, injection, XSS, CSRF, token/session abuse, file security, QR replay, forged payloads | API level | Agent 2, Agent 5 |
| L6 End-to-end (E2E) | Complete workflows through the UI: login, attendance, tasks, orders, leave, complaints, payroll visibility, reports | Browser (Playwright) | Agent 3, Agent 5 |
| L7 Report validation | Reconciliation rules RC-1..RC-18 against database truth | API + SQL | Agent 5 |
| L8 Migration | Schema upgrades from the previous revision, extension creation, constraint additions, backfills, rollback behavior | Real DB | Agent 2, Agent 5 |
| L9 Frontend component | Forms, states, error mapping, permission-driven navigation, accessibility basics | Vitest + Testing Library | Agent 3 |
| L10 Manual/exploratory | Device matrix, PWA install, camera/location on real phones, cross-browser smoke | Devices | Agent 3, Agent 5 |

---

## 3. Tooling

| Purpose | Tool |
| --- | --- |
| Backend unit/integration | `pytest`, `pytest-asyncio`, `httpx` (ASGI transport), `pytest-cov` |
| Database for tests | PostgreSQL 16 via `testcontainers` (or a dedicated CI service), with `btree_gist`, `citext`, `pgcrypto` enabled |
| Factories and fixtures | `factory_boy` (or equivalent) producing committed, deterministic fixtures |
| Concurrency | `asyncio.gather` over independent database sessions plus `pytest.mark.concurrency` tests |
| Frontend unit/component | `vitest`, `@testing-library/react`, `@testing-library/user-event`, `msw` for API mocking |
| E2E | `playwright` with a seeded database and a running API |
| Accessibility | `axe-core` integrated into component and Playwright tests |
| Lint/format/type | `ruff` (lint + format), `mypy` (backend); `eslint`, `prettier`, `tsc --noEmit` (frontend) |
| CI | The pipeline in section 5; failures block merge |

Test data rules: tests must not depend on production data; every test creates its own fixtures;
dates are injected (a controllable clock) so time-dependent tests are deterministic; the business
timezone for tests is pinned to `Asia/Kolkata` unless a test explicitly exercises another zone.

---

## 4. Test Environments

| Environment | Purpose | Notes |
| --- | --- | --- |
| Local unit | Fast feedback | No network, no database |
| CI integration | Full API/DB suites | Ephemeral PostgreSQL, migrations applied to head before tests |
| E2E | Workflow verification | Seeded with the documented seed data plus test-specific fixtures; object storage replaced by a local S3-compatible container |
| Staging | Pre-production verification | Same configuration shape as production; no production credentials or data |
| Device matrix (manual) | Mobile/PWA verification | Entry-level and mid-range Android with Chrome, iOS Safari, desktop Chrome/Firefox/Safari/Edge |

---

## 5. Quality Gates and CI Pipeline

Ordered pipeline; a failure at any stage blocks the merge and the release:

1. Lint, format check, type check (backend and frontend).
2. Module-boundary contract test (`tests/test_module_boundaries.py`, `import-linter`).
3. Unit tests with coverage thresholds (business-rule modules >= 90%, overall >= 80%; money,
   attendance math, permissions and state machines >= 95%).
4. Migrations: apply from empty to head, downgrade one revision and re-upgrade; assert the schema
   matches head.
5. Integration tests (API + DB).
6. Database integrity tests (constraints, triggers, append-only).
7. Concurrency tests (section 7).
8. Security tests (section 8), including the negative authorization matrix.
9. Report reconciliation tests (section 9).
10. Frontend component tests and accessibility checks.
11. E2E critical flows (section 10).
12. Seed idempotency: running seeds twice must not create duplicates.

Coverage is a floor, not a goal: a module with 95% coverage and no negative tests still fails the
"definition of done" requirement.

---

## 6. Required Test Cases by Module

The following are minimum requirements, not a complete list.

### 6.1 Authentication and sessions

- Login success returns a session, sets cookies, audits the event, and issues CSRF material.
- Wrong password, unknown user, locked account, disabled account and inactive employee produce the
  documented codes without revealing which factor failed.
- Lockout triggers at `security.max_failed_logins` and releases after `security.lockout_minutes`.
- Idle timeout and absolute timeout both invalidate the session; renewal slides the idle timeout but
  not the absolute one.
- Logout revokes only the current session; password change revokes all others; admin reset revokes
  all and sets `must_change_password`.
- `must_change_password = true` blocks business endpoints with the documented error.
- Unsafe requests without a CSRF token are rejected; a token from another session is rejected.
- Rate limiting returns `429` with `Retry-After` on login attempts.
- Secrets, tokens, passwords and hashes never appear in logs, audit rows or API responses
  (asserted by scanning captured output).

### 6.2 Permissions and authorization

- The seeded `ADMIN` role holds all 96 catalog permissions; the seeded `EMPLOYEE` role holds exactly
  the 28 documented ones (exact-set assertion, so accidental drift fails the build).
- Every catalog permission maps to at least one route declaration, and every declared route
  permission exists in the catalog (bidirectional check).
- The full negative matrix in section 8.
- Permission changes take effect on the next request; a revoked permission immediately returns
  `403`.
- Object-level checks: each ownership rule in `docs/05_PERMISSIONS.md` section 5 has a positive test
  (owner succeeds) and a negative test (non-owner fails with the documented code).

### 6.3 Attendance and verification

- Check-in with valid GPS inside the geofence and a valid QR succeeds and stores one event, one open
  session, and one verification row per evaluated method.
- Each failure mode produces its specific `failure_code` and **no** attendance event:
  `LOCATION_UNAVAILABLE`, `LOCATION_STALE` (at the limit and one second beyond),
  `ACCURACY_EXCEEDS_LIMIT` (at the limit and just beyond), `OUTSIDE_GEOFENCE` (just inside, exactly
  on the radius, just outside), `QR_INVALID`, `QR_EXPIRED`, `QR_REPLAYED`, `METHOD_NOT_ALLOWED`.
- All four verification modes (`GPS_AND_QR`, `GPS_OR_QR`, `GPS_ONLY`, `QR_ONLY`) and all four
  check-out modes behave as configured (parameterized tests).
- Geofence distance math is verified against known coordinates and radii.
- Check-out with an open break auto-closes the break first and records the audit entry.
- Duplicate check-in returns the open session with `409` and creates nothing new.
- Sessions exceeding `attendance.max_sessions_per_day` are rejected.
- Multiple sessions in one day sum correctly; overlapping sessions are merged and never
  double-counted.
- Shift-crossing-midnight behavior assigns the correct business date.
- Late/early computations are tested at grace boundaries (inside, exactly on, just outside) and are
  zero when shift tracking is disabled.

### 6.4 Work-hour and day classification

- Table-driven tests for `worked_seconds`: single session, multiple sessions, paid break, unpaid
  break, unpaid break overlapping a session boundary, break tracking disabled with the automatic
  deduction, and a zero-length session.
- Threshold boundaries for `FULL_DAY`, `HALF_DAY`, `PARTIAL_DAY`, `NONE` at each setting value
  (exact boundary included).
- Overtime: disabled, below threshold, exactly at threshold, increment behavior, cap applied, and
  the increment floor.
- Recomputation is idempotent: running it twice changes nothing the second time and does not bump
  the version when values are unchanged.
- Changing a threshold and recomputing a record changes only the intended fields, bumps
  `computation_version`, and stores a new snapshot.
- Reconciliation: stored values equal a fresh recomputation (property-style test over generated
  event sequences).

### 6.5 Breaks

- Break start/end sequences, duplicate start, duplicate end, break without a session, break crossing
  check-out, break exceeding `attendance.break_max_minutes_per_day` (recorded as an anomaly), and
  paid vs unpaid effect on worked hours.

### 6.6 Attendance correction

- Request, approve and reject paths; self-approval refused; a second approver race returns `409`;
  approval inside a locked period returns `423`; backdate limit enforced; the correction creates a
  new event and preserves the original; the recomputation audit contains before/after values.

### 6.7 Tasks

- Create with one and with multiple assignees; assignment to an inactive employee rejected;
  duplicate assignment rejected.
- Full lifecycle: assigned -> started -> complete -> submitted -> approved.
- Resubmission path: request resubmission -> resubmit (attempt 2) -> approve, with attempt 1
  preserved including its evidence and the reviewer's notes.
- Rejection is terminal; a further submission is refused.
- Evidence enforcement: description-only, attachment-only, attachments disabled, attachment
  required but missing, and attachment count over the limit.
- Self-review refused for approve, reject and request-resubmission.
- Concurrent double decision returns one success and one `409`.
- Double submission with the same idempotency key creates exactly one attempt.
- Task rollup status matches the documented table for each assignment combination.

### 6.8 Orders

- Creation, broadcast (all three audience scopes), re-broadcast increments the round and
  deactivates the previous one, and the available list respects audience and expiry.
- Claim eligibility rules: inactive employee, expired broadcast, attendance requirement on and off,
  active-claim limit reached, creator self-claim guard.
- Full lifecycle through to delivered, with the claim closed as `COMPLETED` and `delivered_at` set.
- Invalid transitions (skips, backwards, out of terminal states) are refused with
  `ORDER_INVALID_TRANSITION`.
- Proof enforcement: delivery without required proof refused; with proof accepted; packing proof
  required and provided.
- Release by the holder; expiration by the sweeper; reassignment with and without a target
  employee; reassignment cap; reassignment refused after dispatch.
- Cancellation from each allowed status; cancellation refused after delivery; failure requires a
  reason; both are terminal.
- Order amounts are exact decimals, including totals in the report.
- A non-holder without admin permission receives `404` for detail, status change and proof upload.

### 6.9 Leave

- Application with sufficient and insufficient balance (with `allow_negative_balance` on and off).
- Hold posted on application; approval converts the hold to usage; rejection releases the hold
  exactly once; cancellation of a pending request releases it; cancellation of an approved request
  reverses usage.
- Overlap rejected by the service and by the database constraint; two concurrent overlapping
  applications produce exactly one success.
- Half-day behavior when allowed and when disabled; consecutive-day limit; attachment threshold;
  advance and backdate limits.
- Day counting excludes weekly offs and holidays unless configured otherwise.
- Month and year boundary spanning; leave-year reset month.
- Accrual modes (`ANNUAL_UPFRONT`, `MONTHLY_ACCRUAL`, `MANUAL`), carry-forward with cap, and expiry
  movements.
- Balance adjustment cannot push the balance below `used_days` or negative when disallowed.
- Attendance records for covered dates become `ON_LEAVE` on approval and are reclassified on
  cancellation.

### 6.10 Ledger, advances and salary

- Ledger append-only: entries cannot be updated or deleted through the application; a reversal
  creates a new row and the original stays; a double reversal is refused.
- Sign convention: a fully paid period nets to zero; a partially paid period leaves the expected
  balance.
- Advance issuance with and without approval; limit enforcement; installment arithmetic sums exactly
  to the amount; payroll recovery caps at the outstanding amount and at
  `advance.max_percent_recovered_per_month`; cash repayment cannot exceed the outstanding amount;
  write-off closes the advance and is audited.
- Salary computation for all three compensation types with day-credit combinations
  (full, half, partial, paid leave, holiday, weekly off, absent), verifying each component against a
  hand-calculated expectation.
- Rounding modes `HALF_UP`, `HALF_EVEN` and `FLOOR`, including a case designed to expose double
  rounding.
- The database identity `net = gross + overtime + bonus - total_deductions` holds for every row.
- The rule snapshot is written and referenced; recomputing with changed settings after finalization
  is impossible; a `FINALIZED` row cannot be modified even by a direct SQL update (trigger test).
- Payroll lifecycle guards: finalize with pending corrections blocked (and allowed with the audited
  override); pay before finalize blocked; lock blocks corrections and leave changes; unlock requires
  `payroll.unlock` and a reason.
- Month-end: a shift crossing into the next month lands in the correct period; a night shift is not
  split.
- A post-payroll correction produces an adjustment entry in the open period and leaves the finalized
  record untouched.

### 6.11 Complaints

- Creation with defaults from category and settings; visibility enforcement for all three
  visibilities; internal comments hidden from the raiser; a subject employee cannot see a complaint
  about them by default.
- Lifecycle transitions including backwards transitions with a reason; rejection requires a reason;
  resolution requires a summary; closing requires a resolution; comments blocked after close unless
  configured.
- Status history and audit rows written for every transition.

### 6.12 Notifications

- Each documented event produces exactly one in-app notification per intended recipient and the
  expected delivery rows.
- Idempotent handler: redelivering the same event creates no duplicate.
- Preferences suppress non-critical channels but never security events; quiet hours defer but do not
  drop.
- Delivery failure retries with backoff and ends in `FAILED` without affecting business state; a
  failing push subscription is deactivated after the threshold.
- Cursor pagination returns stable ordering and a working `next_cursor`.

### 6.13 Settings

- Registry validation: unknown key, wrong type, out-of-range, disallowed enum and missing reason are
  all rejected; a bulk update with one invalid value changes nothing.
- Every setting in `docs/04_BUSINESS_RULES.md` section 3 exists in the seed with its documented
  default, and `is_provisional` matches the client-decision list (exact-set test to prevent silent
  drift).
- History rows written with old/new values, actor and reason; version increments.
- Changed settings are used by the next computation and do not retroactively rewrite finalized
  records.

### 6.14 Files

- Upload validation: oversize, disallowed type, spoofed magic bytes, and a valid upload with a
  checksum.
- Authorized download succeeds; unauthorized download returns `404`; a presigned URL expires; URL
  issuance is audited.
- Deleting a referenced file is refused; soft-deleting an unreferenced file succeeds.
- Attachment caps per entity enforced.

### 6.15 Audit

- Every audited action in `docs/05_PERMISSIONS.md` section 7.6 produces exactly one audit row with
  the expected actor, action, entity, before/after and reason.
- Redaction: passwords, tokens, secrets and full bank numbers never appear in `before`, `after`,
  `reason` or logs.
- `UPDATE`/`DELETE` on `audit_logs` fail for the application role.

### 6.16 Frontend component tests

- Permission-driven navigation: routes and actions are absent without the permission.
- Mutation states: in-flight disables the control; success renders the server result; failure renders
  the specific message; a double click produces exactly one request with one idempotency key.
- Conflict presentation: claim conflict panel, state conflict refresh, period-locked guidance.
- Attendance UI: location permission denied, scanner unavailable, expired QR rescan, failure-reason
  copy, and the rule that no local success state is ever shown.
- Forms: validation errors highlighted from the server, required-field behavior, upload progress and
  failure.
- Accessibility: axe checks on each primary screen, focus management in dialogs, and live-region
  announcements for async results.
- Money and duration formatting use the decimal/timezone formatters, never ad-hoc math.---

## 7. Concurrency Tests (Mandatory)

These tests use independent database sessions in parallel and assert final database state, not just
HTTP codes.

| # | Test | Expected result |
| --- | --- | --- |
| C-1 | Two employees claim the same order simultaneously | Exactly one `200` and one `409 CLAIM_ALREADY_TAKEN`; exactly one `order_claims` row with `status = 'ACTIVE'`; `orders.current_assignee_id` matches the winner; exactly one `order.claimed.v1` event and one audit row |
| C-2 | The same employee claims with the same idempotency key twice in parallel | One claim row; one success response and one replayed response; no conflict error |
| C-3 | Two check-in requests in parallel for one employee | One open session; one attendance event; the other returns `409` |
| C-4 | Two check-outs in parallel | One `CHECK_OUT` event; the second returns `409`; worked seconds counted once |
| C-5 | Two break starts in parallel | One open break; the second returns `409` |
| C-6 | Two task submissions in parallel for one assignment | One new attempt (`attempt_no` increments once); one success and one `409`, or an idempotent replay with the same key |
| C-7 | Two reviewers decide one submission in parallel | One decision recorded; the other gets `409`; one audit row |
| C-8 | Two Admins approve one attendance correction in parallel | One approval; one `409`; exactly one `CORRECTION` event |
| C-9 | Two overlapping leave applications in parallel for one employee | One succeeds; the other fails with `LEAVE_OVERLAP`; the balance hold reflects exactly one request |
| C-10 | Two leave approvals in parallel consuming the same balance | One succeeds while balance allows; the other fails when the balance is insufficient; balances and ledger reconcile |
| C-11 | Two advance repayments in parallel for one advance | Outstanding never negative; over-repayment refused; one ledger row per accepted repayment |
| C-12 | Two payroll computations in parallel for one period | One run; no duplicate salary rows (unique employee/period constraint); results are consistent |
| C-13 | Two mark-paid calls in parallel for one run | One transition; one `PAYMENT_MADE` entry per employee; the second gets `409` |
| C-14 | Two settings updates in parallel | Both recorded with sequential versions; no lost audit history; the final value is the last committed |
| C-15 | Outbox dispatch run by two workers concurrently | Each event dispatched exactly once (`SKIP LOCKED`); no duplicate notifications |
| C-16 | A scheduler job executed while another instance holds the advisory lock | The second instance skips (`SKIPPED_LOCKED`) and performs no work |
| C-17 | Two deactivations of the same employee in parallel | One cascade; the second is a conflict or an idempotent no-op; no duplicate claim releases |
| C-18 | Duplicate file upload with the same idempotency key | One file row; one success and one replay |

Every concurrency test must also assert that no partial state exists (for example an order with a
claim but no `current_assignee_id`, or a leave marked approved without a usage movement).

---

## 8. Security and Authorization Tests (Mandatory)

Derived from `docs/03_API_CONTRACT.md` section 20 and `docs/05_PERMISSIONS.md`. Agents 2 and 5 both
run these.

| # | Attempt | Expected |
| --- | --- | --- |
| S-1 | Employee calls an admin endpoint (`employee.read.all`, `settings.update`, `payroll.*`, `audit.read`) | `403 PERMISSION_DENIED` |
| S-2 | Employee reads another employee's profile, attendance, task, order, leave, ledger, salary, complaint or file by id | `404` (hidden) with no data leak in the body |
| S-3 | Employee reads a list endpoint that would include others' data | The response contains only their own rows (scope enforced in SQL) |
| S-4 | Employee attempts to change their own attendance record, salary, ledger entry or approval state | `403`/`404`; no endpoint exists that the client can misuse |
| S-5 | Employee approves their own task submission, leave, correction, advance or complaint | `403`/`422 SELF_APPROVAL_NOT_ALLOWED` |
| S-6 | Employee claims an already-claimed order | `409 CLAIM_ALREADY_TAKEN`; no second claim row |
| S-7 | Employee requests a file they are not authorized for (guessed uuid) | `404`; no presigned URL issued |
| S-8 | Employee downloads a presigned URL after expiry | Storage rejects it; the API never extends it |
| S-9 | Malicious uploads: executable renamed `.jpg`, oversized file, SVG with script, zip, path-traversal filename | Rejected by type/magic-byte/size validation; the filename never influences the storage path |
| S-10 | Forged attendance payload: client-provided distance, "verified" flag, coordinates inside the fence while the geofence setting says otherwise, business date, employee id, worked seconds | The server ignores all client claims and recomputes; the stored result reflects server evaluation |
| S-11 | Manipulated financial payload: negative amount, unknown entry type, someone else's employee id, edit of a finalized salary record, entry into a locked period | `403`/`422`/`423` as applicable; nothing written |
| S-12 | QR replay: reuse a consumed token | `failure_code = QR_REPLAYED`; no attendance event |
| S-13 | Expired QR token | `failure_code = QR_EXPIRED`; no event |
| S-14 | SQL injection attempts in filters, sort, search and ids (including `' OR 1=1--` and stacked statements) | `422`/`404`; no injected SQL executed; sort/filter identifiers come from allow-lists |
| S-15 | XSS payloads in task titles, comments, complaint text, order notes, filenames and settings strings | Rendered escaped; no script execution in the E2E test; stored content returned as data |
| S-16 | Unsafe request without a CSRF token, or with another session's token | `403 CSRF_INVALID` |
| S-17 | Session abuse: stolen cookie after password change or deactivation, reuse after logout, tampered cookie value | `401`; session revoked |
| S-18 | Privilege escalation: assign self a role, grant a permission beyond own authority, remove the last Admin, delete a system role, delete a role in use | `403`/`422 RULE_VIOLATION` (`LAST_ADMIN_PROTECTED` where applicable); all attempts audited |
| S-19 | Rate-limit abuse on login, check-in, uploads and exports | `429` with `Retry-After`; no bypass by changing headers or identifiers |
| S-20 | Secret exposure scan: search logs, audit rows and API responses for passwords, tokens, keys and full bank numbers | Nothing found |
| S-21 | IDOR via UUID substitution across every resource type | `404`/`403` consistently |
| S-22 | Mass assignment: send unexpected or privileged fields (`status`, `approved_by`, `net_amount`, `role_codes`) | Unknown fields rejected (`422`) or ignored; never applied |
| S-23 | Malformed and oversized bodies, deep JSON nesting, wrong content types | `400`/`413`/`422`; no crash and no resource exhaustion |
| S-24 | CORS request from a disallowed origin with credentials | Refused by the server policy and by the browser |

---

## 9. Report Validation Tests

Implement one test per reconciliation rule in `docs/08_REPORT_SPEC.md` section 6 (RC-1..RC-18).
Each test must:

1. seed a dataset containing boundary cases (zero-day employees, exactly-threshold days, half days,
   partial days, leaves spanning month ends, overtime at the cap, corrected days, cancelled orders,
   reassigned orders, partially recovered advances, reversals, a locked payroll period, an exited
   employee);
2. compute the report through the API;
3. recompute the same figure directly from the source tables (SQL or independent Python);
4. assert exact equality, including money as decimals;
5. assert that the interactive view and the exported file agree.

Additional required checks:

- Money totals are identical in the interactive report, the CSV export and the underlying
  `SUM(numeric)` (three-way comparison).
- Day counts per employee sum to the number of business dates in the range with no overlap.
- Reports never include rows or fields the caller could not obtain from the detail endpoints.
- Employee-scoped report requests without `all` scope return only the employee's own rows.
- Report range validation rejects over-limit ranges and mismatched formats.
- Export lifecycle: queued -> running -> completed, authorized download, expiry cleanup.

---

## 10. End-to-End Critical Flows

Playwright flows run against a seeded environment and follow the workflow identifiers in
`docs/06_WORKFLOWS.md`.

| # | Flow | Assertions |
| --- | --- | --- |
| E2E-1 | Login -> dashboard -> logout (W-01) | Correct role landing, session established, logout clears access, protected route redirects |
| E2E-2 | Check-in with location and QR -> break start/end -> check-out (W-05, W-06, W-07) | Server result displayed, worked hours appear, break reflected, history shows the events |
| E2E-3 | Check-in rejection paths: outside geofence, poor accuracy, expired QR (W-05) | Specific message shown; no attendance event created; retry succeeds |
| E2E-4 | Missing checkout -> correction request -> admin approval (W-08, W-09) | Day becomes correct; audit trail visible; employee notified |
| E2E-5 | Task assigned -> start -> submit with photo -> resubmission requested -> resubmit -> approve (W-11, W-12) | Attempt history preserved; statuses correct; employee notified at each decision |
| E2E-6 | Order create -> broadcast -> two employees see it -> one claims -> other sees conflict (W-13, W-14) | Exactly one owner; conflict panel shown to the loser; available list refreshes |
| E2E-7 | Order fulfillment with proof -> delivered -> proof visible to Admin (W-15) | Status stepper correct; proof required and stored; history complete |
| E2E-8 | Claim expiry -> sweeper releases -> re-broadcast -> second employee claims (W-16) | Order returns to the pool; both parties notified; history shows the release |
| E2E-9 | Leave apply -> approve -> balance updates -> cancel approved leave (W-18, W-19) | Balance components correct; attendance reclassified; ledger movements visible |
| E2E-10 | Advance issue -> payroll recovery -> advance closes (W-20, W-22) | Outstanding decreases correctly; salary deduction shown; advance closed at zero |
| E2E-11 | Payroll: compute -> finalize -> lock -> pay (W-22) | Blockers shown before finalize; locked period rejects corrections; payment entries exist |
| E2E-12 | Complaint submit -> triage -> resolve -> close with an internal note (W-23) | Internal note never visible to the raiser; status timeline correct |
| E2E-13 | Settings change with a reason, including a provisional setting (W-26) | Diff preview, provisional labelling, history entry, effect on the next computation |
| E2E-14 | Report view -> filter -> export -> download (W-25) | Numbers match the list; export row count matches; download authorized |
| E2E-15 | Role change grants a permission -> navigation updates -> action becomes available (W-27) | UI reflects the change after refresh; the server enforces it immediately |
| E2E-16 | Audit investigation for a change made in an earlier flow (W-28) | Row found with actor, before/after and reason; no secrets present |
| E2E-17 | PWA install, offline read path, and a mutation attempted offline | Offline banner and cached data shown; the mutation fails with a clear message; retry uses the same idempotency key |
| E2E-18 | Session expiry mid-flow -> redirect to login -> login returns to a safe destination | No data loss for GET navigation; no half-completed mutation |

Every E2E flow must assert that the UI never displays a business state that contradicts the server
and that the browser console contains no unhandled errors.

---

## 11. Database Integrity and Migration Tests

- Each constraint in `docs/02_DATABASE.md` section 18 has a test that attempts the forbidden state
  directly in SQL and expects failure: open-session uniqueness, open-break uniqueness, active-claim
  uniqueness, one record per employee per date, one salary record per employee per period, one
  payroll run per period, leave overlap exclusion, compensation overlap exclusion, assignment
  uniqueness, attempt-number uniqueness, order assignee coherence, salary arithmetic, cancelled
  reason, status timestamps, and active-broadcast uniqueness.
- The salary immutability trigger rejects any financial change on a `FINALIZED`/`PAID` row while
  still permitting `FINALIZED -> PAID`.
- Generated columns hold: `leave_balances.available_days` and
  `salary_records.total_deductions`.
- Append-only tables reject `UPDATE`/`DELETE` for the application role.
- Required extensions are created idempotently.
- Migrations: empty -> head, head -> one revision down -> head again, with the schema compared to
  head.
- Seeds are idempotent: running them twice produces no duplicates and no changed defaults.
- Every seeded setting matches `docs/04_BUSINESS_RULES.md` section 3 and every permission matches
  `docs/05_PERMISSIONS.md` section 3 (exact-set tests).

---

## 12. Non-Functional Tests

| Area | Requirement to verify |
| --- | --- |
| Performance | A 30-day attendance report for 21 employees returns within a documented budget; an export of the same range completes within a documented budget |
| Pagination | Large lists page correctly with stable ordering; cursor pagination for notifications and audit logs tolerates inserts during iteration |
| Timeouts | Report and export sessions have statement timeouts and fail gracefully with `DEPENDENCY_UNAVAILABLE` rather than hanging |
| Storage failure | Object storage unavailable produces `STORAGE_UNAVAILABLE` on upload and leaves no dangling `files` row |
| Database failure | Database unavailable produces `503` from `/health/ready` and clean API errors |
| Job safety | Every scheduled job is safe to run twice, records a `job_runs` row, and processes bounded batches |
| Backups (staging) | Restoring a backup into staging produces a working system with the audit log and ledger intact |
| Log hygiene | Logs contain request ids and no secrets; log volume per request is bounded |

---

## 13. Defect Handling, Severity and Exit Criteria

| Severity | Definition | Examples |
| --- | --- | --- |
| `CRITICAL` | Data corruption, wrong money, authorization bypass, two employees owning one order, silent history rewrite | Salary miscalculation, claim race failure, IDOR, finalized payroll edited |
| `HIGH` | A core workflow cannot complete, or a rule is enforced incorrectly without data loss | Valid check-in rejected, leave balance wrong, correction impossible |
| `MEDIUM` | Incorrect but non-destructive behavior, poor failure handling, missing audit detail | Wrong error message, missing notification, unreconciled report figure |
| `LOW` | Cosmetic, wording, minor UX | Label typo, spacing, unclear copy |
| `CLIENT_DECISION_REQUIRED` | Not a defect: policy awaiting confirmation | Any of the 25 items in `docs/04_BUSINESS_RULES.md` section 10 |

Rules: every defect report includes severity, reproduction steps, expected, actual, root cause when
known, and a fix recommendation. No `CRITICAL` or `HIGH` issue is closed without a verifying test. A
policy that simply needs client confirmation is **not** logged as a defect.

Exit criteria for a release candidate:

1. All CI stages green.
2. No open `CRITICAL` or `HIGH` defects.
3. All critical-affecting test categories (concurrency, negative authorization, salary identity,
   claim atomicity) passing on the release commit.
4. All report reconciliations passing.
5. Known limitations documented, and all `CLIENT_DECISION_REQUIRED` items listed with their
   provisional defaults and their financial or legal impact highlighted.
6. Agent 5's `docs/PRODUCTION_CHECKLIST.md` reviewed with no unresolved blocker.

---

## 14. Traceability

| Product module | Workflows | Required tests |
| --- | --- | --- |
| Authentication | W-01, W-02 | 6.1, S-16, S-17, S-19 |
| Users / Employees | W-03, W-04 | 6.2, S-2, S-18 |
| RBAC | W-27 | 6.2, S-18 |
| Settings | W-26 | 6.13, E2E-13 |
| Attendance, Breaks, Verification, QR | W-05 to W-10 | 6.3, 6.4, 6.5, 6.6, C-3, C-4, C-5, C-8, E2E-2, E2E-3, E2E-4 |
| Tasks | W-11, W-12 | 6.7, C-6, C-7, E2E-5 |
| Orders | W-13 to W-17 | 6.8, C-1, C-2, E2E-6, E2E-7, E2E-8 |
| Leave | W-18, W-19 | 6.9, C-9, C-10, E2E-9 |
| Ledger, Advances, Salary | W-20, W-21, W-22 | 6.10, C-11, C-12, C-13, E2E-10, E2E-11 |
| Complaints | W-23 | 6.11, E2E-12 |
| Notifications | W-24 | 6.12, C-15, C-16 |
| Reports / Export | W-25 | 9 (RC-1..RC-18), E2E-14 |
| Files | W-29 | 6.14, S-7, S-8, S-9, C-18 |
| Audit | W-28 | 6.15, S-20, E2E-16 |
| Database integrity | all | 11 |
| Frontend experience | all | 6.16, 10, 12 |

---

## 15. Open Items

- Performance budgets in section 12 are indicative and should be confirmed once the client confirms
  expected report sizes and the device profile of employees.
- Automated accessibility coverage targets the WCAG 2.1 AA checks that tooling can detect; a manual
  screen-reader pass on the attendance and order flows is recommended before production.
- Cross-browser manual verification is required because the attendance flow depends on browser
  geolocation and camera APIs, which behave differently across iOS Safari and Android Chrome.
- Any client decision in `docs/04_BUSINESS_RULES.md` section 10 that changes a formula requires the
  corresponding tests in sections 6.3 to 6.10 to be updated in the same change, per the change
  protocol in `AGENTS.md` section 5.