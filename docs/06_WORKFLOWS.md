# 06 - Workflows

| Field | Value |
| --- | --- |
| Document owner | Agent 1 - Architect / Tech Lead |
| Status | Baseline (implementation-ready) |
| Version | 1.0 |
| Source-of-truth rank | 4 |
| Applies to | Agents 2, 3, 4, 5 |

This document describes every end-to-end workflow: who does what, in what order, what the system
enforces at each step, what is audited, and how failures are handled. Rule details (formulas,
thresholds, transitions) live in `docs/04_BUSINESS_RULES.md`; endpoints live in
`docs/03_API_CONTRACT.md`.

Every workflow below is written so that Agent 2 can implement it, Agent 3 can build the UI for
it, Agent 4 can check it against real operations, and Agent 5 can test it end to end.

---

## 1. How to Read a Workflow

Each workflow uses the same structure:

- **Trigger** - the event that starts it.
- **Actors** - who participates and with which permission.
- **Preconditions** - state that must already hold.
- **Steps** - the ordered interactions, with the server-side enforcement noted.
- **Success outcome** - resulting state.
- **Failure paths** - what happens when each step fails, and what the user sees.
- **Notifications / Audit** - what is emitted.
- **Related edge cases** - the `E-xx` identifiers from `docs/04_BUSINESS_RULES.md` section 5.

Two invariants apply to every workflow and are not repeated:

1. The backend validates and computes authoritative state; client-supplied state is never trusted.
2. Every state change is written in a single transaction with its audit record and domain event.

---

## 2. Workflow Index

| ID | Workflow | Primary actor | Key permissions |
| --- | --- | --- | --- |
| W-01 | Login / session lifecycle | Everyone | `auth.*.self` |
| W-02 | Password change / admin reset | Everyone / Admin | `auth.password.change.self`, `employee.manage.credentials` |
| W-03 | Employee onboarding | Admin | `employee.create`, `employee.manage.roles` |
| W-04 | Employee deactivation / reactivation | Admin | `employee.deactivate` |
| W-05 | Check-in with verification | Employee | `attendance.checkin.self` |
| W-06 | Break start / end | Employee | `attendance.break.self` |
| W-07 | Check-out | Employee | `attendance.checkout.self` |
| W-08 | Missing checkout handling | System / Employee / Admin | `attendance.correct.request.self`, `attendance.manage` |
| W-09 | Attendance correction | Employee / Admin | `attendance.correct.request.self`, `attendance.correct.approve` |
| W-10 | Work-hour computation and day classification | System | `attendance.read.self` / `attendance.read.all` |
| W-11 | Task assignment and execution | Admin / Employee | `task.create`, `task.assign`, `task.submit.self` |
| W-12 | Task review and resubmission | Admin / Employee | `task.review`, `task.submit.self` |
| W-13 | Order creation and broadcast | Admin | `order.create`, `order.broadcast` |
| W-14 | Atomic order claim | Employee | `order.claim` |
| W-15 | Order fulfillment and proof of delivery | Employee | `order.update.status.self`, `order.proof.upload` |
| W-16 | Order release, abandonment and reassignment | Employee / Admin / System | `order.reassign` |
| W-17 | Order cancellation and failure | Admin / Employee | `order.cancel`, `order.update.status.self` |
| W-18 | Leave application and decision | Employee / Admin | `leave.apply.self`, `leave.approve` |
| W-19 | Leave cancellation and balance correction | Employee / Admin | `leave.cancel.self`, `leave.cancel.any`, `leave.balance.manage` |
| W-20 | Advance issuance and recovery | Admin | `advance.create`, `advance.approve` |
| W-21 | Manual financial adjustment and reversal | Admin | `ledger.entry.create`, `ledger.entry.adjust` |
| W-22 | Payroll run: compute, finalize, lock, pay | Admin | `salary.compute`, `salary.finalize`, `payroll.*` |
| W-23 | Complaint intake and resolution | Employee / Admin | `complaint.create.self`, `complaint.manage`, `complaint.resolve` |
| W-24 | Notification delivery | System | `notification.read.self` |
| W-25 | Reporting and export | Admin | `report.*`, `report.export` |
| W-26 | Settings change | Admin | `settings.update` |
| W-27 | Role and permission management | Admin | `role.manage`, `employee.manage.roles` |
| W-28 | Audit inspection | Admin | `audit.read` |
| W-29 | File upload and authorized download | Everyone | `file.upload` |

---

## 3. Identity Workflows

### W-01 - Login / session lifecycle

- **Trigger:** a user opens the app or signs in.
- **Actors:** any user with an active account.
- **Preconditions:** the account exists and is `ACTIVE`; the employee (if any) is not `EXITED`.
- **Steps:**
  1. Client requests `POST /auth/login` with credentials.
  2. Server enforces the login rate limit; exceeding it returns `429 RATE_LIMITED`.
  3. Server resolves the identifier, verifies the Argon2id hash, and checks `status`, `locked_until`
     and failed-attempt counters.
  4. On success: reset failure counters, create a session row (token hash, CSRF hash, absolute and
     idle expiry), set `HttpOnly`/`Secure`/`SameSite=Lax` cookies, audit the event, emit
     `identity.session.created.v1`.
  5. On failure: record the attempt, increment counters, apply lockout at the threshold, return a
     generic `INVALID_CREDENTIALS` (never revealing which factor was wrong), audit the attempt.
  6. Client calls `GET /auth/me` and routes by role using the returned permissions.
  7. Session renewal: each authenticated request refreshes `idle_expires_at` (capped by the
     absolute `expires_at`).
- **Success outcome:** an authenticated session with a resolved permission set.
- **Failure paths:** bad credentials (`401`), locked account (`423 ACCOUNT_LOCKED`), disabled
  account (`403 ACCOUNT_DISABLED`), expired/idle-out session (`401 SESSION_EXPIRED` -> client
  redirects to login), revoked session (`401`).
- **Notifications:** none for login. Security events (repeated failures, lockout) are audited and,
  where configured, surfaced to the Admin.
- **Audit:** `AUTH`/`SECURITY` category - login success, login failure, lockout, logout, session
  revocation.
- **Edge cases:** E-84 (duplicate submission), E-86 (clock/timezone), session theft (W-02, W-04).

### W-02 - Password change / admin reset

- **Trigger:** user decides to change their password, or an Admin resets it.
- **Actors:** the account owner (`auth.password.change.self`) or an Admin
  (`employee.manage.credentials`).
- **Steps (self-change):** submit current + new password -> server verifies the current password,
  enforces policy (`security.password_min_length`, `security.password_require_complexity` and a
  not-same-as-current check), writes the new Argon2id hash, revokes **all other** sessions, audits
  the event, and keeps the current session valid.
- **Steps (admin reset):** Admin submits `{ user_id, reason }` -> server generates a one-time
  token (hashed at rest, TTL `security.password_reset_ttl_minutes`), returns it once, sets
  `must_change_password = true`, revokes all sessions of the target user, audits the event.
- **Success outcome:** credentials updated; the target must set a new password before doing
  anything else.
- **Failure paths:** wrong current password (`401`), policy violation (`422 VALIDATION_ERROR` with
  the specific rule), reset for an inactive user (`422 RULE_VIOLATION`).
- **Audit:** `AUTH`/`SECURITY` with actor, target, reason (never the password or token value).
- **Related edge cases:** E-84, session theft containment.

### W-03 - Employee onboarding

- **Trigger:** Admin adds a new employee.
- **Actors:** Admin with `employee.create`; role assignment additionally requires
  `employee.manage.roles`; compensation requires `employee.update.sensitive`.
- **Steps:**
  1. Admin submits employee details, username, initial roles (default `EMPLOYEE`) and optionally
     the initial compensation.
  2. Server validates uniqueness (`employee_code`, `username`, `email`), dates, and referential
     integrity (`manager_employee_id`).
  3. In one transaction: create `users` (password hash or generated one-time password with
     `must_change_password = true`), create `employees`, create `employee_compensation` when
     supplied, assign roles, write audit records, emit `directory.employee.created.v1`.
  4. If a password was generated, it is returned once in the response; it is never logged.
  5. Admin communicates the credentials out of band. The employee logs in via W-01 and changes the
     password via W-02.
- **Success outcome:** an active employee who can authenticate and is eligible for tasks, orders,
  attendance and leave.
- **Failure paths:** duplicate code/username/email (`409 CONFLICT_DUPLICATE`), invalid dates or
  missing required fields (`422`), role assignment attempt beyond the actor's authority (`403`).
- **Notifications:** optional welcome notification; not required by the product scope.
- **Audit:** `EMPLOYEE` category (create, role assignment, compensation).
- **Related edge cases:** E-33 (assignment to inactive employee).

### W-04 - Employee deactivation / reactivation

- **Trigger:** employee leaves or is suspended; later possibly rehired.
- **Actors:** Admin with `employee.deactivate` (+ `order.reassign`, `task.assign` for a forced
  cascade).
- **Preconditions:** not the last active Admin (`LAST_ADMIN_PROTECTED`).
- **Steps:**
  1. Admin submits `{ date_of_exit, reason, force? }`.
  2. Server checks open responsibilities: active order claims and open task assignments.
  3. Without `force`, if any exist, return `422 RULE_VIOLATION` listing them so the Admin can
     handle them explicitly.
  4. With `force` (and the extra permissions), in one transaction: release active claims as
     `REVOKED` and return orders to the pool, mark open assignments for reassignment/cancellation,
     set `employment_status = 'EXITED'` and `date_of_exit`, disable the user, revoke all sessions,
     audit every cascade action, emit `directory.employee.deactivated.v1`.
  5. Outstanding financial state (advances) is reported but not auto-written-off; the Admin must
     choose settlement or write-off.
  6. Reactivation reverses status and re-enables login, keeping the same employee identity so
     history remains continuous.
- **Success outcome:** the employee can no longer authenticate or accept new work; all history is
  intact.
- **Failure paths:** last-admin protection, blocking responsibilities without `force`, invalid
  `date_of_exit`.
- **Notifications:** the employee (if reachable), and the Admin who owns the reassignment work.
- **Audit:** `EMPLOYEE` category with before/after status and every cascaded action.
- **Related edge cases:** E-33, E-72 (mid-period exit and payroll).

---

## 4. Attendance Workflows

### W-05 - Check-in with verification

- **Trigger:** employee arrives at the shop and taps Check In.
- **Actors:** employee with `attendance.checkin.self`.
- **Preconditions:** active employment; no open work session; geofence configured when GPS is
  required; a QR token available when QR is required.
- **Steps:**
  1. Client requests browser location; on denial it shows a clear explanation (no attendance event
     is attempted without the required evidence).
  2. Client obtains a fresh location fix and, when the mode requires QR, opens the scanner and
     scans the dynamic shop QR displayed at the shop.
  3. Client submits `POST /attendance/check-in` with latitude, longitude, accuracy,
     `location_captured_at`, the scanned QR payload and an `Idempotency-Key`.
  4. Server applies BR-4.1: state check, method resolution, GPS evaluation (availability,
     freshness, accuracy, geofence), QR evaluation (existence, expiry, single use, purpose).
  5. On success: create the `attendance_events` row, the open `attendance_sessions` row and one
     `attendance_verifications` row per evaluated method; consume the QR token; set the record
     `status = 'PRESENT'` with `is_open = true`; run the day recomputation (W-10).
  6. Return the record plus a `verification` block and `next_allowed_action`.
  7. On failure: record `attendance_verifications` rows only, return `422` with the precise
     `failure_code`, and rate limit repeated failures.
- **Success outcome:** authoritative attendance with stored evidence; the employee sees the
  server's result, never a local guess.
- **Failure paths:** `LOCATION_UNAVAILABLE`, `LOCATION_STALE`, `ACCURACY_EXCEEDS_LIMIT`,
  `OUTSIDE_GEOFENCE`, `QR_EXPIRED`, `QR_REPLAYED`, `QR_INVALID`, `METHOD_NOT_ALLOWED`
  (unconfigured geofence), `STATE_CONFLICT` (already checked in), `RATE_LIMITED`, and the offline
  case (E-06).
- **Notifications:** the Admin dashboard reflects late arrival; no per-event notification by
  default.
- **Audit:** `ATTENDANCE` category (event, verification result, QR consumption) plus
  `attendance.checked_in.v1`.
- **Related edge cases:** E-01, E-05 to E-14, E-24.

### W-06 - Break start / end

- **Trigger:** employee takes a configured break.
- **Actors:** employee with `attendance.break.self`.
- **Preconditions:** an open work session; no open break; break tracking enabled.
- **Steps:** submit break type -> server verifies session/break state and the daily break cap ->
  creates the `BREAK_START` event, the open `break_sessions` row (snapshotting `is_paid`) and
  recomputes the day. On end: verify an open break exists -> create the `BREAK_END` event, close
  the break with `duration_seconds`, recompute.
- **Success outcome:** break time recorded with paid/unpaid semantics.
- **Failure paths:** `STATE_CONFLICT` for a duplicate start/end or no open break;
  `BREAK_WITHOUT_SESSION` when no session is open; cap violation flagged as an anomaly (break time
  is still recorded).
- **Audit:** `ATTENDANCE` (break start/end) plus `attendance.break_started.v1` /
  `attendance.break_ended.v1`.
- **Related edge cases:** E-16, E-17, E-18, E-01.

### W-07 - Check-out

- **Trigger:** employee finishes work.
- **Actors:** employee with `attendance.checkout.self`.
- **Preconditions:** an open work session.
- **Steps:**
  1. Client gathers evidence per `attendance.checkout_verification_mode` (default: same as
     check-in).
  2. Submit `POST /attendance/check-out` with the required evidence and an `Idempotency-Key`.
  3. Server: if a break is open, close it first with `close_reason = AUTO_CLOSE` (audited); verify
     evidence per the configured mode; create the `CHECK_OUT` event; close the session with
     `duration_seconds`; set `is_open = false`, `status = 'PRESENT'`; recompute the day (W-10).
- **Success outcome:** the day's derived values are final, pending any correction.
- **Failure paths:** `STATE_CONFLICT` (no open session, or already checked out),
  verification failures as in W-05, `PERIOD_LOCKED` never applies to the current day.
- **Notifications:** none by default; the Admin dashboard updates.
- **Audit:** `ATTENDANCE` plus `attendance.checked_out.v1`.
- **Related edge cases:** E-02 (crossing midnight), E-04, E-16.

### W-08 - Missing checkout handling

- **Trigger:** the shift ends and a session is still open, or the system detects an unclosed day.
- **Actors:** system (sweeper), employee, Admin.
- **Steps:**
  1. `attendance_auto_close` runs every 15 minutes and finds open sessions past
     `shift_end + auto_close_grace_minutes`.
  2. It applies `attendance.missing_checkout_policy` (BR-4.4): keep incomplete and notify, close at
     shift end, close with a cap, or mark incomplete after closing.
  3. Original events are preserved; auto-close appends an `AUTO_CLOSE` event and an anomaly note.
  4. The employee is notified and can file a correction (W-09).
  5. The Admin sees incomplete days in the attendance list and in the payroll readiness check
     (W-22 refuses to finalize while corrections are pending, by default).
- **Success outcome:** no silently guessed worked time; every auto-closed day is visible and
  correctable.
- **Failure paths:** if auto-close cannot determine a shift end (shift tracking disabled), the
  policy falls back to leaving the record `INCOMPLETE` for correction.
- **Audit:** `ATTENDANCE` (auto-close with policy and computed duration).
- **Related edge cases:** E-03, E-04, E-22.

### W-09 - Attendance correction

- **Trigger:** employee notices a wrong or missing punch; or an Admin identifies a discrepancy.
- **Actors:** employee (`attendance.correct.request.self`), Admin (`attendance.correct.approve`).
- **Preconditions:** the target `attendance_record` exists; the date is within
  `attendance.correction_max_backdate_days`; the payroll period is not locked.
- **Steps:**
  1. Employee submits a correction with type, requested times, a mandatory reason and optional
     evidence.
  2. Server validates the request (times in the past, ordered, type consistent) and creates a
     `PENDING` correction.
  3. Admin reviews with the original events and verification evidence visible side by side.
  4. On approval: create a `CORRECTION` attendance event with `occurred_at` = corrected time, link
     `correction_id`, store `previous_computation`, recompute the day (W-10), audit both the
     decision and the derived-value change, emit `attendance.corrected.v1`.
  5. On rejection: record notes, change nothing.
  6. The employee can cancel their own pending request.
- **Success outcome:** corrected attendance with a complete audit trail showing what changed, who
  approved it and why.
- **Failure paths:** `PERIOD_LOCKED` (use W-21 instead), `STATE_CONFLICT` (already decided),
  `SELF_APPROVAL_NOT_ALLOWED`, backdate limit exceeded, invalid time sequence.
- **Notifications:** the employee on decision; the Admin on a new request.
- **Audit:** `ATTENDANCE` (request, decision, recomputation before/after).
- **Related edge cases:** E-04, E-21, E-22, E-23, E-62, E-89.

### W-10 - Work-hour computation and day classification

- **Trigger:** any attendance event, break close, correction approval, holiday/leave change or the
  `attendance_recompute` sweep.
- **Actors:** system (no user action; results are read by employees and admins).
- **Steps:**
  1. Load the record's events, sessions and breaks for one employee and business date.
  2. Merge overlapping intervals so no time is double counted.
  3. Compute `session_seconds`, subtract unpaid breaks within sessions (or apply the fixed
     automatic break deduction when break tracking is disabled).
  4. Compute `overtime_seconds` from `attendance.overtime_threshold_hours` with the configured
     increment and cap.
  5. Compute `late_minutes` and `early_checkout_minutes` when shift tracking is enabled.
  6. Classify the day (`FULL_DAY`, `HALF_DAY`, `PARTIAL_DAY`, `NONE`) from the thresholds.
  7. Write the record with `computation_version + 1`, a `settings_snapshot` and `computed_at`;
     emit `attendance.record_recalculated.v1`; audit only when values changed.
  8. Reconciliation invariant: the stored values must equal a fresh recomputation.
- **Success outcome:** reproducible, explainable, settings-driven attendance values.
- **Failure paths:** a record that cannot be computed (for example a session with a null start) is
  flagged as an anomaly and surfaced to the Admin rather than silently defaulting to zero.
- **Related edge cases:** E-19, E-89, and the reconciliation rules in `docs/04_BUSINESS_RULES.md`
  section 7.---

## 5. Task Workflows

### W-11 - Task assignment and execution

- **Trigger:** Admin creates a task; employee works on it.
- **Actors:** Admin (`task.create`, `task.assign`, `task.update`), employee (`task.read.self`,
  `task.submit.self`, `task.comment`).
- **Preconditions:** assignees are `ACTIVE` employees; due date, priority and evidence
  requirements are set by the Admin.
- **Steps:**
  1. Admin creates the task with title, description, priority, due date, evidence requirements and
     optionally brief attachments, and assigns one or more employees.
  2. Server validates assignees (active, not already assigned to this task), creates `tasks` +
     `task_assignments` rows, writes audit records and emits `task.assigned.v1`, which notifies
     each assignee.
  3. Employee sees the assignment in My Tasks and opens it (task brief, attachments, due date).
  4. Employee taps Start -> `ASSIGNED` to `STARTED` (server-validated transition).
  5. Employee performs the work and taps Complete, optionally adding a note.
  6. Employee submits for review with a description and/or evidence attachments; the server
     enforces evidence rules, increments `attempt_no`, sets assignment `SUBMITTED`, rolls up the
     task status, audits and emits `task.submitted.v1` to the reviewers.
  7. Comments from either side are appended to the thread; internal admin notes stay internal.
- **Success outcome:** a submitted assignment awaiting review, with attempt history preserved.
- **Failure paths:** `STATE_CONFLICT` for out-of-order actions or double submission;
  `TASK_EVIDENCE_REQUIRED`; inactive assignee at creation (`422`); self-assignment to a task the
  Admin is also to review is allowed but the review itself is governed by W-12.
- **Notifications:** assignee on assignment; reviewers on submission; assignee on reminder and on
  approval/rejection (W-12).
- **Audit:** `TASK` category (create, assign, start, complete, submit).
- **Related edge cases:** E-25, E-26, E-27, E-31, E-32, E-33.

### W-12 - Task review and resubmission

- **Trigger:** an assignment reaches `SUBMITTED`.
- **Actors:** Admin/reviewer with `task.review`; employee with `task.submit.self`.
- **Preconditions:** the submission has no decision; the reviewer is not the assignee.
- **Steps:**
  1. Reviewer opens the review queue (`GET /task-submissions?status=PENDING_DECISION`) and inspects
     the submission with its evidence and the task brief.
  2. Reviewer chooses one of:
     - **Approve** -> submission decision `APPROVED`, assignment `APPROVED`, task rollup updated;
       approval is terminal; evidence retained.
     - **Request resubmission** -> assignment `RESUBMISSION_REQUESTED` with mandatory notes; the
       employee edits and submits again, creating `attempt_no + 1` while preserving the earlier
       attempt and the reviewer's notes.
     - **Reject** -> terminal for that assignment with mandatory notes; further work needs a new
       task or assignment (`tasks.reopen_on_rejection` defaults to false).
  3. Each decision writes `decided_by`/`decided_at`/`decision_notes`, audits the decision, and
     emits the corresponding event (`task.approved.v1`, `task.rejected.v1`,
     `task.resubmission_requested.v1`).
  4. On a task where every assignment is `APPROVED`, the task rollup becomes `COMPLETED` and
     `completed_at` is set.
- **Success outcome:** a decided assignment with full history, or a reopened one for another
  attempt.
- **Failure paths:** `STATE_CONFLICT` on double decision (including two reviewers racing),
  `SELF_REVIEW_NOT_ALLOWED` when the reviewer is the assignee, missing notes on
  reject/resubmission.
- **Notifications:** assignee on every decision.
- **Audit:** `TASK` (decision, notes, before/after status).
- **Related edge cases:** E-25, E-26, E-28, E-29, E-31.

---

## 6. Order Workflows

### W-13 - Order creation and broadcast

- **Trigger:** an order arrives and the Admin registers it.
- **Actors:** Admin (`order.create`, `order.broadcast`).
- **Preconditions:** customer/order identifiers valid; amount is a non-negative decimal.
- **Steps:**
  1. Admin registers the order (customer details, delivery address, items, amount, payment mode)
     and optionally broadcasts it immediately.
  2. Server validates and creates the order with `status = 'BROADCASTED'` when a broadcast was
     requested; otherwise the order is created and awaits an explicit broadcast. Orders are not
     visible to employees until broadcast.
  3. On broadcast: create an `order_broadcasts` round with the resolved audience (`ALL_ACTIVE_EMPLOYEES`,
     `ROLE` or `EXPLICIT`), deactivate the previous round, set `broadcast_at`, append status
     history, audit, and emit `order.broadcasted.v1` which notifies the audience.
  4. Employees with `order.read.available` now see the order in the available list.
- **Success outcome:** a broadcast order visible to the intended employees.
- **Failure paths:** duplicate `order_code` (`409`), invalid payload (`422`), broadcast attempt on
  an order with an active claim (`RULE_VIOLATION`), broadcast with an empty audience (allowed but
  flagged as unclaimed-overdue).
- **Notifications:** broadcast notification to the audience.
- **Audit:** `ORDER` (create, broadcast round, audience).
- **Related edge cases:** E-43, E-44.

### W-14 - Atomic order claim

- **Trigger:** an employee claims an available order.
- **Actors:** employee with `order.claim`.
- **Preconditions:** order is `BROADCASTED` with an active non-expired broadcast including the
  employee; the employee is active; active-claim limit respected; attendance requirement satisfied
  when `orders.claim_requires_active_attendance` is true.
- **Steps:**
  1. Employee taps Claim; the client sends `Idempotency-Key` and disables the control.
  2. Server performs the conditional transition and claim insert exactly as specified in
     `docs/01_ARCHITECTURE.md` section 21.1: `UPDATE orders ... WHERE status = 'BROADCASTED' AND
     current_assignee_id IS NULL`, then `INSERT` the claim protected by the partial unique index on
     active claims.
  3. Winner: set `current_assignee_id`, `claimed_at`, `claim_expires_at` (when auto-release is on),
     append status history, write audit, emit `order.claimed.v1`, notify the employee and the
     Admin.
  4. Loser: `409 CLAIM_ALREADY_TAKEN` with the current order state; the UI shows an explicit
     conflict and refreshes the order and the available list.
  5. Replay with the same idempotency key returns the original success response instead of a
     conflict.
- **Success outcome:** exactly one owner, decided by the database.
- **Failure paths:** `CLAIM_ALREADY_TAKEN`, `ACTIVE_CLAIM_LIMIT_REACHED`,
  `RULE_VIOLATION` (not eligible / expired broadcast / attendance required),
  `IDEMPOTENCY_CONFLICT`, `STATE_CONFLICT`.
- **Notifications:** employee (confirmation), Admin (claim activity).
- **Audit:** `ORDER` (claim, actor, timestamp).
- **Related edge cases:** E-34, E-44, E-45.

### W-15 - Order fulfillment and proof of delivery

- **Trigger:** the holder starts packing.
- **Actors:** holder with `order.update.status.self` and `order.proof.upload`; Admin with
  `order.update.status.any`.
- **Steps:**
  1. Holder moves `CLAIMED -> PACKING` (work started).
  2. Holder packs and moves `PACKING -> PACKED`; when `orders.packing_proof_required` is true, a
     packing proof must be attached first.
  3. Holder moves `PACKED -> READY_FOR_DELIVERY`.
  4. Holder leaves the shop (field work) and moves `READY_FOR_DELIVERY -> OUT_FOR_DELIVERY`.
  5. On delivery, the holder uploads the configured proof (photo, note, optionally location and/or
     customer confirmation) and moves `OUT_FOR_DELIVERY -> DELIVERED`.
  6. Server enforces every transition (allowed successor, holder identity, required proof),
     appends `order_status_history` with from/to, actor, employee, reason and timestamp, audits,
     emits `order.status_changed.v1` / `order.delivered.v1`, closes the active claim as
     `COMPLETED`, and sets `delivered_at`.
- **Success outcome:** a delivered order with evidence and a complete transition history.
- **Failure paths:** `ORDER_INVALID_TRANSITION` (including status skipping when disabled),
  `ORDER_PROOF_REQUIRED` naming the missing requirement, `STATE_CONFLICT` (not the holder, or a
  stale version), `RESOURCE_NOT_FOUND` (not the holder and no admin permission).
- **Notifications:** Admin on delivery and on failure; the employee on Admin-initiated changes.
- **Audit:** `ORDER` for every transition and proof upload.
- **Related edge cases:** E-40, E-46, E-47, E-48.

### W-16 - Order release, abandonment and reassignment

- **Trigger:** the holder cannot fulfill the order; a claim expires; or the Admin reassigns.
- **Actors:** holder (`order.claim` release), Admin (`order.reassign`), system (sweeper).
- **Steps:**
  1. Holder-initiated: `POST /orders/{id}/release` with a reason -> claim closes as `RELEASED`,
     order moves to `REASSIGNED`, and returns to the pool via a new broadcast round when
     `orders.allow_rebroadcast_after_release` is true.
  2. System-initiated abandonment: the `order_claim_sweeper` finds claims past `claim_expires_at`
     and, when `orders.auto_release_on_timeout` is true, closes them as `EXPIRED` and returns the
     order to the pool, notifying the employee and the Admin. When auto-release is disabled, the
     claim stays and the order is surfaced to the Admin as overdue.
  3. Admin reassignment: `POST /orders/{id}/reassign` with a reason and optionally a target
     employee. With a target, the previous claim closes as `REASSIGNED` and a new claim is created
     atomically for the target (still protected by the active-claim unique index). Without a
     target, the order returns to the pool.
  4. `reassign_count` increments and is capped; exceeding the cap requires an explicit override and
     is audited.
  5. Prior responsibility is never erased: the previous claim row, status history and audit records
     remain.
- **Success outcome:** the order is back in the pool or with a new owner, with a visible chain of
  responsibility.
- **Failure paths:** `RULE_VIOLATION` (status not reassignable, e.g. `OUT_FOR_DELIVERY`),
  missing reason when required, cap exceeded, `RESOURCE_NOT_FOUND` for a non-holder without admin
  permission.
- **Notifications:** previous holder, new holder (when applicable), Admin.
- **Audit:** `ORDER` (release, expiration, reassignment, cap override).
- **Related edge cases:** E-35, E-36, E-37, E-38, E-39.

### W-17 - Order cancellation and failure

- **Trigger:** the order cannot proceed (customer cancelled, items unavailable, delivery failed).
- **Actors:** Admin (`order.cancel`); holder for failure (`order.update.status.self`).
- **Steps:**
  1. Cancellation: Admin submits `POST /orders/{id}/cancel` with a reason. Server verifies the
     current status is in `orders.cancel_allowed_statuses`, closes the active claim as `CANCELLED`,
     sets `cancelled_at` and `cancel_reason`, appends status history, audits, and emits
     `order.cancelled.v1`.
  2. Failure: the holder (or an Admin) submits `POST /orders/{id}/fail` with a reason code and
     reason; the claim closes as `FAILED`, `failed_at`/`failure_reason` are set, and the Admin is
     notified so a decision (re-broadcast, cancel, refund) can be made.
  3. Both are terminal; no further transitions are possible on the order itself.
- **Success outcome:** a terminal order state with an explanation and no orphaned claim.
- **Failure paths:** `RULE_VIOLATION` when the status is not cancellable (for example after
  delivery) or when a reason is missing, `STATE_CONFLICT` on a raced transition.
- **Notifications:** the holder and the Admin.
- **Audit:** `ORDER` (cancellation or failure with reason and actor).
- **Related edge cases:** E-41, E-42, E-46, E-47.---

## 7. Leave Workflows

### W-18 - Leave application and decision

- **Trigger:** employee requests time off.
- **Actors:** employee (`leave.apply.self`), Admin (`leave.approve`).
- **Preconditions:** leave module enabled; the leave type is active; dates are within policy.
- **Steps:**
  1. Employee selects a leave type and dates (optionally a half day), adds a reason and an
     attachment when required.
  2. Server computes `total_days` from working days (excluding weekly offs and holidays unless
     configured), validates advance/backdate limits, consecutive-day limits, attachment rules and
     overlap with existing pending/approved leave.
  3. Server locks the balance row and, when sufficient (or when negative balances are allowed),
     posts a `PENDING_HOLD` movement and creates the request as `PENDING`.
  4. Admin reviews the request with the employee's balance and history visible.
  5. On approval: convert the hold to `USAGE`, increment `used_days`, decrement `pending_days`, mark
     the covered attendance dates `ON_LEAVE`, audit, and emit `leave.approved.v1`.
  6. On rejection: release the hold, record notes, audit, emit `leave.rejected.v1`.
  7. On request-modification: set `MODIFICATION_REQUESTED`, keep the hold, notify the employee, who
     may edit and resubmit (back to `PENDING`) or cancel.
- **Success outcome:** a decided leave request with a balance that always matches its ledger.
- **Failure paths:** `LEAVE_OVERLAP`, `LEAVE_BALANCE_INSUFFICIENT`, `SELF_APPROVAL_NOT_ALLOWED`,
  attachment required, advance/backdate limit exceeded, `CONFLICT_DUPLICATE` from the exclusion
  constraint under a race, `IDEMPOTENCY_CONFLICT`.
- **Notifications:** Admin on request; employee on decision.
- **Audit:** `LEAVE` (apply, hold, decision, balance movement).
- **Related edge cases:** E-49 to E-60.

### W-19 - Leave cancellation and balance correction

- **Trigger:** plans change, or a balance needs correction.
- **Actors:** employee (`leave.cancel.self`), Admin (`leave.cancel.any`, `leave.balance.manage`).
- **Steps:**
  1. Cancel a pending request: release the hold, mark `CANCELLED`, audit.
  2. Cancel an approved request: verify the covered dates are not inside a locked payroll period;
     post the reversal movement, decrement `used_days`, reclassify the affected attendance dates and
     recompute them, audit, and emit `leave.cancelled.v1`.
  3. Balance correction: Admin posts an adjustment with days (signed) and a reason; the service
     locks the balance row, writes an `ADJUSTMENT` ledger movement and updates the balance. The
     result may not drop below `used_days` and may not be negative unless
     `leaves.allow_negative_balance` is true.
  4. Accrual and carry-forward (when configured) are applied by the `leave_accrual` job with their
     own dated movements so the balance history always explains the net change.
- **Success outcome:** a correct balance with a movement trail for every change.
- **Failure paths:** `PERIOD_LOCKED` for cancellations inside a locked period (use a balance
  adjustment plus a ledger adjustment instead), `RULE_VIOLATION` when the adjustment would make the
  balance inconsistent.
- **Notifications:** employee on cancellation by an Admin; Admin on employee cancellation.
- **Audit:** `LEAVE` (cancellation, reversal, adjustment, accrual, carry-forward, expiry).
- **Related edge cases:** E-51, E-53, E-54, E-55, E-60, E-62.

---

## 8. Financial Workflows

### W-20 - Advance issuance and recovery

- **Trigger:** employee requests an advance; payroll later recovers it.
- **Actors:** Admin (`advance.create`, `advance.approve`); the employee is the beneficiary.
- **Steps:**
  1. Admin records the advance (amount, reason, repayment mode, installments).
  2. Server checks `advance.max_outstanding_percent_of_salary` against the employee's monthly gross
     equivalent, validates installment arithmetic (`count` x `amount` = total, with the last
     installment absorbing rounding) and creates the advance as `PENDING_APPROVAL` when approval is
     required.
  3. On approval: post an `ADVANCE_ISSUED` ledger entry (DEBIT), generate installments, set the
     advance `OUTSTANDING`, audit, and emit `payroll.advance_issued.v1`. Approval must not be
     performed by the beneficiary.
  4. Payroll recovery (W-22): the deduction is `min(outstanding, next installment,
     max_percent_recovered_per_month * gross)`; it reduces `outstanding_amount`, advances the
     installment status, and closes the advance at zero. No separate repayment ledger entry is
     posted for payroll recovery (double-counting guard).
  5. Cash repayment (when allowed): post an `ADVANCE_REPAYMENT` entry and reduce the outstanding
     amount; it may never exceed the outstanding amount.
  6. Write-off: an Admin with `ledger.entry.adjust` closes the advance as `WRITTEN_OFF` with a
     reason, posting an adjustment so the books reflect the decision.
- **Success outcome:** a tracked advance that reduces correctly and closes exactly once.
- **Failure paths:** `ADVANCE_LIMIT_EXCEEDED`, `RULE_VIOLATION` for over-repayment, self-approval,
  `PERIOD_LOCKED` for retroactive recovery inside a locked period, `IDEMPOTENCY_CONFLICT`.
- **Notifications:** employee on approval; Admin on outstanding/overdue advances.
- **Audit:** `FINANCIAL` (issue, approval, repayment, write-off, outstanding changes).
- **Related edge cases:** E-65, E-66, E-67, E-68, E-71.

### W-21 - Manual financial adjustment and reversal

- **Trigger:** a correction, bonus, deduction or error needs to be recorded.
- **Actors:** Admin (`ledger.entry.create`, `ledger.entry.adjust`).
- **Preconditions:** `ledger.allow_manual_entries`; `ledger.require_reason` for the reason field;
  the target period is not locked.
- **Steps:**
  1. Admin posts an entry (type, direction, amount, business date, optional period, reason,
     reference) with an `Idempotency-Key`.
  2. Server validates the amount, direction, permitted manual entry types, period lock state and
     reason; appends the entry; updates any affected cached aggregate (for example advance
     outstanding); audits; and emits `payroll.ledger_entry_created.v1`.
  3. To correct an existing entry, the Admin posts a reversal: a new `REVERSAL` entry referencing
     the original with the opposite direction. The original row is never modified.
  4. An entry may be reversed once; a second reversal is refused.
  5. Period-tagged entries are picked up by the next payroll run for that period (or by the current
     open period when the original period is locked).
- **Success outcome:** an append-only financial record where every change is traceable to an actor
  and a reason.
- **Failure paths:** `PERIOD_LOCKED`, `ALREADY_REVERSED`, `VALIDATION_ERROR`,
  `IDEMPOTENCY_CONFLICT`, `PERMISSION_DENIED`.
- **Notifications:** the affected employee when policy allows self-view; otherwise none.
- **Audit:** `FINANCIAL` with before/after balances where relevant.
- **Related edge cases:** E-62, E-68, E-69.

### W-22 - Payroll run: compute, finalize, lock, pay

- **Trigger:** the payroll period ends (or the Admin starts the run manually).
- **Actors:** Admin, with separated permissions: `salary.compute`, `salary.finalize`,
  `payroll.lock`, `payroll.unlock`, `payroll.pay`.
- **Steps:**
  1. **Create run** for the period (one per period, DB-6).
  2. **Compute:** for each active employee with an effective compensation row, resolve attendance
     and leave inputs, resolve the working-day denominator, compute day credits, gross, overtime,
     deductions (including advance recovery) and net, write `inputs_snapshot`,
     `calculation_breakdown` and a `payroll_rule_snapshots` row, and set the run `COMPUTED`.
     Employees without a compensation row are skipped and reported with a reason. The run may be
     re-computed while it remains `DRAFT`/`COMPUTED`.
  3. **Finalize:** refuse while attendance corrections for the period are pending (unless an
     explicit audited override is used); make every salary record immutable; set
     `finalized_by`/`finalized_at`.
  4. **Lock:** close the period for attendance corrections and leave changes; record `locked_at`.
  5. **Mark paid:** post a `PAYMENT_MADE` ledger entry per employee, set `paid_at`, and set the run
     `PAID`. Payment must not precede finalization (`payroll.require_finalize_before_pay`).
  6. **Unlock (exception):** an Admin with `payroll.unlock` may reopen a finalized-but-unpaid run
     with a mandatory reason; unlocking is audited and notifies the reviewer.
  7. **Post-payroll correction:** a late attendance correction inside a finalized/locked period is
     never applied to the historical record; an adjustment entry in the current open period carries
     the effect forward (BR-4.10).
  8. **Month-end specifics:** business-date attribution keeps a night shift in the period where it
     started; no day is split or double counted.
- **Success outcome:** an auditable payroll period that can be explained line by line, with
  historical records that never change after finalization.
- **Failure paths:** `PERIOD_LOCKED`, `CONFLICT_DUPLICATE` (run already exists), missing
  compensation, open corrections, insufficient permission, `STATE_CONFLICT` on raced transitions.
- **Notifications:** finalization and payment notifications per policy; employees may see their
  record only when granted `salary.read.self` (decision 25).
- **Audit:** `FINANCIAL` for compute, finalize, lock, unlock, pay, plus every derived change with
  the rule snapshot hash.
- **Related edge cases:** E-51, E-61, E-62, E-63, E-64, E-70, E-71, E-72, E-73, E-88.

---

## 9. Service and Support Workflows

### W-23 - Complaint intake and resolution

- **Trigger:** an employee raises a concern, or an Admin records an operational/disciplinary issue.
- **Actors:** employee (`complaint.create.self`, `complaint.comment`), Admin
  (`complaint.manage`, `complaint.resolve`, `complaint.close`).
- **Steps:**
  1. Employee submits a complaint with category, title, description, optional evidence and
     optionally a subject employee (only when `complaints.employee_may_reference_employee` is true).
     Priority and visibility default from the category or settings.
  2. Server validates and creates the complaint as `OPEN`, computes `sla_due_at` from
     `complaints.sla_hours`, notifies the Admin, and audits (`COMPLAINT`).
  3. Admin triages: `OPEN -> IN_REVIEW` (optionally assigning a reviewer).
  4. Review: may move to `ACTION_REQUIRED` (with a reason) or straight to `RESOLVED` with a
     mandatory resolution summary.
  5. `RESOLVED -> CLOSED` closes the thread; a disputed resolution may return to `IN_REVIEW` with a
     reason.
  6. `REJECTED` is terminal and requires a rejection reason.
  7. Comments are appended; internal comments and internal notes are never shown to the raiser.
     Visibility rules (BR-4.11) govern who can see what at every step.
- **Success outcome:** a resolved or explicitly rejected complaint with a complete, appropriately
  private history.
- **Failure paths:** `RESOURCE_NOT_FOUND` for out-of-visibility access (never a leak),
  `RULE_VIOLATION` for missing reasons or invalid transitions, comment on a closed complaint
  (unless allowed).
- **Notifications:** Admin on creation; raiser on status changes and on resolution when visibility
  permits.
- **Audit:** `COMPLAINT` (create, assignment, status changes, resolution, visibility changes,
  internal notes).
- **Related edge cases:** E-74, E-75, E-76.

### W-24 - Notification delivery

- **Trigger:** any domain event mapped to a notification.
- **Actors:** system; users read their own notifications.
- **Steps:**
  1. A service writes its domain event to `domain_events` inside the business transaction.
  2. `outbox_dispatch` claims undispatched events (`FOR UPDATE SKIP LOCKED`) and invokes handlers
     idempotently on `event_id`.
  3. The `notifications` handler resolves recipients from the event (assignee, holder, raiser,
     audience, Admin group), applies per-user preferences and quiet hours (never suppressing
     security events), and creates one `notifications` row per recipient.
  4. For each enabled channel, a `notification_deliveries` row is created and the adapter is
     invoked: `IN_APP` (always), `WEB_PUSH` (VAPID), and `EMAIL`/`SMS`/`WHATSAPP` as
     `NOT_CONFIGURED` until providers are integrated.
  5. Failed deliveries retry with backoff up to `notifications.max_delivery_attempts`; a persistent
     failure marks the delivery `FAILED` and, for web push, increments the subscription failure
     count and deactivates it when it exceeds the threshold.
  6. The client shows the unread count, lists notifications with cursor pagination, and marks them
     read individually or in bulk.
- **Success outcome:** users are informed of relevant events; a delivery failure never affects
  business state.
- **Failure paths:** provider unavailable (retry then fail), expired push subscription
  (deactivate), duplicate event dispatch (idempotent handler produces no duplicate notification).
- **Audit:** not required for delivery itself; security-relevant notifications are audited at their
  source.
- **Related edge cases:** E-77, E-78.

### W-25 - Reporting and export

- **Trigger:** Admin opens a report or requests an export.
- **Actors:** Admin with the relevant `report.*` permission; `report.export` for files.
- **Steps:**
  1. Client reads `GET /reports/catalog` to discover available reports, filters and required
     permissions.
  2. Admin selects a report and a date range within `reports.max_range_days`; the server validates
     the range and filters.
  3. The report query runs in a read-only transaction against the documented views
     (`docs/02_DATABASE.md` section 20), applies the caller's scope (an employee-scoped report
     filters to self), excludes sensitive fields by default (`reports.include_sensitive_fields`),
     and computes totals with exact decimal arithmetic.
  4. For an export, the server queues a `report_exports` job with the validated parameters, streams
     rows to object storage in the requested format, records `row_count`, and exposes the artifact
     through an authorized download URL that expires per `files.export_retention_days`.
  5. Report numbers must reconcile with the underlying records; the reconciliation rules are
     listed in `docs/04_BUSINESS_RULES.md` section 7 and validated in
     `docs/09_TEST_PLAN.md` section 8.
- **Success outcome:** a report or export whose numbers match the source data and respect
  permissions.
- **Failure paths:** range too large (`422`), format not enabled (`422`), rate limited (`429`),
  export job failure (status `FAILED` with an error message and no partial file exposed), unknown
  filter (`422`).
- **Notifications:** the requester is notified when an export completes or fails.
- **Audit:** `report.export` includes report type, parameters, row count and actor (report reads
  may be audited when `audit.log_reads` is enabled).
- **Related edge cases:** report totals are covered by the reconciliation rules; E-83 applies to
  scoping.

### W-26 - Settings change

- **Trigger:** the client's policy changes (thresholds, geofence, QR validity, claim timeout, pay
  rules and so on).
- **Actors:** Admin with `settings.update` (history visible with `settings.read.history`).
- **Steps:**
  1. Client reads `GET /settings/schema` and renders a form from the registry (all keys in
     `docs/04_BUSINESS_RULES.md` section 3), grouping provisional items and marking them.
  2. Admin changes one or more values and supplies a mandatory reason.
  3. Server validates every change against the registry (type, bounds, allowed values) atomically;
     one invalid value rejects the whole request.
  4. Server writes the new values with an incremented `version`, appends `business_setting_history`
     rows, audits with before/after and reason, emits `settings.changed.v1`, and invalidates the
     per-request settings cache.
  5. If a change affects already-computed attendance for open dates, the response warns which
     dates are affected and offers a bounded, audited recomputation; the system never rewrites
     history silently.
  6. Changes affecting payroll apply to future computations only; finalized records keep their
     snapshots.
- **Success outcome:** a traceable policy change with no hidden recomputation.
- **Failure paths:** unknown key, type/range violation, missing reason, concurrent edits (both
  changes recorded in history with versions; the last write wins deterministically).
- **Notifications:** optional Admin notification on sensitive setting changes.
- **Audit:** `SETTINGS` with key, old value, new value, actor, reason and version.
- **Related edge cases:** E-61, E-85, E-89.

### W-27 - Role and permission management

- **Trigger:** the Admin needs a new role composition or assigns roles to a user.
- **Actors:** Admin with `role.manage` / `employee.manage.roles`.
- **Steps:**
  1. Admin reads roles and the permission catalog (`GET /roles`, `GET /permissions`).
  2. To create a role: submit a code, name and permission set; server validates codes against the
     catalog and rejects unknown codes.
  3. To change a role: submit the new permission set with a reason; the server enforces the
     escalation guards (section 8 of `docs/05_PERMISSIONS.md`), prevents weakening `ADMIN` below the
     catalog minimum, and refuses to delete system roles or roles in use.
  4. To assign roles: submit `PUT /users/{id}/roles`; the server refuses self-escalation and
     `LAST_ADMIN_PROTECTED` violations.
  5. Every change is audited with before/after permission code lists and takes effect for the
     affected user on their next request.
- **Success outcome:** accurate authorization data with a full change history.
- **Failure paths:** `VALIDATION_ERROR` (unknown permission code), `RULE_VIOLATION` (system role,
  role in use, last-admin protection, self-escalation), `CONFLICT_DUPLICATE` (role code exists).
- **Notifications:** optional Admin notification for role changes.
- **Audit:** `PERMISSION` category with before/after.

### W-28 - Audit inspection

- **Trigger:** the Admin investigates who changed what, or exports evidence.
- **Actors:** Admin with `audit.read`; export with `audit.export`.
- **Steps:**
  1. Admin queries `GET /audit-logs` with filters (category, action, entity, actor, date range)
     using cursor pagination.
  2. The response includes actor, action, entity, before/after values, reason, timestamp, request id
     and origin, already redacted of secrets and sensitive values.
  3. The Admin may export a filtered set as a file, which is queued and audited.
  4. Audit records cannot be modified or deleted through the API or by the application role.
- **Success outcome:** a complete, trustworthy investigation trail.
- **Failure paths:** `403` without `audit.read`; oversized export is rate limited.
- **Audit:** when `audit.log_reads` is enabled, reads and exports are themselves audited.

### W-29 - File upload and authorized download

- **Trigger:** a user attaches evidence (task, order, leave, complaint, correction) or the system
  produces an export.
- **Actors:** any user with `file.upload`; readers authorized by the relying entity.
- **Steps:**
  1. Client uploads via `POST /files` with the intended purpose.
  2. Server validates size (`files.max_upload_mb`), MIME allow-list, magic-byte signature, computes
     a SHA-256 checksum, stores the object privately, creates the `files` row and audits the upload.
  3. The module links the file: task evidence to a submission, order proof to a purpose, leave
     attachment to the request, complaint evidence to the complaint, correction evidence to the
     correction. Attachment counts are capped.
  4. Download: the client requests `GET /files/{id}/url`; the server authorizes the actor against
     the relying entity (or ownership, or `file.read.all`) and returns a short-lived presigned URL;
     issuance is audited.
  5. Deletion is a soft delete; a file referenced by a submitted record cannot be deleted.
- **Success outcome:** private, validated, authorized file handling with an access trail.
- **Failure paths:** `FILE_TOO_LARGE`, `UNSUPPORTED_FILE_TYPE`, `STORAGE_UNAVAILABLE`,
  `RESOURCE_NOT_FOUND` (unauthorized access is indistinguishable from a missing file),
  `RULE_VIOLATION` (delete of a referenced file).
- **Audit:** `FILE` (upload, presigned URL issuance, delete).
- **Related edge cases:** E-79, E-80, E-81, E-82.

---

## 10. Workflow Coverage and Cross-Checks (Agent 1)

| Check | Result |
| --- | --- |
| Every product-scope module appears in at least one workflow | Yes - the index in section 2 covers authentication, users, RBAC, dashboards (via W-24/W-25 plus the report/dashboard summary), attendance, breaks, location verification and QR (W-05), tasks, submissions/approval, orders, broadcasting, claiming, fulfillment, leave, ledger, payroll, advances, complaints, notifications, reports/export, attachments, audit and settings |
| Every workflow names the permissions it needs | Yes - each workflow lists permissions, and `docs/05_PERMISSIONS.md` section 9 verifies both directions |
| Every workflow maps to documented endpoints | Yes - `docs/03_API_CONTRACT.md` section 21 |
| Every workflow's rules are specified | Yes - each step references `docs/04_BUSINESS_RULES.md` sections and rule identifiers |
| Every workflow's failure behavior is defined | Yes - each workflow lists failure paths, and section 5 of the business rules document defines 90 edge cases |
| Concurrency-sensitive workflows are explicit | Yes - W-14 (atomic claim), W-05/W-06 (duplicate attendance events), W-09 (concurrent correction approval), W-12 (concurrent review), W-18/W-19 (balance locks), W-21/W-22 (financial integrity) |
| No workflow depends on frontend enforcement | Yes - all enforcement points are server-side or database constraints |

Unresolved items affecting workflows: the 25 `CLIENT_DECISION_REQUIRED` items in
`docs/04_BUSINESS_RULES.md` section 10. The workflows with the most client-dependent behavior are
W-05/W-06/W-07 (verification and break policy), W-08/W-09 (missing checkout and corrections),
W-14/W-15/W-16 (claiming, proof and reassignment) and W-22 (payroll semantics).