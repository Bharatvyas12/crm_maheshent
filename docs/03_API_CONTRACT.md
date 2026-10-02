# 03 - API Contract

| Field | Value |
| --- | --- |
| Document owner | Agent 1 - Architect / Tech Lead |
| Status | Baseline (implementation-ready) |
| Version | 1.0 |
| Source-of-truth rank | 7 |
| Base path | `/api/v1` |
| Consumers | Agent 2 (implements), Agent 3 (integrates), Agent 4/5 (verify) |

Cross-cutting conventions (status codes, error body, validation, pagination, filtering, sorting,
idempotency, rate limiting, versioning, headers) are defined in
`docs/01_ARCHITECTURE.md` section 13 and are not repeated here. This document defines the
endpoint surface and its semantics.

Where an endpoint's behavior depends on a configurable value, the setting key is named. Where
behavior is not yet confirmed by the client, the endpoint returns the provisional behavior and
the `CLIENT_DECISION_REQUIRED` reference is stated.

---

## 1. Reading This Document

Each module section lists endpoints in a table:

- **Auth** - required permission code from `docs/05_PERMISSIONS.md`. `public` means no session
  required; `authenticated` means any valid session.
- **Request** - body/query shape at the level needed to implement; full field-level validation
  rules live in `docs/04_BUSINESS_RULES.md` and the Pydantic schemas Agent 2 writes.
- **Returns** - success status and body summary (resource shapes are defined in section 3).
- **Errors** - the module-specific error codes in addition to the generic set.

Naming: resource paths are plural nouns; actions that are not CRUD are `POST` sub-resources with
a verb. All ids are UUIDs. Timestamps in responses are UTC RFC 3339; business dates are
`YYYY-MM-DD`.

---

## 2. Authentication and Session Endpoints

| Method | Path | Auth | Request | Returns | Errors |
| --- | --- | --- | --- | --- | --- |
| POST | `/auth/login` | public | `{ "username", "password" }` (username accepts username or email) | `200` + `{ user, employee, roles, permissions, settings }`, sets `session` and `csrf_token` cookies | `INVALID_CREDENTIALS`, `ACCOUNT_LOCKED`, `ACCOUNT_DISABLED`, `RATE_LIMITED`, `VALIDATION_ERROR` |
| POST | `/auth/logout` | authenticated | - | `204`, clears cookies | `CSRF_INVALID` |
| GET | `/auth/me` | authenticated | - | `200` + same session payload as login | `SESSION_EXPIRED` |
| POST | `/auth/change-password` | authenticated | `{ "current_password", "new_password" }` | `204`; revokes all other sessions | `INVALID_CREDENTIALS` (wrong current password), `VALIDATION_ERROR` (policy) |
| POST | `/auth/reset-password` | `employee.manage.credentials` | `{ "user_id", "reason" }` | `201` + `{ "user_id", "reset_token", "expires_at" }` (token returned once, never logged) | `RESOURCE_NOT_FOUND`, `PERMISSION_DENIED` |
| GET | `/auth/sessions` | authenticated | - | `200` + the caller's active sessions (id, created_at, last_seen_at, ip, user_agent, is_current) | - |
| DELETE | `/auth/sessions/{session_id}` | authenticated (own session) | - | `204` | `RESOURCE_NOT_FOUND` (not the caller's session) |

Notes:

- The `settings` block in the login/session payload contains only employee-relevant,
  non-sensitive settings (business timezone, currency, break types enabled, QR/GPS requirement
  flags, attendance thresholds needed for display). It never contains financial policy used for
  computation.
- `permissions` in the payload is a convenience for navigation. The backend re-checks every
  protected operation; a stale or forged payload grants nothing.
- Password reset revokes all sessions for the target user and sets `must_change_password = true`.

---

## 3. Core Resource Shapes (abbreviated)

Full field lists are the Pydantic schemas; these shapes fix naming and semantics so the frontend
and backend agree.

**`User`**: `id`, `username`, `email`, `status`, `last_login_at`, `must_change_password`,
`roles[]`, `created_at`.

**`Employee`**: `id`, `user_id`, `employee_code`, `full_name`, `phone`, `email`,
`date_of_joining`, `date_of_exit`, `employment_status`, `employment_type`, `department`,
`designation`, `manager_employee_id`, `emergency_contact_name`, `emergency_contact_phone`,
`address_line`, `created_at`, `updated_at`. Sensitive fields (`bank_account_name`,
`bank_account_number` masked, `bank_ifsc`) are returned only with `employee.read.sensitive`.

**`AttendanceRecord`**: `id`, `employee_id`, `business_date`, `status`, `day_classification`,
`first_check_in_at`, `last_check_out_at`, `worked_seconds`, `worked_hours`, `break_seconds`,
`unpaid_break_seconds`, `overtime_seconds`, `late_minutes`, `early_checkout_minutes`,
`is_open`, `is_corrected`, `computed_at`, `version`, plus `next_allowed_action` (see 4.1).

**`TaskAssignment`**: `id`, `task` (embedded summary), `employee_id`, `status`, `assigned_at`,
`started_at`, `completed_at`, `submitted_at`, `reviewed_at`, `reviewer_id`, `review_decision`,
`review_notes`, `attempt_count`, `due_at`, `version`, `allowed_transitions[]`.

**`Order`**: `id`, `order_code`, `customer_name`, `customer_phone`, `delivery_address`,
`delivery_notes`, `item_summary`, `item_count`, `order_amount`, `currency`, `payment_mode`,
`status`, `current_assignee_id`, `claimed_at`, `claim_expires_at`, `reassigned_at`,
`reassign_count`, `pod_required`, timestamps per milestone, `version`, `allowed_transitions[]`.

**`Leave`**: `id`, `employee_id`, `leave_type`, `start_date`, `end_date`, `total_days`,
`is_half_day`, `half_day_period`, `reason`, `status`, `applied_at`, `decided_by`, `decided_at`,
`decision_notes`, `attachment`, `version`.

**`SalaryRecord`**: `id`, `employee_id`, `period_year`, `period_month`, `currency`,
`compensation_type`, `base_rate`, day counts, `payable_days`, `gross_amount`,
`overtime_amount`, `bonus_amount`, deductions (`leave_deduction`, `late_deduction`,
`advance_deduction`, `other_deduction`, `total_deductions`), `net_amount`, `status`,
`rule_snapshot_hash`, `computed_at`, `finalized_at`, `paid_at`, `version`.

Money fields are decimal strings (section 13.1 of the architecture document). Durations are
`*_seconds` integers with a convenience `*_hours` decimal string.

Convention: resources that participate in a state machine expose `allowed_transitions[]` so the
frontend never hard-codes lifecycle rules; the server remains authoritative and re-validates
every transition.

---

## 4. Attendance Module

### 4.1 Endpoints

| Method | Path | Auth | Request | Returns | Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/attendance/me/today` | `attendance.read.self` | - | `200` + today's `AttendanceRecord` (may be `NOT_MARKED` placeholder) + `next_allowed_action` | - |
| POST | `/attendance/check-in` | `attendance.checkin.self` | `{ "latitude", "longitude", "accuracy_meters", "location_captured_at", "qr_token"?, "client_time"?, "device_info"? }` + `Idempotency-Key` | `201` + `AttendanceRecord` + `verification` summary | `RULE_VIOLATION` (state/verification), `STATE_CONFLICT` (already checked in), `VALIDATION_ERROR`, `RATE_LIMITED`, `IDEMPOTENCY_CONFLICT` |
| POST | `/attendance/check-out` | `attendance.checkout.self` | same evidence fields as check-in (requirement governed by `attendance.checkout_verification_mode`) | `200` + `AttendanceRecord` | `STATE_CONFLICT` (no open session), `RULE_VIOLATION` (verification failed) |
| POST | `/attendance/break/start` | `attendance.break.self` | `{ "break_type_id" }` + `Idempotency-Key` | `201` + break session | `STATE_CONFLICT` (break already open), `RULE_VIOLATION` (no open work session, max break exceeded) |
| POST | `/attendance/break/end` | `attendance.break.self` | `Idempotency-Key` | `200` + break session | `STATE_CONFLICT` (no open break) |
| GET | `/attendance/me` | `attendance.read.self` | `from`, `to`, `page`, `page_size` | `200` + paginated `AttendanceRecord` | `VALIDATION_ERROR` |
| GET | `/attendance/me/summary` | `attendance.read.self` | `from`, `to` (defaults: current period) | `200` + totals: present/half/partial/absent/leave days, worked/break/overtime seconds, late minutes | `VALIDATION_ERROR` |
| GET | `/attendance` | `attendance.read.all` | `employee_id`, `department`, `status`, `day_classification`, `from`, `to`, `q`, `sort`, `page`, `page_size` | `200` + paginated `AttendanceRecord` | `VALIDATION_ERROR` |
| GET | `/attendance/{record_id}` | `attendance.read.all` or self | - | `200` + `AttendanceRecord` | `RESOURCE_NOT_FOUND` |
| GET | `/attendance/{record_id}/events` | `attendance.read.all` or self | - | `200` + ordered `attendance_events` with linked session/break ids | `RESOURCE_NOT_FOUND` |
| GET | `/attendance/{record_id}/verifications` | `attendance.read.all` | - | `200` + verification evidence rows | `RESOURCE_NOT_FOUND` |
| POST | `/attendance/{record_id}/recompute` | `attendance.manage` | `{ "reason" }` | `200` + recomputed `AttendanceRecord` + audit reference | `RULE_VIOLATION` (period locked), `RESOURCE_NOT_FOUND` |
| GET | `/break-types` | `attendance.read.self` | `include_inactive` (`attendance.config.manage` only) | `200` + active break types | - |
| POST | `/break-types` | `attendance.config.manage` | `{ "code", "name", "is_paid", "max_minutes", "requires_approval", "counts_toward_max_per_day" }` | `201` + break type | `CONFLICT_DUPLICATE`, `VALIDATION_ERROR` |
| PATCH | `/break-types/{id}` | `attendance.config.manage` | partial break type | `200` + break type | `RESOURCE_NOT_FOUND`, `VALIDATION_ERROR` |
| GET | `/holidays` | `attendance.read.self` | `year` | `200` + holidays for the year | `VALIDATION_ERROR` |
| POST | `/holidays` | `attendance.config.manage` | `{ "holiday_date", "name", "is_paid", "is_working_day" }` | `201` + holiday | `CONFLICT_DUPLICATE`, `VALIDATION_ERROR` |
| DELETE | `/holidays/{id}` | `attendance.config.manage` | - | `204` | `RESOURCE_NOT_FOUND` |
| POST | `/attendance/qr-tokens` | `attendance.qr.generate` | `{ "purpose"? }` | `201` + `{ "id", "qr_payload", "nonce", "expires_at", "rotation_seconds" }` | `PERMISSION_DENIED` |
| GET | `/attendance/qr-tokens/current` | `attendance.qr.generate` | `purpose` | `200` + the current non-expired token, or `404` when none is valid (shop display calls this to rotate) | `RESOURCE_NOT_FOUND` |

### 4.2 Verification request semantics

- `latitude`/`longitude` are required only when the configured
  `attendance.verification_mode` includes GPS (`GPS`, `GPS_AND_QR`, `GPS_OR_QR`).
- `qr_token` is required only when the mode includes QR. The value is the opaque payload scanned
  from the shop display; the server hashes it and matches `attendance_qr_tokens.token_hash` by
  `nonce`.
- `location_captured_at` is the client's fix time and is validated for freshness against
  `attendance.location_max_age_seconds`; a stale fix is rejected with
  `failure_code = LOCATION_STALE`.
- The server never trusts client-side verification results. It recomputes distance from the
  configured geofence, compares accuracy against `attendance.gps_accuracy_max_m`, and validates
  the QR token's existence, expiry, single-use state and purpose.
- The response includes an explicit `verification` object: `{ "method", "result", "distance_meters",
  "accuracy_meters", "geofence_radius_meters", "qr_result", "failure_code", "failure_reason" }`,
  so the UI can explain precisely why a check-in was rejected.
- Failed attempts are recorded in `attendance_verifications` and are rate limited; they never
  create an attendance event.

### 4.3 Correction endpoints

| Method | Path | Auth | Request | Returns | Errors |
| --- | --- | --- | --- | --- | --- |
| POST | `/attendance/corrections` | `attendance.correct.request.self` | `{ "attendance_record_id", "correction_type", "requested_check_in_at"?, "requested_check_out_at"?, "requested_break_start_at"?, "requested_break_end_at"?, "reason", "attachment_file_id"? }` | `201` + correction (`PENDING`) | `RULE_VIOLATION` (backdate limit, already pending), `VALIDATION_ERROR` |
| GET | `/attendance/corrections/mine` | `attendance.correct.request.self` | `status`, `page` | `200` + paginated corrections | - |
| GET | `/attendance/corrections` | `attendance.correct.approve` | `employee_id`, `status`, `from`, `to`, `page` | `200` + paginated corrections | - |
| POST | `/attendance/corrections/{id}/approve` | `attendance.correct.approve` | `{ "decision_notes"?, "adjust_to"?: {...} }` | `200` + correction + updated `AttendanceRecord` | `STATE_CONFLICT` (already decided), `RULE_VIOLATION` (payroll period locked), `RESOURCE_NOT_FOUND` |
| POST | `/attendance/corrections/{id}/reject` | `attendance.correct.approve` | `{ "decision_notes" }` | `200` + correction | `STATE_CONFLICT`, `RESOURCE_NOT_FOUND` |
| POST | `/attendance/corrections/{id}/cancel` | `attendance.correct.request.self` (own, pending) | `{ "reason" }` | `200` + correction | `STATE_CONFLICT`, `RESOURCE_NOT_FOUND` |

Approval creates a `CORRECTION` attendance event, recomputes the record, and audits both the
correction decision and the recomputation (`before`/`after` of derived values).

### 4.4 Attendance state machine exposed to clients

`next_allowed_action` and `allowed_transitions[]` are computed server-side:

- `NOT_MARKED` -> `CHECK_IN`
- `PRESENT` with open session -> `CHECK_OUT`, `START_BREAK` (when no break is open)
- `PRESENT` with open break -> `END_BREAK`, `CHECK_OUT`
- `PRESENT` closed -> `REQUEST_CORRECTION`
- `INCOMPLETE` -> `REQUEST_CORRECTION`
- `ON_LEAVE` / `HOLIDAY` / `WEEKLY_OFF` -> none (correction may still be requested through the
  correction endpoint when policy allows)---

## 5. Directory (User / Employee Management) Module

| Method | Path | Auth | Request | Returns | Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/me` | authenticated | - | `200` + own profile (`user` + `employee`, sensitive fields omitted unless permitted) | - |
| PATCH | `/me` | `profile.update.self` | allow-listed self-service fields: `phone`, `email`, `address_line`, `emergency_contact_name`, `emergency_contact_phone` | `200` + updated profile | `VALIDATION_ERROR`, `CONFLICT_DUPLICATE` (email in use) |
| GET | `/employees` | `employee.read.all` | `status`, `department`, `employment_type`, `q`, `sort`, `page`, `page_size` | `200` + paginated `Employee` (sensitive fields masked) | `VALIDATION_ERROR` |
| POST | `/employees` | `employee.create` | `{ "employee_code", "full_name", "phone"?, "email"?, "date_of_joining", "employment_type", "department"?, "designation"?, "manager_employee_id"?, "emergency_contact_name"?, "emergency_contact_phone"?, "address_line"?, "username", "initial_password"?, "roles"?: ["EMPLOYEE"], "compensation"?: { "compensation_type", "rate", "currency", "effective_from", "reason" } }` | `201` + `Employee` + `User`; creates user account and (optionally) initial compensation | `CONFLICT_DUPLICATE` (code/username/email), `VALIDATION_ERROR` |
| GET | `/employees/{id}` | `employee.read.all` or self | - | `200` + `Employee` (sensitive fields only with `employee.read.sensitive`) | `RESOURCE_NOT_FOUND` |
| PATCH | `/employees/{id}` | `employee.update` | profile/employment fields (not bank details, not role assignment, not compensation) | `200` + `Employee` | `VALIDATION_ERROR`, `RESOURCE_NOT_FOUND` |
| PATCH | `/employees/{id}/sensitive` | `employee.update.sensitive` | `{ "bank_account_name"?, "bank_account_number"?, "bank_ifsc"?, "reason" }` | `200` + masked sensitive block | `PERMISSION_DENIED`, `VALIDATION_ERROR` |
| POST | `/employees/{id}/deactivate` | `employee.deactivate` | `{ "date_of_exit", "reason", "revoke_sessions"?: true }` | `200` + `Employee`; disables the user, revokes sessions, keeps all history | `RULE_VIOLATION` (open orders/tasks must be reassigned first unless forced), `RESOURCE_NOT_FOUND` |
| POST | `/employees/{id}/reactivate` | `employee.deactivate` | `{ "reason" }` | `200` + `Employee`; re-enables the user | `RESOURCE_NOT_FOUND`, `VALIDATION_ERROR` |
| GET | `/employees/{id}/compensation` | `employee.read.sensitive` | - | `200` + effective-dated compensation list | `RESOURCE_NOT_FOUND` |
| POST | `/employees/{id}/compensation` | `employee.update.sensitive` | `{ "compensation_type", "rate", "currency", "effective_from", "effective_to"?, "reason" }` | `201` + compensation row | `CONFLICT_DUPLICATE` (overlap), `VALIDATION_ERROR` |
| PUT | `/users/{id}/roles` | `employee.manage.roles` | `{ "role_codes": [...], "reason" }` | `200` + updated roles | `RULE_VIOLATION` (self-escalation, last-admin protection), `PERMISSION_DENIED` |
| GET | `/users` | `employee.read.all` | `status`, `q`, `page` | `200` + paginated users | - |

Notes:

- Deactivation is not deletion. The employee row, attendance, orders, ledger, salary records and
  audit history remain intact and are never rewritten (`docs/04_BUSINESS_RULES.md` section 4.12).
- `POST /employees/{id}/deactivate` returns `RULE_VIOLATION` when the employee holds an active
  order claim or an open task assignment, unless the request sets `"force": true` (permission
  `order.reassign` + `task.assign` also required), in which case the service releases claims and
  reassigns/unassigns open work in the same transaction and audits the cascade.
- Initial password handling: if `initial_password` is omitted, the API generates a one-time
  password and returns it once with `must_change_password = true`; it is never stored in plain
  text and never logged.

---

## 6. RBAC Module

| Method | Path | Auth | Request | Returns | Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/roles` | `role.read` | `include_system`, `page` | `200` + roles with permission counts | - |
| POST | `/roles` | `role.manage` | `{ "code", "name", "description"?, "permission_codes": [...] }` | `201` + role | `CONFLICT_DUPLICATE`, `VALIDATION_ERROR` (unknown permission code) |
| GET | `/roles/{id}` | `role.read` | - | `200` + role with `permissions[]` and `user_count` | `RESOURCE_NOT_FOUND` |
| PATCH | `/roles/{id}` | `role.manage` | `{ "name"?, "description"?, "is_assignable"? }` | `200` + role | `RULE_VIOLATION` (system role rename restrictions), `RESOURCE_NOT_FOUND` |
| PUT | `/roles/{id}/permissions` | `role.manage` | `{ "permission_codes": [...], "reason" }` | `200` + role permissions | `VALIDATION_ERROR`, `RULE_VIOLATION` (cannot weaken ADMIN below the catalog minimum), `RESOURCE_NOT_FOUND` |
| DELETE | `/roles/{id}` | `role.manage` | - | `204` | `RULE_VIOLATION` (system role or role in use) |
| GET | `/permissions` | `permission.read` | `module`? | `200` + full permission catalog grouped by module | - |

Permission changes are audited (`PERMISSION` category) with `before`/`after` code lists and take
effect on the next request of the affected user (permission resolution is not cached across
requests).

---

## 7. Settings Module

| Method | Path | Auth | Request | Returns | Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/settings/schema` | `settings.read` | - | `200` + registry: each key with `value_type`, `description`, `default`, `min`, `max`, `allowed_values`, `unit`, `is_provisional`, `consumer_module`, `group` | - |
| GET | `/settings` | `settings.read` | `group`?, `keys`? | `200` + current settings grouped by module | - |
| GET | `/settings/{key}` | `settings.read` | - | `200` + setting with value, type, version, updated_by, updated_at | `RESOURCE_NOT_FOUND` |
| PATCH | `/settings` | `settings.update` | `{ "reason", "changes": [ { "key", "value" } ] }` | `200` + updated settings; bumps versions and writes history | `VALIDATION_ERROR` (type/range/unknown key), `RESOURCE_NOT_FOUND` |
| GET | `/settings/{key}/history` | `settings.read.history` | `page`, `page_size` | `200` + paginated history (old/new value, actor, reason, timestamp) | `RESOURCE_NOT_FOUND` |

Notes:

- `GET /settings/schema` exists so the admin UI can render settings forms from the registry
  instead of hard-coding fields (`docs/07_UI_SPEC.md` section 9). It is the single source for
  labels, types, bounds and provisional flags.
- Bulk `PATCH /settings` is atomic: if any change fails validation, nothing is applied.
- Every change writes `business_setting_history`, an `audit_logs` row (`SETTINGS` category) and a
  `settings.changed.v1` event. `reason` is mandatory.
- Changing a setting that affects already-computed attendance or payroll does **not** silently
  rewrite history (see `docs/04_BUSINESS_RULES.md` sections 4.8 and 4.10).

---

## 8. Tasks Module

### 8.1 Admin (task owner) endpoints

| Method | Path | Auth | Request | Returns | Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/tasks` | `task.read.all` | `status`, `priority`, `assignee_employee_id`, `from`, `to` (due range), `q`, `sort`, `page` | `200` + paginated tasks with assignment rollup | `VALIDATION_ERROR` |
| POST | `/tasks` | `task.create` | `{ "title", "description"?, "priority"?, "due_at"?, "requires_evidence"?, "requires_attachment"?, "assignee_employee_ids": [...], "brief_attachment_file_ids"?: [...] }` | `201` + task with assignments | `VALIDATION_ERROR` (no assignees, inactive employee), `RESOURCE_NOT_FOUND` |
| GET | `/tasks/{id}` | `task.read.all` or assigned | - | `200` + task, assignments, comments, attachments | `RESOURCE_NOT_FOUND` |
| PATCH | `/tasks/{id}` | `task.update` | `{ "title"?, "description"?, "priority"?, "due_at"?, "requires_evidence"?, "requires_attachment"? }` | `200` + task | `RULE_VIOLATION` (completed/cancelled task), `RESOURCE_NOT_FOUND` |
| POST | `/tasks/{id}/cancel` | `task.cancel` | `{ "reason" }` | `200` + task; cancels open assignments and notifies assignees | `RULE_VIOLATION` (already completed), `RESOURCE_NOT_FOUND` |
| POST | `/tasks/{id}/assignments` | `task.assign` | `{ "employee_ids": [...], "due_at"? }` | `201` + created assignments | `CONFLICT_DUPLICATE` (already assigned), `VALIDATION_ERROR` |
| DELETE | `/tasks/{id}/assignments/{assignment_id}` | `task.assign` | - | `204`; only while the assignment is `ASSIGNED` and not started | `RULE_VIOLATION` (already started), `RESOURCE_NOT_FOUND` |
| POST | `/tasks/{id}/attachments` | `task.update` | `{ "file_id", "attachment_type": "BRIEF" }` | `201` + attachment | `VALIDATION_ERROR`, `RESOURCE_NOT_FOUND` |

### 8.2 Employee endpoints

| Method | Path | Auth | Request | Returns | Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/task-assignments/mine` | `task.read.self` | `status`, `due_before`, `sort`, `page` | `200` + paginated own assignments with task summary | - |
| GET | `/task-assignments/{id}` | `task.read.self` (own) or `task.read.all` | - | `200` + assignment, task, own submissions, comments, attachments | `RESOURCE_NOT_FOUND` (not own -> 404) |
| POST | `/task-assignments/{id}/start` | `task.submit.self` (own) | - | `200` + assignment (`STARTED`) | `STATE_CONFLICT`, `RESOURCE_NOT_FOUND` |
| POST | `/task-assignments/{id}/complete` | `task.submit.self` (own) | `{ "description"? }` | `200` + assignment (`COMPLETED` marker before submission) | `STATE_CONFLICT` |
| POST | `/task-assignments/{id}/submissions` | `task.submit.self` (own) | `{ "description"?, "attachment_file_ids"?: [...] }` + `Idempotency-Key` | `201` + submission (`attempt_no` incremented) | `RULE_VIOLATION` (evidence/attachment required), `STATE_CONFLICT` (not in a submittable state), `IDEMPOTENCY_CONFLICT` |
| POST | `/task-assignments/{id}/comments` | `task.comment` (own) | `{ "body" }` | `201` + comment | `RESOURCE_NOT_FOUND` |

### 8.3 Review endpoints

| Method | Path | Auth | Request | Returns | Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/task-submissions` | `task.review` | `status` (`PENDING_DECISION`), `employee_id`, `page` | `200` + submissions awaiting decision | - |
| POST | `/task-submissions/{id}/approve` | `task.review` | `{ "review_notes"? }` | `200` + submission + assignment (`APPROVED`) | `STATE_CONFLICT` (already decided), `RULE_VIOLATION` (self-approval not permitted), `RESOURCE_NOT_FOUND` |
| POST | `/task-submissions/{id}/reject` | `task.review` | `{ "review_notes" }` | `200` + submission + assignment (`REJECTED`, terminal) | `STATE_CONFLICT`, `RULE_VIOLATION` (self-approval), `RESOURCE_NOT_FOUND` |
| POST | `/task-submissions/{id}/request-resubmission` | `task.review` | `{ "review_notes" }` | `200` + submission + assignment (`RESUBMISSION_REQUESTED`) | `STATE_CONFLICT`, `RULE_VIOLATION` (self-review), `RESOURCE_NOT_FOUND` |
| POST | `/tasks/{id}/comments` | `task.review` or `task.update` | `{ "body", "assignment_id"?, "is_internal"? }` | `201` + comment | `RESOURCE_NOT_FOUND` |

Notes:

- `POST .../submissions` is the only way to attach task evidence; evidence attachments carry the
  `submission_id` so each attempt's evidence is preserved (`docs/02_DATABASE.md` section 10.5).
- Self-review is blocked: the acting user must not be the assignee
  (`docs/04_BUSINESS_RULES.md` section 4.6).
- A `REJECTED` assignment is terminal; further work requires a new task or a fresh assignment.
  `RESUBMISSION_REQUESTED` is the reopen path and increments `attempt_no` on the next
  submission.
- Rejected submissions are never deleted or edited; the history is visible to both sides.---

## 9. Orders Module

### 9.1 Endpoints

| Method | Path | Auth | Request | Returns | Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/orders` | `order.read.all` | `status`, `assignee_employee_id`, `unassigned`, `from`, `to` (created range), `q` (code/customer), `sort`, `page` | `200` + paginated orders | `VALIDATION_ERROR` |
| POST | `/orders` | `order.create` | `{ "order_code"?, "customer_name", "customer_phone"?, "delivery_address"?, "delivery_notes"?, "item_summary"?, "item_count"?, "order_amount", "currency"?, "payment_mode"?, "notes"?, "broadcast"?: { "audience_scope", "audience_payload"? } }` | `201` + order (`BROADCASTED` when `broadcast` supplied, otherwise `DRAFT`-equivalent creation requires broadcast before visibility) | `CONFLICT_DUPLICATE` (order_code), `VALIDATION_ERROR` |
| GET | `/orders/{id}` | `order.read.all` or holder | - | `200` + order + history + attachments + `allowed_transitions[]` | `RESOURCE_NOT_FOUND` |
| PATCH | `/orders/{id}` | `order.update` | `{ "customer_name"?, "customer_phone"?, "delivery_address"?, "delivery_notes"?, "item_summary"?, "item_count"?, "order_amount"?, "payment_mode"?, "notes"? }` | `200` + order | `RULE_VIOLATION` (delivered/cancelled order), `STATE_CONFLICT` (version), `RESOURCE_NOT_FOUND` |
| POST | `/orders/{id}/broadcast` | `order.broadcast` | `{ "audience_scope"?, "audience_payload"?, "expires_at"? }` | `200` + order + broadcast round | `RULE_VIOLATION` (already active claim / invalid status), `RESOURCE_NOT_FOUND` |
| GET | `/orders/available` | `order.read.available` | `page`, `page_size`, `sort` (`broadcast_at` asc default) | `200` + paginated broadcasted, unclaimed orders eligible for the caller (audience + settings filters applied server-side) | - |
| POST | `/orders/{id}/claim` | `order.claim` | `{}` + `Idempotency-Key` | `200` + order (`CLAIMED`) + claim | `CLAIM_ALREADY_TAKEN` (409, includes current order state), `RULE_VIOLATION` (not eligible: inactive, max active claims reached, attendance requirement), `STATE_CONFLICT`, `IDEMPOTENCY_CONFLICT` |
| POST | `/orders/{id}/release` | `order.claim` (holder) or `order.reassign` | `{ "reason" }` | `200` + order returned to `REASSIGNED`/`BROADCASTED` per settings | `RULE_VIOLATION` (status not releasable), `RESOURCE_NOT_FOUND` |
| GET | `/orders/mine` | `order.read.self` | `status`, `page` | `200` + paginated orders currently held by the caller (including completed history with `include_history=true`) | - |
| POST | `/orders/{id}/status` | `order.update.status.self` (holder) or `order.update.status.any` | `{ "to_status", "reason"?, "note"?, "evidence"?: { "latitude"?, "longitude"?, "accuracy_meters"? }, "proof_file_ids"?: [...] }` | `200` + order with new status | `RULE_VIOLATION` (invalid transition, proof required), `STATE_CONFLICT` (not the holder / version), `RESOURCE_NOT_FOUND` |
| POST | `/orders/{id}/reassign` | `order.reassign` | `{ "reason", "new_assignee_employee_id"? }` | `200` + order (`REASSIGNED` then `CLAIMED` when a target is given, else `BROADCASTED`) | `RULE_VIOLATION` (not reassignable), `RESOURCE_NOT_FOUND` |
| POST | `/orders/{id}/cancel` | `order.cancel` | `{ "reason", "cancellation_code"? }` | `200` + order (`CANCELLED`) | `RULE_VIOLATION` (status not cancellable per `orders.cancel_allowed_statuses`), `RESOURCE_NOT_FOUND` |
| POST | `/orders/{id}/fail` | `order.update.status.self` (holder) or `order.update.status.any` | `{ "failure_reason", "reason_code"? }` | `200` + order (`FAILED`) | `RULE_VIOLATION`, `RESOURCE_NOT_FOUND` |
| POST | `/orders/{id}/attachments` | `order.proof.upload` (holder) or `order.update.status.any` | `{ "file_id", "purpose", "note"?, "latitude"?, "longitude"?, "accuracy_meters"?, "customer_confirmed"?: bool, "customer_confirmation_method"? }` | `201` + attachment | `VALIDATION_ERROR` (purpose not allowed for status), `RESOURCE_NOT_FOUND` |
| GET | `/orders/{id}/history` | `order.read.all` or holder | - | `200` + ordered status history (from/to, actor, employee, reason, timestamp) | `RESOURCE_NOT_FOUND` |

### 9.2 Claim semantics (authoritative)

- `POST /orders/{id}/claim` is the only way to obtain ownership. It:
  1. verifies the caller is an active employee with `order.claim`;
  2. verifies the order is `BROADCASTED` and visible to the caller under the active broadcast
     round's audience;
  3. verifies eligibility settings (`orders.claim_requires_active_attendance`,
     `orders.max_active_claims_per_employee`);
  4. performs the conditional update and claim insert described in
     `docs/01_ARCHITECTURE.md` section 21.1;
  5. sets `claim_expires_at = now() + orders.claim_timeout_minutes` when
     `orders.auto_release_on_timeout` is true;
  6. writes status history, audit record and `order.claimed.v1` event.
- The loser of a race receives `409 CLAIM_ALREADY_TAKEN` with the winning claim's `claimed_at` and
  the current `status`, so the UI can render a clear conflict state
  (`docs/07_UI_SPEC.md` section 6.3).
- A claim is released by: the holder (`release`), an admin (`reassign`/`release`), delivery
  completion (`COMPLETED`), failure, cancellation, or the `order_claim_sweeper` job when
  `claim_expires_at` passes. Every release writes history, audit and an
  `order.claim_released.v1` event.
- `Idempotency-Key` is required; a duplicate click replays the original response instead of
  producing a second claim.

### 9.3 Lifecycle transitions exposed to clients

`allowed_transitions[]` is computed per order and per caller. The canonical transitions:

| From | To | Who | Notes |
| --- | --- | --- | --- |
| `BROADCASTED` | `CLAIMED` | Employee with `order.claim` | Atomic claim |
| `BROADCASTED` | `CANCELLED` | `order.cancel` | Per `orders.cancel_allowed_statuses` |
| `CLAIMED` | `PACKING` | Holder | Work started |
| `CLAIMED` | `REASSIGNED` | `order.reassign` | Admin releases and re-broadcasts |
| `CLAIMED` | `CANCELLED` / `FAILED` | `order.cancel` / holder | Per settings |
| `PACKING` | `PACKED` | Holder | Packing proof may be required |
| `PACKING` | `FAILED` | Holder | e.g. item unavailable |
| `PACKED` | `READY_FOR_DELIVERY` | Holder | Proof-of-packing window closes |
| `PACKED` | `REASSIGNED` | `order.reassign` | |
| `READY_FOR_DELIVERY` | `OUT_FOR_DELIVERY` | Holder | |
| `READY_FOR_DELIVERY` | `REASSIGNED` | `order.reassign` | |
| `OUT_FOR_DELIVERY` | `DELIVERED` | Holder | Requires configured proof-of-delivery |
| `OUT_FOR_DELIVERY` | `FAILED` | Holder | Requires failure reason |
| any non-terminal | `CANCELLED` | `order.cancel` | Subject to `orders.cancel_allowed_statuses` |
| `REASSIGNED` | `BROADCASTED` | system/admin | Returns to the pool for a new broadcast round |

`DELIVERED`, `CANCELLED` and `FAILED` are terminal; reaching `DELIVERED` closes the active claim
as `COMPLETED`. Skipping states (for example `CLAIMED` -> `PACKED`) is rejected with
`RULE_VIOLATION` unless the client decision on allowed shortcuts explicitly permits it - see
`docs/04_BUSINESS_RULES.md` section 4.7 and the `CLIENT_DECISION_REQUIRED` item 18.

---

## 10. Leaves Module

| Method | Path | Auth | Request | Returns | Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/leave-types` | `leave.read.self` | `include_inactive` (`leave.type.manage` only) | `200` + active leave types | - |
| POST | `/leave-types` | `leave.type.manage` | `{ "code", "name", "is_paid", "requires_approval", "requires_attachment_after_days"?, "max_consecutive_days"?, "allow_half_day"?, "annual_entitlement_days"?, "accrual_mode"? }` | `201` + leave type | `CONFLICT_DUPLICATE`, `VALIDATION_ERROR` |
| PATCH | `/leave-types/{id}` | `leave.type.manage` | partial leave type | `200` + leave type | `RULE_VIOLATION` (deactivating a type with pending requests), `RESOURCE_NOT_FOUND` |
| POST | `/leaves` | `leave.apply.self` | `{ "leave_type_id", "start_date", "end_date", "is_half_day"?, "half_day_period"?, "reason", "attachment_file_id"? }` + `Idempotency-Key` | `201` + leave (`PENDING`) | `RULE_VIOLATION` (overlap, balance insufficient, attachment required, max advance days, max consecutive days), `VALIDATION_ERROR`, `IDEMPOTENCY_CONFLICT` |
| GET | `/leaves/mine` | `leave.read.self` | `status`, `leave_type_id`, `from`, `to`, `page` | `200` + paginated own leaves | - |
| GET | `/leaves` | `leave.read.all` | `employee_id`, `leave_type_id`, `status`, `from`, `to`, `sort`, `page` | `200` + paginated leaves | `VALIDATION_ERROR` |
| GET | `/leaves/{id}` | `leave.read.all` or self | - | `200` + leave + balance effect + `allowed_transitions[]` | `RESOURCE_NOT_FOUND` |
| POST | `/leaves/{id}/approve` | `leave.approve` | `{ "decision_notes"? }` | `200` + leave (`APPROVED`) + updated balance | `STATE_CONFLICT` (already decided), `RULE_VIOLATION` (insufficient balance, self-approval, overlapping approved leave), `RESOURCE_NOT_FOUND` |
| POST | `/leaves/{id}/reject` | `leave.approve` | `{ "decision_notes" }` | `200` + leave (`REJECTED`) + balance hold released | `STATE_CONFLICT`, `RESOURCE_NOT_FOUND` |
| POST | `/leaves/{id}/request-modification` | `leave.approve` | `{ "decision_notes" }` | `200` + leave (`MODIFICATION_REQUESTED`) | `STATE_CONFLICT`, `RESOURCE_NOT_FOUND` |
| POST | `/leaves/{id}/cancel` | `leave.cancel.self` (own, pending) or `leave.cancel.any` | `{ "reason" }` | `200` + leave (`CANCELLED`); releases hold or reverses usage | `STATE_CONFLICT`, `RULE_VIOLATION` (period locked), `RESOURCE_NOT_FOUND` |
| GET | `/leave-balances/mine` | `leave.read.self` | `period_year`? | `200` + own balances with component breakdown | - |
| GET | `/leave-balances` | `leave.read.all` | `employee_id`, `leave_type_id`, `period_year`, `page` | `200` + paginated balances | `VALIDATION_ERROR` |
| GET | `/leave-balances/{id}/movements` | `leave.read.all` or owner | `page`, `page_size` | `200` + paginated balance ledger movements | `RESOURCE_NOT_FOUND` |
| POST | `/leave-balances/adjustments` | `leave.balance.manage` | `{ "employee_id", "leave_type_id", "period_year", "days", "reason" }` | `200` + updated balance + ledger movement | `VALIDATION_ERROR`, `RULE_VIOLATION` (resulting balance below used days), `RESOURCE_NOT_FOUND` |

Notes:

- Applying for leave immediately places a negative `PENDING_HOLD` movement so the balance cannot
  be over-committed by concurrent requests; approval converts the hold into `USAGE`, and
  rejection/cancellation releases it with `PENDING_RELEASE`
  (`docs/04_BUSINESS_RULES.md` section 4.8).
- Self-approval is rejected even for users holding `leave.approve`, unless the caller is the only
  holder of `leave.approve` and the settings flag
  `leaves.allow_admin_self_approval` is explicitly enabled (default false).
- `POST /leaves/{id}/cancel` on an `APPROVED` leave that falls inside a `LOCKED` payroll period is
  rejected with `RULE_VIOLATION` and must be handled through a balance adjustment, so finalized
  payroll is never silently invalidated.---

## 11. Ledger, Advances and Payroll Module

### 11.1 Employee ledger

| Method | Path | Auth | Request | Returns | Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/ledger/me` | `ledger.read.self` | `from`, `to`, `entry_type`, `page` | `200` + paginated own ledger entries + `summary` (credit total, debit total, net) | - |
| GET | `/ledger` | `ledger.read.all` | `employee_id`, `entry_type`, `direction`, `period_year`, `period_month`, `from`, `to`, `page` | `200` + paginated entries + `summary` | `VALIDATION_ERROR` |
| GET | `/ledger/{id}` | `ledger.read.all` or owner | - | `200` + entry with reference details | `RESOURCE_NOT_FOUND` |
| POST | `/ledger/entries` | `ledger.entry.create` | `{ "employee_id", "entry_type", "direction", "amount", "currency"?, "business_date", "period_year"?, "period_month"?, "reason", "reference_type"?, "reference_id"? }` + `Idempotency-Key` | `201` + entry | `RULE_VIOLATION` (period locked, entry type not permitted manually), `VALIDATION_ERROR`, `IDEMPOTENCY_CONFLICT` |
| POST | `/ledger/entries/{id}/reverse` | `ledger.entry.adjust` | `{ "reason" }` | `201` + reversal entry referencing the original | `RULE_VIOLATION` (already reversed, period locked), `RESOURCE_NOT_FOUND` |
| GET | `/ledger/balance/{employee_id}` | `ledger.read.all` or owner with `ledger.read.self` | `as_of`? | `200` + `{ credit_total, debit_total, net, as_of }` | `RESOURCE_NOT_FOUND` |

Rules: ledger rows are never updated or deleted ("No silent financial mutation",
`AGENTS.md` section 3). Correction is always a reversal plus, if needed, a new entry. Both the
original and the reversal remain visible. `ADVANCE_REPAYMENT` is documented as the only
repayment type posted outside payroll (section 13.1 of the database document).

### 11.2 Advances

| Method | Path | Auth | Request | Returns | Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/advances/mine` | `advance.read.self` | `status`, `page` | `200` + own advances with outstanding and next due installment | - |
| GET | `/advances` | `advance.read.all` | `employee_id`, `status`, `from`, `to`, `page` | `200` + paginated advances | `VALIDATION_ERROR` |
| GET | `/advances/{id}` | `advance.read.all` or owner | - | `200` + advance + installments + linked ledger entries | `RESOURCE_NOT_FOUND` |
| POST | `/advances` | `advance.create` | `{ "employee_id", "amount", "currency"?, "issued_on", "reason", "repayment_mode", "installment_count"?, "installment_amount"? }` + `Idempotency-Key` | `201` + advance (`PENDING_APPROVAL` when `advance.requires_approval`, else `OUTSTANDING`) | `RULE_VIOLATION` (exceeds `advance.max_outstanding_percent_of_salary`), `VALIDATION_ERROR`, `IDEMPOTENCY_CONFLICT` |
| POST | `/advances/{id}/approve` | `advance.approve` | `{ "decision_notes"? }` | `200` + advance (`OUTSTANDING`), ledger `ADVANCE_ISSUED` entry, installments generated | `STATE_CONFLICT`, `RULE_VIOLATION` (self-approval), `RESOURCE_NOT_FOUND` |
| POST | `/advances/{id}/reject` | `advance.approve` | `{ "decision_notes" }` | `200` + advance (`CANCELLED`) | `STATE_CONFLICT`, `RESOURCE_NOT_FOUND` |
| POST | `/advances/{id}/repayments` | `ledger.entry.create` | `{ "amount", "business_date", "reason" }` + `Idempotency-Key` | `201` + ledger `ADVANCE_REPAYMENT` entry + updated advance | `RULE_VIOLATION` (exceeds outstanding), `STATE_CONFLICT`, `RESOURCE_NOT_FOUND` |
| POST | `/advances/{id}/write-off` | `advance.approve` + `ledger.entry.adjust` | `{ "amount"?, "reason" }` | `200` + advance (`WRITTEN_OFF`) + audit | `RULE_VIOLATION` (period locked), `RESOURCE_NOT_FOUND` |

### 11.3 Payroll runs and salary records

| Method | Path | Auth | Request | Returns | Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/payroll/runs` | `salary.read.all` | `period_year`, `status`, `page` | `200` + paginated runs | - |
| POST | `/payroll/runs` | `salary.compute` | `{ "period_year", "period_month", "notes"? }` | `201` + run (`DRAFT`) | `CONFLICT_DUPLICATE` (run exists), `VALIDATION_ERROR` |
| GET | `/payroll/runs/{id}` | `salary.read.all` | - | `200` + run + summary totals + record counts by status | `RESOURCE_NOT_FOUND` |
| POST | `/payroll/runs/{id}/compute` | `salary.compute` | `{ "employee_ids"?: [...], "reason"? }` | `200` + run (`COMPUTED`) + per-employee results (including skipped employees with reasons) | `RULE_VIOLATION` (run locked/finalized), `STATE_CONFLICT`, `RESOURCE_NOT_FOUND` |
| POST | `/payroll/runs/{id}/finalize` | `salary.finalize` | `{ "reason"? }` | `200` + run (`FINALIZED`); each record becomes immutable | `RULE_VIOLATION` (uncomputed records, open attendance corrections), `STATE_CONFLICT`, `RESOURCE_NOT_FOUND` |
| POST | `/payroll/runs/{id}/lock` | `payroll.lock` | `{ "reason" }` | `200` + run (`LOCKED`) | `RULE_VIOLATION` (not finalized), `RESOURCE_NOT_FOUND` |
| POST | `/payroll/runs/{id}/unlock` | `payroll.unlock` | `{ "reason" }` | `200` + run (`FINALIZED`); audited with reason | `RULE_VIOLATION` (already paid), `RESOURCE_NOT_FOUND` |
| POST | `/payroll/runs/{id}/mark-paid` | `payroll.pay` | `{ "paid_on", "payment_reference"?, "reason"? }` | `200` + run (`PAID`); posts `PAYMENT_MADE` ledger entries | `RULE_VIOLATION` (not finalized), `STATE_CONFLICT`, `RESOURCE_NOT_FOUND` |
| GET | `/salary-records/me` | `salary.read.self` | `period_year`?, `page` | `200` + own salary records (fields gated by `salary.read.self` policy) | - |
| GET | `/salary-records` | `salary.read.all` | `employee_id`, `period_year`, `period_month`, `status`, `payroll_run_id`, `page` | `200` + paginated salary records | `VALIDATION_ERROR` |
| GET | `/salary-records/{id}` | `salary.read.all` or owner with `salary.read.self` | - | `200` + salary record with `calculation_breakdown` and rule snapshot hash | `RESOURCE_NOT_FOUND` |
| GET | `/salary-records/{id}/payslip` | `salary.read.all` or owner with `salary.read.self` | `format` (`PDF`/`JSON`) | `200` + payslip | `NOT_IMPLEMENTED` until client confirms format (item 21), `RESOURCE_NOT_FOUND` |

Notes:

- `compute` snapshots the settings used into `payroll_rule_snapshots` and records
  `inputs_snapshot` / `calculation_breakdown` per record, so a record can be explained and
  reproduced without recomputing from today's rules (`AGENTS.md` section 11).
- `finalize` refuses to proceed while attendance corrections for the period are still `PENDING`,
  unless an Admin explicitly passes `"force": true` with `salary.finalize` +
  `ledger.entry.adjust`, which records the override in the audit log and in the run notes.
- Attendance corrections after a run is `LOCKED` do not modify the locked salary record; they
  produce an adjustment in the next open period through `POST /ledger/entries` (see
  `docs/04_BUSINESS_RULES.md` section 4.10).
- Employee visibility of salary/ledger detail is client decision 25
  (`CLIENT_DECISION_REQUIRED`); the endpoints exist and are gated by permissions that the Admin
  can grant or withhold.

---

## 12. Complaints Module

| Method | Path | Auth | Request | Returns | Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/complaint-categories` | `complaint.create.self` | `include_inactive` (`complaint.manage` only) | `200` + categories | - |
| POST | `/complaint-categories` | `complaint.manage` | `{ "code", "name", "default_priority"?, "default_visibility"? }` | `201` + category | `CONFLICT_DUPLICATE`, `VALIDATION_ERROR` |
| POST | `/complaints` | `complaint.create.self` | `{ "category_id", "title", "description", "priority"?, "subject_employee_id"?, "attachment_file_ids"?: [...] }` | `201` + complaint (`OPEN`) | `VALIDATION_ERROR`, `RESOURCE_NOT_FOUND` |
| GET | `/complaints/mine` | `complaint.read.self` | `status`, `page` | `200` + paginated own complaints (internal comments excluded) | - |
| GET | `/complaints` | `complaint.read.all` | `status`, `priority`, `category_id`, `raised_by`, `subject_employee_id`, `assigned_to`, `from`, `to`, `q`, `sort`, `page` | `200` + paginated complaints (visibility-filtered) | `VALIDATION_ERROR` |
| GET | `/complaints/{id}` | `complaint.read.all` or raiser | - | `200` + complaint + comments (internal gated) + history + `allowed_transitions[]` | `RESOURCE_NOT_FOUND` (visibility-denied -> 404) |
| PATCH | `/complaints/{id}` | `complaint.manage` | `{ "title"?, "description"?, "priority"?, "category_id"?, "visibility"?, "assigned_to"? }` | `200` + complaint | `RULE_VIOLATION` (closed complaint), `RESOURCE_NOT_FOUND` |
| POST | `/complaints/{id}/status` | `complaint.manage` | `{ "to_status", "reason"?, "internal_note"? }` | `200` + complaint | `RULE_VIOLATION` (invalid transition), `STATE_CONFLICT`, `RESOURCE_NOT_FOUND` |
| POST | `/complaints/{id}/resolve` | `complaint.resolve` | `{ "resolution_summary" }` | `200` + complaint (`RESOLVED`) | `STATE_CONFLICT`, `RESOURCE_NOT_FOUND` |
| POST | `/complaints/{id}/close` | `complaint.close` | `{ "note"? }` | `200` + complaint (`CLOSED`) | `RULE_VIOLATION` (not resolved), `RESOURCE_NOT_FOUND` |
| POST | `/complaints/{id}/reject` | `complaint.resolve` | `{ "rejection_reason" }` | `200` + complaint (`REJECTED`) | `STATE_CONFLICT`, `RESOURCE_NOT_FOUND` |
| GET | `/complaints/{id}/comments` | `complaint.read.self` (raiser) or `complaint.read.all` | `include_internal` (`complaint.read.internal` only) | `200` + comments | `RESOURCE_NOT_FOUND` |
| POST | `/complaints/{id}/comments` | `complaint.comment` | `{ "body", "is_internal"? }` (`is_internal` requires `complaint.read.internal`) | `201` + comment | `RULE_VIOLATION` (closed complaint), `RESOURCE_NOT_FOUND` |
| POST | `/complaints/{id}/attachments` | `complaint.comment` (raiser) or `complaint.manage` | `{ "file_id", "note"? }` | `201` + attachment | `RESOURCE_NOT_FOUND` |

Visibility rules (`docs/04_BUSINESS_RULES.md` section 4.11):

- `EMPLOYEE_PRIVATE`: the raiser and holders of `complaint.read.all` can see it. A non-raiser
  without `complaint.read.all` receives `404`.
- `ADMIN_ONLY`: only holders of `complaint.read.all`.
- `INTERNAL_TEAM`: holders of `complaint.read.all` and `complaint.read.internal` plus the raiser.
- `is_internal` comments and internal status notes are never returned to a raiser.
- Complaint privacy/visibility defaults are client decision 20 (`CLIENT_DECISION_REQUIRED`).

---

## 13. Notifications Module

| Method | Path | Auth | Request | Returns | Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/notifications` | `notification.read.self` | `is_read`, `cursor`, `limit` (or `page`) | `200` + notifications with `next_cursor` | - |
| GET | `/notifications/unread-count` | `notification.read.self` | - | `200` + `{ "unread": n }` | - |
| POST | `/notifications/{id}/read` | `notification.read.self` (own) | - | `204` | `RESOURCE_NOT_FOUND` |
| POST | `/notifications/read` | `notification.read.self` | `{ "ids"?: [...], "all"?: true }` | `200` + `{ "updated": n }` | `VALIDATION_ERROR` |
| GET | `/notification-preferences` | `notification.read.self` | - | `200` + per-event/channel preferences with effective defaults | - |
| PATCH | `/notification-preferences` | `notification.read.self` | `{ "preferences": [ { "event_type", "channel", "is_enabled" } ] }` | `200` + updated preferences | `RULE_VIOLATION` (security event cannot be disabled), `VALIDATION_ERROR` |
| POST | `/push-subscriptions` | `notification.read.self` | `{ "endpoint", "keys": { "p256dh", "auth" }, "user_agent"? }` | `201` + subscription | `VALIDATION_ERROR` |
| DELETE | `/push-subscriptions/{id}` | `notification.read.self` (own) | - | `204` | `RESOURCE_NOT_FOUND` |
| POST | `/notifications/broadcast` | `notification.manage` | `{ "title", "body", "audience": { "scope", "employee_ids"? }, "priority"? }` | `201` + created notifications | `VALIDATION_ERROR` |

Notes: notification list is cursor-paginated because it is append-heavy
(`docs/01_ARCHITECTURE.md` section 13.5). Broadcast notifications are audited. Delivery status
for a channel is visible only to `notification.manage`.

---

## 14. Files Module

| Method | Path | Auth | Request | Returns | Errors |
| --- | --- | --- | --- | --- | --- |
| POST | `/files` | `file.upload` | multipart `file` + `purpose` | `201` + file metadata (id, original_name, content_type, size_bytes, checksum, scan_status) | `FILE_TOO_LARGE`, `UNSUPPORTED_FILE_TYPE`, `STORAGE_UNAVAILABLE`, `RATE_LIMITED` |
| GET | `/files/{id}` | authorized by relying entity or owner | - | `200` + file metadata | `RESOURCE_NOT_FOUND` (hidden when unauthorized) |
| GET | `/files/{id}/url` | authorized by relying entity or owner | `disposition`? | `200` + `{ "url", "expires_at" }` (short-lived presigned URL) | `RESOURCE_NOT_FOUND`, `STORAGE_UNAVAILABLE` |
| DELETE | `/files/{id}` | `file.delete` or owner while unreferenced | - | `204` (soft delete) | `RULE_VIOLATION` (referenced by a submitted record), `RESOURCE_NOT_FOUND` |

Authorization rule: `GET /files/{id}` and `/files/{id}/url` delegate to the owning module. For
example, a task evidence file is readable by the assignee, the task creator and holders of
`task.read.all`; an order delivery proof by the holder and holders of `order.read.all`; a
complaint attachment by the raiser (when visibility allows) and holders of
`complaint.read.all`. A file that is not referenced by any entity is readable only by its
uploader and holders of `file.read.all`. Every presigned URL issuance is audit-logged.

---

## 15. Reports Module

Report column definitions, calculations and filters are in `docs/08_REPORT_SPEC.md`. This section
fixes the endpoint surface.

| Method | Path | Auth | Request | Returns | Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/reports/catalog` | any authenticated | - | `200` + available report types the caller may run, with filter schema and required permission | - |
| GET | `/reports/dashboard-summary` | authenticated | `as_of`? | `200` + role-appropriate summary (admin: attendance/tasks/orders/leaves/complaints counters; employee: my today/attendance/tasks/orders/balance/notifications) | - |
| GET | `/reports/attendance` | `report.attendance` | `from`, `to`, `employee_id`?, `department`?, `group_by` (`employee`/`date`), `page` | `200` + report rows + totals | `VALIDATION_ERROR` (range exceeds `reports.max_range_days`) |
| GET | `/reports/work-hours` | `report.attendance` | `from`, `to`, `employee_id`?, `group_by` | `200` + worked/break/overtime totals with day classification counts | `VALIDATION_ERROR` |
| GET | `/reports/breaks` | `report.attendance` | `from`, `to`, `employee_id`?, `break_type_id`? | `200` + break totals per employee and type | `VALIDATION_ERROR` |
| GET | `/reports/overtime` | `report.attendance` | `from`, `to`, `employee_id`? | `200` + overtime totals and days | `VALIDATION_ERROR` |
| GET | `/reports/tasks` | `report.tasks` | `from`, `to`, `employee_id`?, `status`?, `priority`? | `200` + assignment counts, completion rate, average review turnaround, overdue counts | `VALIDATION_ERROR` |
| GET | `/reports/orders` | `report.orders` | `from`, `to`, `employee_id`?, `status`? | `200` + order counts by status, claim counts, average time per stage, delivery counts, failures | `VALIDATION_ERROR` |
| GET | `/reports/leaves` | `report.leaves` | `from`, `to`, `employee_id`?, `leave_type_id`?, `status`? | `200` + leave days by employee/type/status + balance summary | `VALIDATION_ERROR` |
| GET | `/reports/advances` | `report.ledger` | `from`, `to`, `employee_id`?, `status`? | `200` + issued/recovered/outstanding advances | `VALIDATION_ERROR` |
| GET | `/reports/ledger` | `report.ledger` | `from`, `to`, `employee_id`?, `entry_type`? | `200` + group-by-employee summary and opening/closing movement | `VALIDATION_ERROR` |
| GET | `/reports/salary` | `report.salary` | `period_year`, `period_month`, `employee_id`? | `200` + per-employee salary components and totals for the period | `VALIDATION_ERROR`, `RESOURCE_NOT_FOUND` (no run) |
| GET | `/reports/complaints` | `report.complaints` | `from`, `to`, `status`?, `category_id`?, `include_subject`? | `200` + complaint counts by status/priority/category, resolution times (subject only with `include_subject` + `complaint.read.all`) | `VALIDATION_ERROR` |
| POST | `/reports/exports` | `report.export` | `{ "report_type", "format", "parameters": {...} }` + `Idempotency-Key` | `202` + export job (`QUEUED`) | `VALIDATION_ERROR` (format not in `reports.export_formats`, range too large), `RATE_LIMITED`, `CONFLICT_DUPLICATE` (identical job already running) |
| GET | `/reports/exports` | authenticated | `mine` (default true unless `report.export`), `status`, `page` | `200` + paginated export jobs | - |
| GET | `/reports/exports/{id}` | owner or `report.export` | - | `200` + export job with `file_id` and download URL when complete | `RESOURCE_NOT_FOUND` |
| DELETE | `/reports/exports/{id}` | owner or `report.export` | - | `204` | `RESOURCE_NOT_FOUND` |

Notes:

- Reports never return data the caller could not obtain from the corresponding list endpoints.
  Employee-scoped reports (`report.attendance` held by a non-admin) apply a self-scope filter
  automatically.
- Report and export queries run in a read-only transaction with a bounded date range, and
  exports stream to object storage rather than buffering in memory.

---

## 16. Audit Module

| Method | Path | Auth | Request | Returns | Errors |
| --- | --- | --- | --- | --- | --- |
| GET | `/audit-logs` | `audit.read` | `category`, `action`, `entity_type`, `entity_id`, `actor_user_id`, `from`, `to`, `cursor`, `limit` | `200` + audit records with `next_cursor` | `VALIDATION_ERROR` |
| GET | `/audit-logs/{id}` | `audit.read` | - | `200` + audit record | `RESOURCE_NOT_FOUND` |
| POST | `/audit-logs/exports` | `audit.export` | `{ "format", "filters": {...} }` | `202` + export job | `VALIDATION_ERROR`, `RATE_LIMITED` |

Audit records are immutable through the API: there is no update or delete endpoint, by design.

---

## 17. Health Endpoints

| Method | Path | Auth | Returns |
| --- | --- | --- | --- |
| GET | `/health` | public (internal network preferred) | `200` + `{ "status": "ok", "version" }` |
| GET | `/health/ready` | public (internal network preferred) | `200` when database is reachable, migrations are at head and storage is reachable; `503` with `DEPENDENCY_UNAVAILABLE` otherwise |---

## 18. Idempotency and Duplicate-Submission Matrix

`Idempotency-Key` is mandatory for the operations marked "required" and accepted (but optional)
elsewhere. Regardless of the header, database constraints prevent duplicate state
(`docs/02_DATABASE.md` section 18).

| Operation | Idempotency-Key | Database guard behind it |
| --- | --- | --- |
| `POST /attendance/check-in` | required | Partial unique index on open `attendance_sessions` (DB-1) |
| `POST /attendance/check-out` | required | Session state guard + unique open session |
| `POST /attendance/break/start` | required | Partial unique index on open `break_sessions` (DB-2) |
| `POST /attendance/break/end` | required | Break state guard |
| `POST /attendance/corrections` | optional | `PENDING` uniqueness per record/type enforced in service (documented, not a DB unique index because multiple historical corrections are allowed) |
| `POST /task-assignments/{id}/submissions` | required | `UNIQUE (assignment_id, attempt_no)` (DB-10) + state guard |
| `POST /orders/{id}/claim` | required | Conditional update + partial unique active claim (DB-3) |
| `POST /orders/{id}/status` | optional | Optimistic `version` + transition guard |
| `POST /orders/{id}/attachments` | optional | `files.id` unique reference per attachment row |
| `POST /leaves` | required | Exclusion constraint on overlapping pending/approved leave (DB-7) + lock on balance |
| `POST /leave-balances/adjustments` | optional | Row lock on `leave_balances` |
| `POST /ledger/entries` | required | Append-only; replay returns the stored response |
| `POST /advances` | required | Balance/limit rule + replay |
| `POST /advances/{id}/repayments` | required | Outstanding-amount guard |
| `POST /payroll/runs/{id}/compute` | optional | Run status guard (`COMPUTED` is recomputable while not finalized) |
| `POST /payroll/runs/{id}/mark-paid` | required | Run status guard; `PAYMENT_MADE` unique per salary record |
| `POST /files` | optional | Checksum recorded; duplicates are distinct files unless the client de-duplicates |
| `POST /reports/exports` | required | Identical-job dedupe check |

Replay semantics: identical key + identical request hash returns the original response with
`Idempotency-Replayed: true`. Identical key + different request hash returns
`409 IDEMPOTENCY_CONFLICT`.

---

## 19. Conflict and Concurrency Response Semantics

The frontend needs unambiguous signals to render conflict states. The following codes are
contractual and must not be reused for other meanings.

| Code | HTTP | Meaning | Client action |
| --- | --- | --- | --- |
| `CLAIM_ALREADY_TAKEN` | 409 | Another employee won the order claim | Refresh the order, show conflict state, stop claiming |
| `STATE_CONFLICT` | 409 | The entity is not in the state this operation requires | Refresh the entity and recompute allowed actions |
| `CONFLICT_DUPLICATE` | 409 | A uniqueness rule is violated (code/username/email/period) | Show which field conflicts |
| `IDEMPOTENCY_CONFLICT` | 409 | Same idempotency key, different payload | Treat as a client bug; do not retry automatically |
| `RULE_VIOLATION` | 422 | A configurable business rule rejected the operation | Show the server's message; do not retry unchanged |
| `VALIDATION_ERROR` | 422 | Request shape/values invalid | Fix the highlighted fields |
| `PERMISSION_DENIED` | 403 | Authenticated but not permitted | Hide the action; do not retry |
| `RESOURCE_NOT_FOUND` | 404 | Missing, or intentionally hidden (authorization) | Navigate away; never infer existence |
| `RATE_LIMITED` | 429 | Too many attempts | Back off per `Retry-After` |
| `PERIOD_LOCKED` | 423 | Target payroll period is locked | Offer an adjustment path instead |

`RULE_VIOLATION` responses include a `rule_code` (stable identifier such as
`ATTENDANCE_OUTSIDE_GEOFENCE`, `LEAVE_BALANCE_INSUFFICIENT`, `ORDER_PROOF_REQUIRED`) plus a
human-readable `detail`, so the UI can map to specific UX without string matching.

---

## 20. Authorization Test Surface (contract for Agent 5)

Every endpoint must reject the following. These are explicit API-level requirements, verified in
`docs/09_TEST_PLAN.md` section 6.

1. An employee calling any admin-scoped endpoint (`employee.read.all`, `settings.update`,
   `payroll.*`, `audit.read`, `report.*` beyond self-scope) -> `403`.
2. An employee reading another employee's record, attendance, ledger, salary, leave, task
   assignment, order, complaint or file -> `404`/`403` and never a partial leak.
3. An employee attempting to modify their own attendance directly (no endpoint exists; crafting
   one is a defect), salary, ledger, or approval state -> `403`/`404`.
4. An employee approving or reviewing their own task submission, leave or complaint -> `403`.
5. An employee claiming an already-claimed order -> `409 CLAIM_ALREADY_TAKEN`.
6. Reading a file without authorization on the relying entity -> `404`.
7. Replaying an expired or consumed QR token -> `RULE_VIOLATION` with
   `failure_code = QR_EXPIRED` / `QR_REPLAYED`, no attendance event created.
8. Forging attendance evidence (client-supplied distance, "verified" flags, business date,
   `employee_id`, worked hours) -> the value is ignored, not trusted.
9. Manipulating financial payloads (negative amounts, unknown entry types, amounts on someone
   else's ledger, edits to finalized salary) -> `403`/`422`/`423`.
10. Acting on another user's session or CSRF-less unsafe request -> `401`/`403`.

---

## 21. Workflow Coverage Matrix

Every workflow in `docs/06_WORKFLOWS.md` must be executable with the endpoints above. This is
Agent 1's verification that the API supports the product workflows.

| Workflow (docs/06) | Endpoints |
| --- | --- |
| W-01 Login / logout / session | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `GET|DELETE /auth/sessions` |
| W-02 Password change / admin reset | `POST /auth/change-password`, `POST /auth/reset-password` |
| W-03 Employee onboarding | `POST /employees`, `POST /employees/{id}/compensation`, `PUT /users/{id}/roles` |
| W-04 Employee deactivation / reactivation | `POST /employees/{id}/deactivate`, `POST /employees/{id}/reactivate` |
| W-05 Check-in with verification | `POST /attendance/check-in`, `GET /attendance/me/today`, `GET /attendance/qr-tokens/current`, `POST /attendance/qr-tokens` |
| W-06 Break start / end | `POST /attendance/break/start`, `POST /attendance/break/end`, `GET /break-types` |
| W-07 Check-out | `POST /attendance/check-out` |
| W-08 Missing checkout handling | `attendance_auto_close` job, `POST /attendance/corrections`, `GET /attendance/me/today` |
| W-09 Attendance correction | `POST /attendance/corrections`, `POST /attendance/corrections/{id}/approve|reject`, `POST /attendance/{record_id}/recompute` |
| W-10 Work-hour computation and day classification | derived; visible through `GET /attendance/{id}`, `GET /attendance/me/summary`, `POST /attendance/{record_id}/recompute` |
| W-11 Task assignment and execution | `POST /tasks`, `POST /tasks/{id}/assignments`, `GET /task-assignments/mine`, `POST /task-assignments/{id}/start|complete`, `POST /task-assignments/{id}/submissions` |
| W-12 Task review and resubmission | `POST /task-submissions/{id}/approve|reject|request-resubmission`, `GET /task-submissions` |
| W-13 Order creation and broadcast | `POST /orders`, `POST /orders/{id}/broadcast`, `GET /orders/available` |
| W-14 Order claim (atomic) | `POST /orders/{id}/claim` |
| W-15 Order fulfillment | `POST /orders/{id}/status`, `POST /orders/{id}/attachments` |
| W-16 Order reassignment / abandonment | `POST /orders/{id}/release`, `POST /orders/{id}/reassign`, `order_claim_sweeper` job |
| W-17 Order cancellation / failure | `POST /orders/{id}/cancel`, `POST /orders/{id}/fail` |
| W-18 Leave application and decision | `POST /leaves`, `POST /leaves/{id}/approve|reject|request-modification`, `GET /leave-balances/mine` |
| W-19 Leave cancellation and balance correction | `POST /leaves/{id}/cancel`, `POST /leave-balances/adjustments` |
| W-20 Advance issuance and recovery | `POST /advances`, `POST /advances/{id}/approve`, `POST /advances/{id}/repayments` |
| W-21 Manual financial adjustment | `POST /ledger/entries`, `POST /ledger/entries/{id}/reverse` |
| W-22 Payroll run: compute -> finalize -> lock -> pay | `POST /payroll/runs`, `POST /payroll/runs/{id}/compute|finalize|lock|unlock|mark-paid` |
| W-23 Complaint intake and resolution | `POST /complaints`, `POST /complaints/{id}/status|resolve|close|reject`, `POST /complaints/{id}/comments` |
| W-24 Notification delivery | derived from events; `GET /notifications`, `POST /notifications/read`, `POST /push-subscriptions`, `PATCH /notification-preferences` |
| W-25 Reporting and export | `GET /reports/*`, `POST /reports/exports`, `GET /reports/exports/{id}` |
| W-26 Settings change | `GET /settings/schema`, `PATCH /settings`, `GET /settings/{key}/history` |
| W-27 Role and permission management | `GET|POST /roles`, `PUT /roles/{id}/permissions`, `PUT /users/{id}/roles`, `GET /permissions` |
| W-28 Audit inspection | `GET /audit-logs`, `POST /audit-logs/exports` |
| W-29 File upload and authorized download | `POST /files`, `GET /files/{id}`, `GET /files/{id}/url` |

---

## 22. Contract Change Log

| Version | Date | Change | Author |
| --- | --- | --- | --- |
| 1.0 | 2026-09-25 | Initial endpoint surface for all modules; idempotency and conflict semantics; authorization test surface; workflow coverage matrix | Agent 1 |

Change protocol: any change to a documented path, permission requirement, request field,
response field, status code or error code requires (1) the issue identified, (2) this document
updated, (3) affected implementation updated, (4) affected tests run
(`AGENTS.md` section 5).

---

## 23. Agent 1 Verification Notes (API layer)

- **Modules covered:** all 27 core modules in `docs/00_PRODUCT_SCOPE.md` section 3 have
  endpoints or are derived state exposed through endpoints (work-hour computation, day
  classification, order lifecycle timestamps, notification delivery, dashboard summaries).
- **Permissions align with workflows:** every mutating endpoint names a permission that exists in
  `docs/05_PERMISSIONS.md`, and the role mapping in that document grants the workflow to the
  correct role. Admin-only operations are never reachable with an employee-scoped permission.
- **Database supports the API:** each request field maps to a column or a derived value in
  `docs/02_DATABASE.md`; each documented error condition is enforceable by a constraint, a
  transaction guard or a settings-driven rule.
- **Reports are derivable:** every report endpoint is backed by the views in
  `docs/02_DATABASE.md` section 20 or by an explicit aggregate over documented columns.
- **Every configurable business rule has a storage strategy:** the endpoints consult
  `business_settings` keys, all of which are enumerated in `docs/04_BUSINESS_RULES.md` section 3.
- **Unresolved items:** 25 `CLIENT_DECISION_REQUIRED` items (`docs/04_BUSINESS_RULES.md`
  section 10) currently resolve to documented provisional defaults, not invented policy.