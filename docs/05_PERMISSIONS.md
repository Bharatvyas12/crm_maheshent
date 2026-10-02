# 05 - Permissions, Roles and Security

| Field | Value |
| --- | --- |
| Document owner | Agent 1 - Architect / Tech Lead |
| Status | Baseline (implementation-ready) |
| Version | 1.0 |
| Source-of-truth rank | 3 |
| Applies to | Agents 2, 3, 4, 5 |

This document defines the authorization model, the complete permission catalog, the seeding role
mapping, object-level authorization rules, sensitive-data boundaries and the security
requirements that must hold server-side.

`AGENTS.md` section 3 is binding here: **authorization is server-side**, frontend guards are UX
only, and hidden buttons never protect functionality.

---

## 1. Authorization Model

Four layers, all enforced on the server:

1. **Authentication** - a valid, unexpired, non-revoked session resolves to a user
   (`docs/01_ARCHITECTURE.md` section 11). Otherwise `401 AUTHENTICATION_REQUIRED`.
2. **Route permission** - the route declares a permission code from the catalog in section 3.
   The acting user's effective permissions must include it, otherwise `403 PERMISSION_DENIED`.
3. **Object-level authorization** - the service verifies the actor may act on *this specific*
   entity, using the ownership rules in section 5. Failing this returns `404` when revealing
   existence is itself a leak, otherwise `403`.
4. **Row-level scoping** - list, report and export queries apply an ownership/visibility filter
   derived from the caller's permissions (`self` scope vs `all` scope) in SQL, never by fetching
   everything and filtering in application code.

Additional properties:

- **Deny by default.** A route without an explicit permission declaration is only reachable if it
  is on the small public allow-list (health, login). Everything else requires a declaration.
- **Permission checks use the catalog enum**, not string literals, so drift between code and this
  document is detectable in tests.
- **Effective permissions** = union of the permissions of all roles assigned to the user
  (`user_roles` -> `role_permissions` -> `permissions`). Resolution is per-request; a permission
  change applies to the next request.
- **Scope naming convention:** a `.self` suffix means "own records only"; the corresponding
  unsuffixed or `.all` code means "any record in the business". A user may hold both.
- **Roles are data, not code.** New roles can be created and composed from the same catalog. The
  two seeded roles (`ADMIN`, `EMPLOYEE`) are system roles and cannot be deleted.

---

## 2. Role Seeding Summary

| Role | Composition | Notes |
| --- | --- | --- |
| `ADMIN` | Every permission in the catalog | System role. Bootstrapped by `scripts/create_admin.py`. Cannot be deleted or reduced below the catalog minimum |
| `EMPLOYEE` | The `.self` set plus order claiming, file upload and complaint submission (section 4) | System role. Default role for new employees |

Deliberate design choices:

- There is no `MANAGER` role in the MVP because the product scope names only Admin and Employee.
  The catalog is granular enough that a future `SUPERVISOR` role can be composed without code
  changes (for example adding `attendance.read.all`, `task.review`, `leave.approve`).
- `ADMIN` is a role, not a superuser bypass: even Admin requests flow through the same permission
  checks, which keeps the model honest and testable. The only difference is that `ADMIN` holds
  everything.
- Multiple roles may be assigned to one user (`PUT /users/{id}/roles`); permissions are additive.
  There is no negative permission concept - removing a role removes its permissions.

---

## 3. Permission Catalog

`is_sensitive` marks capabilities over money, permissions, audit or other people's personal data.
The admin UI groups these separately and treats them as high-risk to grant.

### 3.1 Authentication and session

| Code | Description | Sensitive |
| --- | --- | --- |
| `auth.session.read.self` | View own active sessions | no |
| `auth.session.revoke.self` | Revoke own sessions | no |
| `auth.password.change.self` | Change own password | no |
| `employee.manage.credentials` | Trigger a password reset for another user | yes |

### 3.2 Employee and user management

| Code | Description | Sensitive |
| --- | --- | --- |
| `profile.update.self` | Update own permitted profile fields | no |
| `employee.read.self` | Read own employee profile | no |
| `employee.read.all` | Read any employee profile | no |
| `employee.read.sensitive` | Read sensitive employee fields (bank details) | yes |
| `employee.create` | Create employees and their user accounts | yes |
| `employee.update` | Update employee profile and employment fields | yes |
| `employee.update.sensitive` | Update bank details and other sensitive fields | yes |
| `employee.deactivate` | Deactivate, reactivate or exit an employee | yes |
| `employee.manage.roles` | Assign roles to users | yes |

### 3.3 Roles and permissions

| Code | Description | Sensitive |
| --- | --- | --- |
| `role.read` | Read roles and their permissions | no |
| `role.manage` | Create, update and delete roles; change role permissions | yes |
| `permission.read` | Read the permission catalog | no |

### 3.4 Business settings

| Code | Description | Sensitive |
| --- | --- | --- |
| `settings.read` | Read business settings and the settings schema | no |
| `settings.update` | Change business settings | yes |
| `settings.read.history` | Read settings change history | yes |

### 3.5 Attendance, breaks and verification

| Code | Description | Sensitive |
| --- | --- | --- |
| `attendance.checkin.self` | Check in | no |
| `attendance.checkout.self` | Check out | no |
| `attendance.break.self` | Start/end own breaks | no |
| `attendance.read.self` | Read own attendance records, events and break types | no |
| `attendance.read.all` | Read any employee's attendance, including verification evidence | yes |
| `attendance.manage` | Record manual attendance events and trigger recomputation | yes |
| `attendance.config.manage` | Manage break types and the holiday calendar | yes |
| `attendance.qr.generate` | Issue dynamic shop QR tokens | yes |
| `attendance.correct.request.self` | Request a correction to own attendance | no |
| `attendance.correct.approve` | Approve or reject attendance corrections | yes |

### 3.6 Tasks

| Code | Description | Sensitive |
| --- | --- | --- |
| `task.create` | Create tasks and assign employees | no |
| `task.read.self` | Read own task assignments and submissions | no |
| `task.read.all` | Read any task, assignment and submission | no |
| `task.update` | Update task details and brief attachments | no |
| `task.assign` | Add or remove assignments | no |
| `task.cancel` | Cancel a task | no |
| `task.submit.self` | Start, complete and submit own assignments | no |
| `task.comment` | Comment on tasks and assignments | no |
| `task.review` | Approve, reject or request resubmission | yes |

### 3.7 Orders

| Code | Description | Sensitive |
| --- | --- | --- |
| `order.create` | Register orders | no |
| `order.read.available` | See broadcasted orders available to claim | no |
| `order.read.self` | Read orders currently or previously held by the caller | no |
| `order.read.all` | Read any order, its history and attachments | yes |
| `order.update` | Edit order details | no |
| `order.broadcast` | Broadcast or re-broadcast an order | no |
| `order.claim` | Claim and release orders | no |
| `order.update.status.self` | Advance the status of an order the caller holds | no |
| `order.update.status.any` | Advance the status of any order | yes |
| `order.proof.upload` | Upload packing/delivery proof | no |
| `order.reassign` | Reassign or force-release an order | yes |
| `order.cancel` | Cancel an order | yes |

### 3.8 Leave

| Code | Description | Sensitive |
| --- | --- | --- |
| `leave.apply.self` | Apply for own leave | no |
| `leave.read.self` | Read own leave, types and balances | no |
| `leave.read.all` | Read any employee's leave and balances | yes |
| `leave.cancel.self` | Cancel own leave request | no |
| `leave.cancel.any` | Cancel any employee's leave | yes |
| `leave.approve` | Approve, reject or request modification | yes |
| `leave.type.manage` | Manage leave types | yes |
| `leave.balance.manage` | Adjust leave balances | yes |

### 3.9 Ledger, advances, salary and payroll

| Code | Description | Sensitive |
| --- | --- | --- |
| `ledger.read.self` | Read own ledger entries and balance | yes |
| `ledger.read.all` | Read any employee's ledger | yes |
| `ledger.entry.create` | Post manual ledger entries and advance repayments | yes |
| `ledger.entry.adjust` | Reverse or adjust ledger entries; write off advances | yes |
| `advance.read.self` | Read own advances | yes |
| `advance.read.all` | Read any employee's advances | yes |
| `advance.create` | Issue an advance | yes |
| `advance.approve` | Approve, reject or write off an advance | yes |
| `salary.read.self` | Read own salary records and payslips | yes |
| `salary.read.all` | Read any employee's salary records | yes |
| `salary.compute` | Create payroll runs and compute salary records | yes |
| `salary.finalize` | Finalize a payroll run and its salary records | yes |
| `payroll.lock` | Lock a payroll period | yes |
| `payroll.unlock` | Unlock a payroll period | yes |
| `payroll.pay` | Mark a payroll run as paid and post payment entries | yes |

### 3.10 Complaints

| Code | Description | Sensitive |
| --- | --- | --- |
| `complaint.create.self` | Submit a complaint | no |
| `complaint.read.self` | Read own complaints | no |
| `complaint.read.all` | Read any complaint | yes |
| `complaint.read.internal` | Read internal comments and notes | yes |
| `complaint.comment` | Comment on a complaint | no |
| `complaint.manage` | Change status, priority, category, visibility or assignment | yes |
| `complaint.resolve` | Resolve or reject a complaint | yes |
| `complaint.close` | Close a resolved complaint | yes |

### 3.11 Notifications, files, reports and audit

| Code | Description | Sensitive |
| --- | --- | --- |
| `notification.read.self` | Read and manage own notifications and preferences | no |
| `notification.manage` | Broadcast notifications and inspect delivery status | no |
| `file.upload` | Upload files | no |
| `file.read.all` | Download any file (subject to entity authorization) | yes |
| `file.delete` | Delete files not yet referenced by a submitted record | yes |
| `report.attendance` | Run attendance, work-hour, break and overtime reports | yes |
| `report.tasks` | Run task reports | no |
| `report.orders` | Run order reports | no |
| `report.leaves` | Run leave reports | yes |
| `report.ledger` | Run ledger and advance reports | yes |
| `report.salary` | Run salary reports | yes |
| `report.complaints` | Run complaint reports | yes |
| `report.export` | Generate and download report exports | yes |
| `audit.read` | Read the audit log | yes |
| `audit.export` | Export the audit log | yes |

Total: 96 permissions.

---

## 4. Seeded Role Mapping

### 4.1 `ADMIN`

Grants **every** permission in section 3 (96 of 96). Implementation note: the seed inserts one
`role_permissions` row per catalog entry, so the mapping is explicit, reviewable and testable
rather than a wildcard evaluated at runtime.

### 4.2 `EMPLOYEE`

Grants exactly the following 28 permissions:

| Module | Permissions |
| --- | --- |
| Authentication | `auth.session.read.self`, `auth.session.revoke.self`, `auth.password.change.self` |
| Profile | `profile.update.self`, `employee.read.self` |
| Attendance | `attendance.checkin.self`, `attendance.checkout.self`, `attendance.break.self`, `attendance.read.self`, `attendance.correct.request.self` |
| Tasks | `task.read.self`, `task.submit.self`, `task.comment` |
| Orders | `order.read.available`, `order.read.self`, `order.claim`, `order.update.status.self`, `order.proof.upload` |
| Leave | `leave.apply.self`, `leave.read.self`, `leave.cancel.self` |
| Ledger | `ledger.read.self`, `advance.read.self` |
| Complaints | `complaint.create.self`, `complaint.read.self`, `complaint.comment` |
| Notifications | `notification.read.self` |
| Files | `file.upload` |

Explicitly **not** granted to `EMPLOYEE` (selected high-impact examples):
`salary.read.self` (pending client decision 25), `attendance.read.all`, `attendance.manage`,
`task.review`, `order.read.all`, `order.reassign`, `order.cancel`, `leave.approve`,
`ledger.read.all`, `ledger.entry.create`, `advance.create`, `complaint.read.all`,
`complaint.read.internal`, `settings.*`, `audit.*`, `report.*`, `notification.manage`,
`employee.*` (except `employee.read.self`).

Note that `ledger.read.self` and `advance.read.self` are `is_sensitive` (they expose financial
data) but are granted to `EMPLOYEE` provisionally per client decision 25; the Admin can revoke
them by adjusting the role, and the seed documents this as provisional.

---

## 5. Object-Level Authorization Rules

These rules are the anti-IDOR contract. They are enforced in the service layer for every read and
write, and they are the basis of the security tests in `docs/09_TEST_PLAN.md` section 6.

| Resource | Read | Write / transition | Ownership rule |
| --- | --- | --- | --- |
| User session | own only | own only (revoke) | `sessions.user_id = actor.id` |
| Employee profile | `employee.read.all`, or self with `employee.read.self` | `employee.update`, or self for allow-listed fields | self = `employees.user_id = actor.id` |
| Sensitive employee fields | `employee.read.sensitive` only | `employee.update.sensitive` only | never returned to the employee themselves unless granted |
| Compensation | `employee.read.sensitive` | `employee.update.sensitive` | admin-only |
| Roles / permissions | `role.read`, `permission.read` | `role.manage`, `employee.manage.roles` | role assignment additionally subject to escalation guards (section 8) |
| Settings | `settings.read` | `settings.update` | admin-only |
| Attendance record | `attendance.read.all`, or self with `attendance.read.self` | events only through the attendance endpoints; corrections through the correction flow | `attendance_records.employee_id = actor.employee_id` |
| Attendance events / verifications | `attendance.read.all`, or self | never editable; created by attendance or correction flows | as above |
| Attendance correction | `attendance.correct.approve` (all), or own | approve/reject with `attendance.correct.approve`; cancel own while pending | subject of the correction may not approve it |
| Break type / holiday | `attendance.read.self` (active only) | `attendance.config.manage` | admin-only |
| QR token | `attendance.qr.generate` | issue with `attendance.qr.generate`; consume only via check-in/out | consumption requires a valid employee session |
| Task | `task.read.all`, or `task.read.self` for own assignment | `task.update`/`task.assign`/`task.cancel`; employee actions with `task.submit.self` on own assignment | `task_assignments.employee_id = actor.employee_id` for employee actions |
| Task submission | `task.read.all`, or own assignment | create with `task.submit.self` on own assignment; decide with `task.review` | reviewer must not be the assignee or the submitter |
| Order | `order.read.all`; holder with `order.read.self`; available pool with `order.read.available` | `order.update` / `order.broadcast` / `order.cancel` / `order.reassign` / `order.update.status.any` for admins; holder paths require the caller to be the active assignee | holder = the single `ACTIVE` claim's `employee_id` |
| Order history / attachments | `order.read.all`, or holder | created by the transitions that produce them | as above |
| Leave | `leave.read.all`, or own with `leave.read.self` | apply/cancel own; `leave.approve` / `leave.cancel.any` for admins | approver must not be the subject |
| Leave balance | `leave.read.all`, or own | `leave.balance.manage` for adjustments | movements must reference the correct employee |
| Ledger | `ledger.read.all`, or own with `ledger.read.self` | `ledger.entry.create`/`ledger.entry.adjust` | admin-only writes; self is read-only |
| Advance | `advance.read.all`, or own with `advance.read.self` | `advance.create`/`advance.approve` | approver must not be the beneficiary |
| Salary record | `salary.read.all`, or own with `salary.read.self` | `salary.compute`/`finalize`, `payroll.*` | employee is read-only on their own record |
| Payroll run | `salary.read.all` | `salary.compute`/`finalize`, `payroll.lock`/`unlock`/`pay` | separation of duties (section 8) |
| Complaint | `complaint.read.all`; raiser with `complaint.read.self`; visibility rules in `docs/04_BUSINESS_RULES.md` section 4.11 | `complaint.manage`/`resolve`/`close`; raiser may comment | internal comments require `complaint.read.internal`; a subject employee never sees a complaint about them by default |
| Notification | own only | own only (read, preferences) | `notifications.recipient_user_id = actor.id`; `notification.manage` may broadcast but cannot read others' inbox |
| File | uploader, or the relying entity's authorization, or `file.read.all` | uploader may soft-delete while unreferenced; `file.delete` otherwise | authorization is delegated to the owning module |
| Report | per report permission | exports via `report.export` | employee-scoped reports apply a self filter automatically |
| Audit log | `audit.read` | none (immutable) | admin-only; exports require `audit.export` |

---

## 6. Sensitive Data Boundaries and Masking

| Classification | Data | Exposure rule |
| --- | --- | --- |
| Public within the app | Order codes, task titles, own attendance, own leave, break types, holidays | Returned to any authenticated user with the relevant permission |
| Internal | Other employees' names, department, designation, employment status, order claim ownership, aggregate order counts | Returned only where the workflow needs it (admin views, task assignment lists). Employee-facing payloads must not include other employees' personal data |
| Sensitive | Attendance verification evidence, corrections, leave decisions, advances, ledger entries, bank details, contact details, complaint subjects | Requires the specific permission; masked or omitted otherwise |
| Restricted | Salary records and payslips, payroll run details, audit logs, permission changes | Requires explicit sensitive permissions; never included in employee-facing aggregates; never in logs |

Masking rules:

- `bank_account_number` is returned masked (last 4 digits) unless the caller holds
  `employee.read.sensitive`.
- Salary and ledger amounts are omitted entirely (field absent, not zero) for callers without the
  permission, so a UI bug cannot turn "absent" into "0.00".
- Complaint internal comments and internal status notes are filtered out at the serializer level.
- Verification evidence for other employees requires `attendance.read.all`.
- Logs and audit records redact secrets, tokens, passwords and full bank numbers
  (`docs/01_ARCHITECTURE.md` sections 16 and 24).
- Error messages never reveal whether a hidden resource exists: unauthorized object access
  returns the same body as a missing resource.

---

## 7. Security Requirements

Each requirement from the architect brief, with its enforcement point. Agent 5 verifies these in
`docs/SECURITY_REPORT.md`.

### 7.1 Authentication

- Argon2id password hashing with per-user salt; rehash on login when parameters change.
- Server-side sessions with opaque 256-bit tokens; only SHA-256 hashes stored.
- `HttpOnly`, `Secure`, `SameSite=Lax` cookies; CSRF double-submit token required on all unsafe
  methods.
- Absolute and idle timeouts from settings; sliding renewal capped by the absolute timeout.
- Failed-login tracking with temporary lockout; all auth events audited.
- No public signup. Admin bootstrap is a CLI operation.
- Password reset tokens are single-use, hashed at rest, expiring, and revoke existing sessions.
- `must_change_password` is honoured: the API rejects business operations until the password is
  changed, except the change-password and session endpoints.

### 7.2 Session and token strategy

| Concern | Decision |
| --- | --- |
| Storage | Database table `sessions` (revocable, inspectable) |
| Revocation | On logout, password change, employee deactivation, admin action, or security event |
| Rotation | Not applicable for opaque session cookies; the token is created once per login |
| Transport | Cookie only; never in local storage, never in URLs |
| CSRF | Double-submit token bound to the session (`csrf_token_hash`) |
| Logout scope | Current session only; "log out everywhere" revokes all sessions for the user |

### 7.3 Object-level authorization (IDOR)

Covered by section 5. Additionally:

- Every list endpoint applies scope filters in SQL.
- Every `{id}` route loads the entity, checks scope, and returns `404` when out of scope.
- Identifiers are UUIDv4, so ids are not enumerable.
- Reports and exports apply the same scope as their detail endpoints.
- Files delegate authorization to the relying entity; an unreferenced file is visible only to its
  uploader and `file.read.all`.

### 7.4 File security

- Private bucket, no public objects, no public bucket policy.
- Upload validation: size limit, MIME allow-list, magic-byte signature check, checksum computed.
- Original filenames are metadata only and never used as storage paths.
- Downloads are short-lived presigned URLs issued only after authorization, and issuance is
  audited.
- Files are never executed, never unpacked, and never served inline from the app origin.
- Soft delete; physical removal only when unreferenced and permitted by retention policy.
- Optional virus scanning integration point (`files.scan_status`), off by default.

### 7.5 Rate limiting

Per-identity and per-IP limits, all settings-driven: login attempts, attendance events, uploads,
report/export generation, QR issuance. Exceeding a limit returns `429 RATE_LIMITED` with
`Retry-After`. Authentication endpoints are the most tightly limited. Failed verification attempts
(attendance) are rate limited to prevent brute-forcing the QR/geofence checks.

### 7.6 Audit requirements

Audited (see also `docs/01_ARCHITECTURE.md` section 16): authentication and session events,
employee changes, role and permission changes, settings changes (with before/after and reason),
attendance corrections and recomputations, task review decisions, order broadcast, claim,
reassignment, cancellation, failure and delivery, leave decisions and balance adjustments, every
financial entry, advance lifecycle, salary computation, finalization, lock/unlock and payment,
complaint resolution and visibility changes, file presigned-URL issuance, and export generation.

Requirements: audit writes are transactional with the change; `UPDATE`/`DELETE` on `audit_logs`
are revoked from the application role; sensitive values are redacted before storage; audit access
requires `audit.read` and is itself auditable when `audit.log_reads` is enabled.

### 7.7 Secret handling

- All secrets come from environment variables or a secret manager: database credentials, session
  signing material if used, object storage keys, web-push VAPID keys, and future provider keys.
- Secrets are never committed, never stored in `business_settings`, never returned by an API, and
  never written to logs or audit records.
- `.env.example` documents variable names with placeholder values only.
- Secrets are rotated by redeploying the environment; the application reads them at startup and
  fails fast if a required secret is missing or malformed.
- Separate credentials per environment; staging never has production credentials.

### 7.8 Injection, XSS, CSRF and transport

- SQL: SQLAlchemy parameter binding only; no string-built SQL; sort/filter fields come from
  allow-lists, never interpolated into queries.
- XSS: React escaping by default; no `dangerouslySetInnerHTML` for user content; strict
  `Content-Type` on API responses; `Content-Security-Policy` set at the proxy; file responses use
  `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`.
- CSRF: double-submit token on all unsafe methods, validated against the session.
- Transport: HTTPS enforced in staging/production with HSTS; CORS restricted to the frontend
  origin with credentials enabled and no wildcard.
- Security headers at the proxy: HSTS, CSP, `X-Content-Type-Options`, `Referrer-Policy`,
  `X-Frame-Options: DENY`.
- Request body size caps at the proxy and in the application to prevent memory exhaustion.

### 7.9 Least privilege (database and runtime)

- The application database role has DML only on business tables: no DDL, and `INSERT`/`SELECT`
  only on `audit_logs`, `employee_ledger_entries`, `leave_balance_ledger`,
  `order_status_history`, `complaint_status_history`, `attendance_events` and `domain_events`.
- Migrations run with a separate, more privileged role and are not executed by the API at runtime.
- The API process runs as a non-root user in a minimal container.
- Report/export queries run in a read-only transaction with statement timeouts.
- `/health` and `/health/ready` expose no sensitive internals beyond status and version.

---

## 8. Privilege Escalation and Administrative Protections

| Risk | Control |
| --- | --- |
| Self-escalation | A user may not grant themselves a role or permission; `employee.manage.roles` and `role.manage` changes are audited with before/after code lists |
| Granting permissions the actor lacks | A role change may not introduce a permission the acting user does not hold, unless the actor holds `role.manage` **and** the change is to a role they are authorized to manage; grants beyond the actor's own set require an explicit audited override by a different Admin |
| Last-admin lockout | The last active user holding `role.manage` cannot be deactivated, disabled or stripped of the role (`LAST_ADMIN_PROTECTED`) |
| Admin self-approval | Admin may not approve their own leave, attendance correction, advance or task submission (except `leaves.allow_admin_self_approval`, default false) |
| Payroll single-actor risk | `salary.compute`, `salary.finalize` and `payroll.pay` are separate permissions; finalization requires resolved corrections; the run records who computed, finalized and paid |
| Silent financial edits | Ledger and finalized salary rows are append-only/immutable at the database level, not merely in service code |
| Session theft persistence | Password change and deactivation revoke sessions; `must_change_password` gates business operations; suspicious auth events are audited |
| Role deletion with users | Deleting a role in use is refused; system roles cannot be deleted |
| Settings tampering | Settings changes require `settings.update`, a reason, and write to history; sensitive settings (`is_sensitive` capability grouping) are highlighted in the UI |

---

## 9. Permission-to-Workflow Consistency Check (Agent 1)

The architect brief requires that permissions match workflows. Verified by walking every workflow
in `docs/06_WORKFLOWS.md` and confirming the required permission exists and is granted to the
correct role.

| Workflow | Required permissions | Held by |
| --- | --- | --- |
| Login / session management | `auth.*.self` | both roles |
| Password change / admin reset | `auth.password.change.self` / `employee.manage.credentials` | both / admin |
| Employee onboarding | `employee.create`, `employee.update.sensitive`, `employee.manage.roles` | admin |
| Employee deactivation | `employee.deactivate` (+ `order.reassign`, `task.assign` for forced cascade) | admin |
| Check-in / break / check-out | `attendance.checkin.self`, `attendance.break.self`, `attendance.checkout.self` | employee (+ admin) |
| QR issuance | `attendance.qr.generate` | admin |
| Attendance correction | request: `attendance.correct.request.self`; decide: `attendance.correct.approve` | employee / admin |
| Manual attendance event and recompute | `attendance.manage` | admin |
| Break types and holidays | `attendance.config.manage` | admin |
| Task assignment and execution | `task.create`, `task.assign` / `task.submit.self` | admin / employee |
| Task review | `task.review` | admin |
| Order create/broadcast | `order.create`, `order.broadcast` | admin |
| Order claim and fulfill | `order.claim`, `order.update.status.self`, `order.proof.upload` | employee (+ admin) |
| Order reassign/cancel | `order.reassign`, `order.cancel` | admin |
| Leave apply / decide | `leave.apply.self` / `leave.approve` | employee / admin |
| Leave balance adjust | `leave.balance.manage` | admin |
| Ledger and advance administration | `ledger.entry.create`, `ledger.entry.adjust`, `advance.create`, `advance.approve` | admin |
| Payroll | `salary.compute`, `salary.finalize`, `payroll.lock`, `payroll.unlock`, `payroll.pay` | admin |
| Employee financial self-view | `ledger.read.self`, `advance.read.self` (+ `salary.read.self` pending decision 25) | employee (granted provisionally) / admin |
| Complaints | `complaint.create.self`, `complaint.comment` / `complaint.manage`, `complaint.resolve`, `complaint.close` | employee / admin |
| Notifications | `notification.read.self` / `notification.manage` | both / admin |
| Reports and exports | `report.*`, `report.export` | admin (employee-scoped only if granted) |
| Audit | `audit.read`, `audit.export` | admin |
| Settings | `settings.read` / `settings.update`, `settings.read.history` | admin (read may be granted more widely) |

Result: every workflow has a permission, every permission belongs to at least one workflow, and
no workflow depends on a permission that only the wrong role holds.

---

## 10. Open Items

- Client decision 25 (employee access to salary/ledger detail) determines whether
  `salary.read.self` is added to `EMPLOYEE`. Default: not granted; `ledger.read.self` and
  `advance.read.self` provisionally granted.
- Whether the client wants an anonymous complaint capability (decision 20) affects
  `complaints.allow_anonymous` and the audit attribution rules.
- Whether a future supervisor/manager role is needed. The catalog already supports it with no code
  change; no such role is created in MVP because the product scope defines only Admin and
  Employee.
- Multi-factor authentication is a documented future extension, not an MVP requirement.