# 01 - Architecture

| Field | Value |
| --- | --- |
| Document owner | Agent 1 - Architect / Tech Lead |
| Status | Baseline (implementation-ready) |
| Version | 1.0 |
| Source-of-truth rank | 5 (see `AGENTS.md` section 2) |
| Applies to | Agents 2, 3, 4, 5 |
| Supersedes | none |

This document defines the target architecture for the Workforce CRM. It is the contract that
Agent 2 (backend) and Agent 3 (frontend) implement, that Agent 4 audits against real-world
operations, and that Agent 5 verifies for production readiness.

Where this document conflicts with `docs/00_PRODUCT_SCOPE.md` or `docs/04_BUSINESS_RULES.md`,
those documents win. Do not silently change behavior: follow the change protocol in `AGENTS.md`
section 6 and record the conflict.

---

## 1. Purpose and Scope

Build a production-ready, mobile-first Workforce CRM / Employee Operations Management web
application for one small business with:

- 1 Admin
- approximately 20 Employees

The system is a **modular monolith**: a single deployable backend, a single deployable
frontend, one PostgreSQL database, one object-storage bucket. Module boundaries are explicit in
code and enforced, so the system can be split later if a concrete requirement appears, but no
microservices, message brokers, or distributed transactions are introduced for the MVP.

In scope for MVP: authentication, employee management, RBAC, attendance (GPS/geofence +
dynamic QR), breaks, work-hour calculation, attendance correction, tasks and task approval,
orders (broadcast, atomic claim, packing, delivery), leave, employee ledger / salary /
advances, complaints, notifications, reports and exports, audit logs, business settings,
attachments, search/filter/sort.

Out of scope for MVP (see section 27): accounting ERP, inventory, customer CRM pipeline,
commission engine, multi-company accounting, native mobile apps, microservices, continuous GPS
surveillance, AI features.

### 1.1 Design invariants (non-negotiable)

1. **Backend is authoritative.** Permissions, attendance validity, work duration, payable days,
   salary, financial totals, order ownership and approval state are computed and enforced
   server-side. The frontend may display and pre-validate, never decide.
2. **No hidden hard-coding of business policy.** Every value listed in `AGENTS.md` section 3
   and in `docs/04_BUSINESS_RULES.md` section 3 lives in the database-backed settings layer.
3. **Authorization is server-side on every protected operation.** Frontend route guards are UX
   only.
4. **Auditability is preserved.** Important mutations record actor, action, target, previous
   and new state, timestamp and reason where required. Historical financial and attendance
   records are never silently mutated.
5. **Time is timezone-aware; money is decimal.** No naive datetimes. No floating point money.
6. **Concurrency safety is enforced by the database**, not by frontend checks or
   read-then-write logic.

---

## 2. Constraints and Design Principles

| Constraint | Consequence for the design |
| --- | --- |
| ~21 users, low concurrency | Single-region, single-node deployable; vertical scaling is sufficient |
| Modular monolith required | One backend service, one DB, in-process module calls, no network hops between modules |
| REST APIs required | Resource-oriented HTTP JSON API, versioned under `/api/v1` |
| Strong auditability | Append-only audit log, append-only ledger, immutable status history, payroll rule snapshots |
| Mobile-first employee experience | PWA with offline-tolerant UX; small payloads; location/QR only at attendance events |
| No continuous GPS tracking | Location captured only at configured attendance events; field work represented by operational records |
| Small team, minimal ops | No Kafka/RabbitMQ; Postgres is the only stateful dependency besides object storage |
| Client policy not yet final | Every uncertain policy is a setting or a `CLIENT_DECISION_REQUIRED` item, never a literal |

Guiding principles: explicit boundaries over clever abstraction; boring, well-documented
technology; correctness and testability over feature velocity; database constraints as the last
line of defense.

---

## 3. Technology Stack (decided)

Agent 1 finalizes the stack; Agents 2 and 3 implement it. Deviations require a documented
change protocol entry.

| Layer | Choice | Rationale / notes |
| --- | --- | --- |
| Frontend framework | Next.js (App Router) + React + TypeScript | One app, role-based navigation; SSR for admin tables, client interactivity for attendance/orders |
| Frontend data layer | TanStack Query + generated/typed API client | Single place for caching, retry, loading/error state |
| Frontend styling | Tailwind CSS + headless component primitives | Fast responsive/mobile-first UI, accessible primitives |
| PWA | Web App Manifest + service worker (Workbox) | Installable employee experience, app-shell caching |
| Backend framework | Python 3.12 + FastAPI | Async I/O, Pydantic validation, OpenAPI generation |
| Validation/serialization | Pydantic v2 | Request/response contracts, settings typing |
| ORM | SQLAlchemy 2.0 (async) | Explicit queries, unit-of-work, `FOR UPDATE` support |
| Migrations | Alembic | Versioned schema, reviewable DDL |
| Database | PostgreSQL 16 | Transactions, constraints, partial/exclusion indexes, `SELECT FOR UPDATE`, `btree_gist` |
| Background jobs | In-process scheduler (APScheduler) + Postgres advisory locks | Due-date and claim-timeout sweeps without extra infrastructure |
| Object storage | S3-compatible (S3 in prod, MinIO locally) | Private bucket, presigned URLs |
| Cache / rate limit | Postgres-backed where sufficient; Redis optional only if justified | Avoid Redis unless a measured need appears (see 22.3) |
| Auth | Server-side sessions, opaque tokens, Argon2id | Revocable, simple, no JWT revocation problem at this scale |
| Testing | pytest, httpx, testcontainers-postgres; Vitest, Testing Library, Playwright | See `docs/09_TEST_PLAN.md` |
| Packaging | Docker Compose (local), single container per service (prod) | Minimal ops |

**Why server-side sessions instead of JWT:** the workload is small and login is infrequent.
Sessions give instant revocation (deactivation, password change, forced logout), no token
refresh race, and no JWT claim-staleness problem for RBAC. Cost is one indexed row lookup per
request, which is negligible here.

**Redis decision:** not required for MVP. Rate limiting, idempotency keys and scheduler locks
are all PostgreSQL-backed. If latency measurements show a hot path, Redis may be added behind
the same interfaces; it must not become a source of business truth.---

## 4. System Context and Deployment Topology

```
                 +-------------------------------------------+
   Employee      |  Browser / installed PWA (mobile-first)    |
   Admin         |  Next.js app: admin + employee experiences |
                 +--------------------+----------------------+
                                      | HTTPS, JSON, httpOnly session cookie
                                      | + X-CSRF-Token, Idempotency-Key
                                      v
                 +-------------------------------------------+
                 |  Reverse proxy (TLS, HSTS, CORS, size cap) |
                 +--------------------+----------------------+
                                      v
                 +-------------------------------------------+
                 |  FastAPI application (modular monolith)    |
                 |  routers -> services -> repositories       |
                 |  in-process scheduler (advisory-locked)    |
                 +----+-------------------------------+-------+
                      |                               |
                      v                               v
        +----------------------------+   +-------------------------------+
        | PostgreSQL 16 (primary)    |   | S3-compatible object storage  |
        | business truth, audit,     |   | private bucket, presigned     |
        | ledger, outbox, sessions   |   | URLs, no public objects       |
        +----------------------------+   +-------------------------------+
```

Deployment units: `web` (Next.js), `api` (FastAPI), `db` (PostgreSQL), `storage`
(S3-compatible). One region. No message broker. The scheduler runs inside the API process but
is guarded by a Postgres advisory lock so that only one worker executes a given job, which
keeps it correct even if the API is later scaled to multiple replicas.

Environments: `local` (Docker Compose: postgres, minio, api, web), `staging`, `production`.
Staging must not share the production database or bucket.

---

## 5. Repository and Code Layout

```
/
  AGENTS.md
  agent-prompts/
  docs/
    00_PRODUCT_SCOPE.md
    01_ARCHITECTURE.md
    02_DATABASE.md
    03_API_CONTRACT.md
    04_BUSINESS_RULES.md
    05_PERMISSIONS.md
    06_WORKFLOWS.md
    07_UI_SPEC.md
    08_REPORT_SPEC.md
    09_TEST_PLAN.md
  backend/
    app/
      main.py                # FastAPI app factory, middleware, router registration
      core/                  # shared kernel (no domain imports)
        config.py            # env/settings loading and validation
        db.py                # engine, session factory, unit of work
        errors.py            # exception types + problem-details handlers
        security/            # password hashing, token hashing, CSRF, crypto helpers
        authz/               # permission catalog enum, require_permission, object checks
        http/                # pagination, filtering, sorting, idempotency dependencies
        time.py              # business timezone and business-date helpers
        money.py             # Decimal helpers, quantization policy
        storage.py           # object storage client + presigned URL issuance
        events.py            # domain event publishing (outbox)
        logging.py           # structured logging, request id, redaction
        audit.py             # AuditWriter protocol consumed by modules
      modules/
        identity/  directory/  rbac/  settings/  attendance/  tasks/  orders/
        leaves/    payroll/    complaints/  notifications/  files/  audit/  reports/
          router.py   schemas.py   service.py   repository.py   models.py
          rules.py    events.py    (module-specific extras as needed)
      platform/              # outbox dispatcher, idempotency, scheduler jobs
      migrations/            # Alembic
    tests/                   # unit, integration, concurrency, security
    pyproject.toml
  frontend/
    app/                     # routes: (auth), (admin), (employee)
    components/              # shared + feature components
    features/                # feature-scoped hooks/api/state
    lib/                     # api client, auth, formatting, settings
    public/                  # manifest, icons, service worker
    tests/                   # vitest + playwright
    package.json
  infra/                     # compose files, Dockerfiles, deploy manifests, nginx
  scripts/                   # seed, backup, export, admin bootstrap
```

---

## 6. Module Boundaries

Each module owns its tables exclusively and exposes a public interface. Nothing outside a
module may import its `models`, `repository` or `router`.

| Module | Responsibility | Owned tables |
| --- | --- | --- |
| `identity` | Login, logout, sessions, password change/reset, login throttling, security events | `sessions`, `login_attempts` |
| `directory` | Users and employee records, employment status, compensation profile, self-service profile | `users`, `employees`, `employee_compensation` |
| `rbac` | Roles, permission catalog, role-permission mapping, user-role assignment | `roles`, `permissions`, `role_permissions`, `user_roles` |
| `settings` | Typed business settings registry, current values, change history | `business_settings`, `business_setting_history` |
| `attendance` | Attendance events and sessions, breaks, work-hour computation, verification (GPS/QR), corrections, day classification | `attendance_records`, `attendance_events`, `attendance_sessions`, `break_types`, `break_sessions`, `attendance_verifications`, `attendance_corrections`, `attendance_qr_tokens` |
| `tasks` | Task creation/assignment, lifecycle, submissions, review, comments, evidence | `tasks`, `task_assignments`, `task_submissions`, `task_comments`, `task_attachments` |
| `orders` | Order registration, broadcast, atomic claim, fulfillment lifecycle, proof of delivery, reassignment, cancellation | `orders`, `order_broadcasts`, `order_claims`, `order_status_history`, `order_attachments` |
| `leaves` | Leave types, applications, decisions, balances, balance movements | `leave_types`, `leaves`, `leave_balances`, `leave_balance_ledger` |
| `payroll` | Employee ledger, advances, salary computation, payroll runs, rule snapshots | `employee_ledger_entries`, `advances`, `advance_installments`, `salary_records`, `payroll_runs`, `payroll_rule_snapshots` |
| `complaints` | Complaint intake, categories, lifecycle, comments, resolution, visibility | `complaints`, `complaint_categories`, `complaint_comments`, `complaint_attachments`, `complaint_status_history` |
| `notifications` | Notification records, channel delivery, preferences, web-push subscriptions | `notifications`, `notification_deliveries`, `notification_preferences`, `push_subscriptions` |
| `files` | File metadata, validation, storage keys, access authorization | `files` |
| `audit` | Append-only audit log writes and read/export APIs | `audit_logs` |
| `reports` | Read-only aggregation and export generation (no business mutations) | `report_exports` |
| `platform` | Transactional outbox dispatch, idempotency keys, scheduled-job bookkeeping | `domain_events`, `idempotency_keys`, `job_runs` |

Notes:
- Additions beyond the entity list in `agent-prompts/01_architect.md` are justified in
  `docs/02_DATABASE.md` section 2. `attendance_events` is split from
  `attendance_records` because events are append-only while records are derived state.
  `payroll_runs` and `payroll_rule_snapshots` exist to satisfy the auditability requirement
  that historical payroll must not be recomputed from today's rules. `leave_balance_ledger`,
  `employee_ledger_entries` and the `order_*_history` tables exist to satisfy the same
  requirement for balances and lifecycle state.
- `reports` is a read-only consumer. It must never write domain state; its only table holds
  generated export artifacts.

---

## 7. Dependency Rules (enforced)

Allowed dependency directions:

```
core            <- (every module)
audit           <- (every module, write-only)
rbac            <- identity, directory
settings        <- (every domain module)
directory       <- attendance, tasks, orders, leaves, payroll, complaints
files           <- tasks, orders, leaves, payroll, complaints
attendance      <- orders (optional active-attendance check), leaves, payroll, reports
leaves          <- payroll, reports, attendance (attendance reads approved leave)
tasks           <- reports
orders          <- reports
complaints      <- reports
notifications   <- (subscribed via domain events only; no domain imports)
reports         <- (read-only facade over modules)
platform        <- core only
```

Rules:

1. `core` must not import any module.
2. A module may import another module only through that module's `service.py` (or an explicit
   `query.py` facade). Importing another module's `models`, `repository`, `router` or
   `schemas` is forbidden.
3. No dependency cycles. The graph above is acyclic; new edges must be added to this
   document first.
4. Modules communicate state changes through domain events (section 9) when the reaction is
   asynchronous or the consumer must not be coupled to the producer.
5. `notifications` and `reports` never mutate domain state.
6. Cross-module reads of another module's tables must go through the owning module's service
   or a read-only SQL view explicitly documented in `docs/02_DATABASE.md`.

Enforcement: an `import-linter` contract in `backend/pyproject.toml` plus a pytest test
(`tests/test_module_boundaries.py`) that fails when a forbidden import or cycle is introduced.
Agent 2 must make this test part of CI.

---

## 8. Shared Kernel (`app/core`)

The shared kernel contains only genuinely cross-cutting, domain-free concerns:

| Component | Contents |
| --- | --- |
| `config` | Environment loading, typed settings object, startup validation (fail fast on missing secrets) |
| `db` | Async engine, session factory, `UnitOfWork` context manager, transaction helpers |
| `errors` | `AppError` hierarchy (`ValidationError`, `NotFound`, `Conflict`, `PermissionDenied`, `RuleViolation`, `RateLimited`, `IdempotencyConflict`), RFC 9457 problem-details handlers |
| `security` | Argon2id hashing, opaque token generation/hashing, CSRF tokens, constant-time comparison |
| `authz` | `Permission` enum (mirrors `docs/05_PERMISSIONS.md`), `require_permission` dependency factory, object-level authorization helpers |
| `http` | Pagination/filter/sort parsing, `Idempotency-Key` handling, request-id middleware |
| `time` | Business timezone resolution from settings, business-date conversion, duration helpers |
| `money` | `Decimal` helpers, currency quantization, money-safe arithmetic |
| `storage` | Object storage client, key naming, presigned URL issue/verify |
| `events` | Domain event envelope, outbox write API, event type registry |
| `logging` | Structured JSON logging, request correlation, redaction of secrets/PII |
| `audit` | `AuditWriter` protocol; implemented by the `audit` module, injected into services |

`core` must stay free of business policy: it never reads a business setting value directly to
make a business decision, and it never imports a domain module.

---

## 9. Cross-Module Communication: Domain Events and Transactional Outbox

Domain events decouple producers (attendance, tasks, orders, leaves, payroll, complaints) from
consumers (notifications, audit enrichment, derived-state updaters such as attendance
recalculation after an approved leave).

Mechanics:

1. A service performing a state change appends an event row to `domain_events` **inside the
   same transaction** as the state change (transactional outbox).
2. A dispatcher in `platform` polls `domain_events` for undispatched rows, claims a batch with
   `FOR UPDATE SKIP LOCKED`, and invokes registered handlers with at-least-once semantics.
3. Handlers must be idempotent: they key on `event_id` and use upserts or existence checks.
4. Delivery attempts, last error and next-retry time are recorded; failures use exponential
   backoff and are surfaced as operational errors after a configurable attempt limit.

Event envelope: `event_id` (uuid), `event_type` (e.g. `order.claimed.v1`), `occurred_at`
(timestamptz, UTC), `actor_user_id`, `entity_type`, `entity_id`, `payload` (jsonb),
`correlation_id`, `attempts`.

Initial event types (non-exhaustive, versioned with a `.v1` suffix):

- `identity.session.created.v1`, `identity.login.failed.v1`
- `directory.employee.created.v1`, `directory.employee.deactivated.v1`
- `settings.changed.v1`
- `attendance.checked_in.v1`, `attendance.checked_out.v1`, `attendance.break_started.v1`,
  `attendance.break_ended.v1`, `attendance.corrected.v1`, `attendance.record_recalculated.v1`
- `task.assigned.v1`, `task.started.v1`, `task.submitted.v1`, `task.approved.v1`,
  `task.rejected.v1`, `task.resubmission_requested.v1`, `task.cancelled.v1`
- `order.broadcasted.v1`, `order.claimed.v1`, `order.claim_released.v1`,
  `order.status_changed.v1`, `order.reassigned.v1`, `order.cancelled.v1`, `order.failed.v1`,
  `order.delivered.v1`
- `leave.requested.v1`, `leave.approved.v1`, `leave.rejected.v1`, `leave.cancelled.v1`
- `payroll.advance_issued.v1`, `payroll.advance_repaid.v1`, `payroll.salary_finalized.v1`,
  `payroll.ledger_entry_created.v1`
- `complaint.created.v1`, `complaint.status_changed.v1`, `complaint.resolved.v1`

Events are the trigger for notifications, but notification *content* is rendered by the
`notifications` module from the event payload plus settings, so producers stay unaware of
channels.---

## 10. Request Lifecycle and Layering

Every request follows the same layered path. Business logic lives only in services.

```
HTTP request
  -> middleware: request id, logging, CORS, security headers, body-size limit
  -> router: parse/validate request (Pydantic), resolve auth context, declare required permission
  -> authorization dependency: authenticated? has permission? (deny by default)
  -> service: open unit of work -> load settings -> enforce business rules ->
              authorize object-level access -> mutate state -> write audit + outbox ->
              commit
  -> router: serialize response (Pydantic) -> HTTP status
  -> middleware: log outcome (status, duration, request id), redact sensitive fields
```

Rules for implementers:

- Routers do not contain business decisions, arithmetic, or direct SQL.
- Services do not build HTTP responses and do not parse raw requests.
- Repositories do not enforce authorization and do not read settings; they perform data access
  only, with explicit filters passed in by the service.
- A service method is the transaction boundary (section 20). One request may open more than one
  unit of work only when an intermediate commit is genuinely required, which must be documented.
- Object-level authorization is a service responsibility, because only the service knows the
  ownership semantics of the entity it is mutating.

---

## 11. Authentication Strategy

| Aspect | Decision |
| --- | --- |
| Identifier | Email address (unique, case-insensitive) for Admin; employees receive a username derived from `employee_code` and may also use email if provided |
| Credential | Password, hashed with Argon2id (per-user salt, tunable cost, rehash on login when parameters change) |
| Session | Opaque 256-bit random token, returned only in a `HttpOnly`, `Secure`, `SameSite=Lax` cookie; server stores only the SHA-256 hash of the token |
| Session lifetime | Absolute lifetime `security.session_timeout_minutes` (default 720), idle timeout `security.session_idle_timeout_minutes` (default 120), both settings |
| Renewal | Sliding expiry on activity, capped by the absolute lifetime; no refresh-token endpoint |
| Logout | Deletes the session row; all cookies cleared |
| Password change | Requires current password; revokes all other sessions for that user |
| Password reset | Admin-initiated reset that issues a one-time token; the reset token is single-use, hashed at rest, and expires per `security.password_reset_ttl_minutes` |
| Failed logins | Credential failures recorded in `login_attempts`; after `security.max_failed_logins` within `security.lockout_window_minutes`, the account is temporarily locked for `security.lockout_minutes` |
| CSRF | Double-submit token: a non-`HttpOnly` `csrf_token` cookie plus `X-CSRF-Token` header required on all unsafe methods (`POST`, `PUT`, `PATCH`, `DELETE`) |
| Transport | HTTPS only in staging/production; HSTS enabled at the proxy |
| Deactivation | Deactivating an employee immediately revokes sessions; subsequent requests return 401 |
| Bootstrap | Exactly one Admin is created by a CLI bootstrap script (`scripts/create_admin.py`); there is no public signup endpoint |
| Secrets | Signing/crypto keys, DB credentials, storage credentials and SMTP/web-push keys come from environment/secret store, never from the database or repository |

Multi-factor authentication is not required for MVP but the session model supports adding a
second factor step before session creation. Recorded as a future extension, not a MVP task.

Token handling rules: never log tokens, cookie values, passwords, password hashes or reset
tokens. Session and CSRF cookies are excluded from request logging.

---

## 12. Authorization Strategy

Three layers, all server-side:

1. **Route permission.** Each protected route declares a permission from the catalog in
   `docs/05_PERMISSIONS.md`; missing permission yields `403` with code `PERMISSION_DENIED`.
   Unauthenticated requests yield `401` with code `AUTHENTICATION_REQUIRED`.
2. **Object-level authorization (anti-IDOR).** The service verifies that the acting user may
   touch *this* entity. Examples: an employee may read only their own attendance record,
   task assignment, order claim, leave, ledger entry and complaint; an employee may not
   transition an order they do not hold; an employee may not read a file they do not own or
   have not been granted. Failing this check returns `404` when revealing existence would leak
   information, otherwise `403`.
3. **Row-level scoping in queries.** List and report endpoints apply an ownership/visibility
   filter derived from the caller's permissions (`self` scope vs `all` scope) instead of
   filtering in application code after fetching.

Additional rules:

- Deny by default: a route with no declared permission is only allowed if it is explicitly
  public (health, login, static).
- Permission checks use the catalog enum, never string literals scattered in code, so drift is
  detectable.
- Frontend role/route guards are UX only and must never be cited as a security control.
- Sensitive field masking (bank details, salary, another employee's contact data) is applied on
  the server based on the caller's permissions, not hidden in the UI.
- Privilege escalation guards: a user cannot grant a role they do not themselves hold the
  permissions for; the last remaining active Admin cannot be deactivated or stripped of the
  Admin role.

Full permission catalog and role mapping: `docs/05_PERMISSIONS.md`.

---

## 13. API Conventions

Base path: `/api/v1`. Public API metadata: `/api/v1/openapi.json`, interactive docs disabled in
production unless explicitly enabled for internal use.

### 13.1 General

- JSON only for API bodies (`application/json`); file upload uses `multipart/form-data`.
- Field names `snake_case`; identifiers are UUIDv4 (`id`) except human-facing codes
  (`employee_code`, `order_code`, `complaint_code`).
- Timestamps are RFC 3339 with offset, always rendered in UTC (`2026-09-25T09:30:00Z`).
  Business dates are `YYYY-MM-DD` and are interpreted in the business timezone.
- Money is serialized as a JSON string with two decimals (e.g. `"1500.00"`) to avoid
  floating-point ambiguity; clients must treat it as a decimal string.
- Durations are serialized as integer seconds (`worked_seconds`) and, where useful, as decimal
  hours (`worked_hours: "9.50"`).
- Enumerations are `UPPER_SNAKE_CASE` strings.
- Every response includes `X-Request-Id`; the same value appears in logs and in error bodies.
- `GET` requests are side-effect free. State-changing operations use `POST`/`PATCH`/`DELETE`.
- CORS: explicit allow-list of the frontend origin(s); credentials enabled; no wildcard with
  credentials.

### 13.2 Success responses

- Single resource: the resource object directly (no envelope).
- Created resource: `201` with the resource object and a `Location` header.
- No content to return: `204`.
- Collections: a paginated object:

```json
{
  "items": [ ... ],
  "page": 1,
  "page_size": 20,
  "total_items": 137,
  "total_pages": 7
}
```

- Actions that are not pure CRUD are modeled as sub-resources with verbs
  (`POST /orders/{id}/claim`, `POST /attendance/check-in`) and return the resulting resource.

### 13.3 Error format (RFC 9457 problem details)

`Content-Type: application/problem+json`

```json
{
  "type": "https://workforce-crm.local/problems/validation-error",
  "title": "Request validation failed",
  "status": 422,
  "code": "VALIDATION_ERROR",
  "detail": "One or more fields are invalid.",
  "instance": "/api/v1/attendance/check-in",
  "request_id": "0f2a...",
  "errors": [
    { "field": "latitude", "code": "OUT_OF_RANGE", "message": "Latitude must be between -90 and 90." }
  ]
}
```

`errors` is present for validation errors; it may be omitted otherwise. Stable machine-readable
`code` values are part of the contract and must not be renamed without a change-protocol entry.
Initial code set: `AUTHENTICATION_REQUIRED`, `INVALID_CREDENTIALS`, `ACCOUNT_LOCKED`,
`ACCOUNT_DISABLED`, `SESSION_EXPIRED`, `CSRF_INVALID`, `PERMISSION_DENIED`,
`RESOURCE_NOT_FOUND`, `VALIDATION_ERROR`, `RULE_VIOLATION`, `STATE_CONFLICT`,
`CONFLICT_DUPLICATE`, `CLAIM_ALREADY_TAKEN`, `IDEMPOTENCY_CONFLICT`, `RATE_LIMITED`,
`FILE_TOO_LARGE`, `UNSUPPORTED_FILE_TYPE`, `STORAGE_UNAVAILABLE`, `DEPENDENCY_UNAVAILABLE`,
`INTERNAL_ERROR`.

HTTP status mapping: `400` malformed request, `401` unauthenticated, `403` authenticated but
not permitted, `404` not found or intentionally hidden, `409` state/ownership conflict
(including lost order claim), `422` semantic validation failure, `423` payroll period locked
where applicable, `429` rate limited, `500` unexpected, `503` dependency unavailable.

### 13.4 Validation

Validation happens in two places by design:

- Pydantic schemas enforce shape, types, ranges and enumerations at the HTTP edge.
- Services enforce business rules against settings and database state (the authoritative part).

The frontend may replicate cheap client-side checks for responsiveness but must display the
server's authoritative result. Never trust client-supplied: `employee_id` of the actor,
`status`, `amount`, `worked_seconds`, `day_classification`, `role`, `permission`,
`claimed_by`, `approved_by`, `computed_at`, or any financial total.

### 13.5 Pagination, filtering, sorting, search

- Pagination: `?page=1&page_size=20`; `page_size` default 20, maximum 100. Responses include
  `total_items` and `total_pages`. Out-of-range `page` returns an empty `items` array, not an
  error.
- For append-heavy, high-volume lists (`audit_logs`, `notifications`) cursor pagination is
  available via `?cursor=<opaque>&limit=50` returning `{ "items": [...], "next_cursor": "..." }`.
  Offset pagination remains supported for admin table views.
- Filtering: explicit, documented query parameters per endpoint (e.g. `employee_id`,
  `status`, `from`, `to`, `leave_type_id`). Date-range filters use business dates or UTC
  timestamps as documented per endpoint, and are always half-open: `>= from`, `< to`.
- Sorting: `?sort=field` ascending, `?sort=-field` descending, optional secondary
  `?sort=-created_at,employee_code`. Only allow-listed sortable fields are accepted; anything
  else returns `422 VALIDATION_ERROR`.
- Search: `?q=` where a module defines it, implemented with case-insensitive prefix/substring
  matching over documented fields. No arbitrary user-provided SQL fragments.
- Unknown query parameters are rejected with `422` to catch client drift early.

### 13.6 Idempotency and duplicate submission

Unsafe, non-idempotent operations accept an `Idempotency-Key` header (UUID or opaque string,
max 128 chars): order claim, attendance check-in, check-out, break start/end, task submission,
leave application, advance issuance, ledger adjustment, salary finalization, file upload
finalization.

Behavior: the first request with a key executes and stores
`(key, user_id, endpoint, request_hash, response_status, response_body)` in `idempotency_keys`;
a replay with the same key and same request hash returns the stored response with
`Idempotency-Replayed: true`; a replay with the same key but a different request hash returns
`409 IDEMPOTENCY_CONFLICT`. Keys expire after `platform.idempotency_ttl_hours` (default 24).
Where a key is not supplied by the client, the backend still enforces uniqueness through
database constraints (e.g. one active session per employee, one active claim per order), so a
duplicate click can never create duplicate state. The frontend must send keys for the
operations above and must disable the triggering control while in flight.

### 13.7 Rate limiting

Per-identity and per-IP limits on authentication endpoints are mandatory
(`security.rate_limit.login_per_minute`), and configurable limits apply to file uploads,
report/export generation and QR token issuance. Exceeding a limit returns `429 RATE_LIMITED`
with `Retry-After`. Limits are settings, not constants.

### 13.8 Versioning and compatibility

The path version (`/api/v1`) changes only for breaking changes. Additive changes (new optional
request fields, new response fields, new endpoints) are allowed within a version. Removing or
renaming fields, changing types or changing documented error semantics requires a change
protocol entry in `docs/03_API_CONTRACT.md` plus a new version.

---

## 14. File Upload and Storage Strategy

- All files live in a **private** S3-compatible bucket. No public object ACLs, no public bucket
  policy. Objects are addressed by generated keys (`{module}/{yyyy}/{mm}/{uuid}.{ext}`); the
  original filename is stored only as metadata.
- Upload flow: `POST /files` (multipart) validates size (`files.max_upload_mb`), declared MIME
  type and magic-byte signature (`files.allowed_mime_types`), computes a SHA-256 checksum,
  stores the object, and creates a `files` row owned by the uploader. Modules then reference the
  `file_id` (task evidence, order proof, leave attachment, complaint evidence, report export).
- Download flow: `GET /files/{id}/url` returns a short-lived presigned URL (TTL
  `files.presigned_url_ttl_seconds`, default 300) **after** the service authorizes access
  against the relying entity (task, order, leave, complaint) or ownership.
- Every presigned URL issuance is audit-logged (`file.presigned_url_issued`) with actor, file id
  and relying entity.
- Deletion is soft (`files.deleted_at`); physical objects are removed by a retention job only
  when policy allows and no audit requirement retains them.
- Uploads are never executed, never served inline from the app origin, and never unpacked.
  Suggested response headers on any app-origin file response: `Content-Disposition: attachment`,
  `X-Content-Type-Options: nosniff`.
- Virus scanning is optional at MVP scale; the integration point is `files.scan_status`
  (`NOT_SCANNED` / `CLEAN` / `INFECTED` / `FAILED`) so a scanner can be added without schema
  change. Until a scanner exists, uploads are restricted to an allow-list of image/PDF/office
  types.

---

## 15. Notification Abstraction

Notifications are produced from domain events and delivered through pluggable channels.

```
domain event -> notifications service (event type -> template + recipients + preferences)
             -> notifications row (in-app truth)
             -> notification_deliveries rows (one per channel)
             -> channel adapters: IN_APP | WEB_PUSH | EMAIL | SMS | WHATSAPP
```

- The `notifications` module owns templates and recipient resolution; producers never know about
  channels.
- Channels are enabled by settings (`notifications.channels_enabled`), and per-user preferences
  (`notification_preferences`) can suppress non-critical channels but never suppress security
  events.
- MVP implements `IN_APP` (the `notifications` table plus API) and `WEB_PUSH` (VAPID web push
  via `push_subscriptions`). `EMAIL`, `SMS` and `WHATSAPP` are defined as adapter interfaces
  with a `NOT_CONFIGURED` status so future providers plug in without touching core logic.
- Delivery is asynchronous and at-least-once; a failed delivery never rolls back the business
  transaction that produced the event. Failures retry with backoff and surface in delivery
  status.
- Notifications never carry secrets; payloads reference entities by id and the client fetches
  details through authorized endpoints.

---

## 16. Audit Logging

- `audit_logs` is append-only. The application role has `INSERT`/`SELECT` only; `UPDATE` and
  `DELETE` are revoked at the database level. Retention/purge is a separate, explicitly
  authorized maintenance operation.
- Audited categories: security/authentication events, employee changes, role/permission
  changes, settings changes, attendance corrections, work-hour recomputation, task review
  decisions, order reassignment/cancellation/failure, leave decisions and balance adjustments,
  financial changes (ledger entries, advances, salary finalization), complaint resolution,
  file access grants.
- Record shape: `actor_user_id`, `actor_type` (`USER`/`SYSTEM`), `action`
  (e.g. `attendance.correction.approved`), `entity_type`, `entity_id`, `before` (jsonb),
  `after` (jsonb), `reason`, `request_id`, `ip`, `user_agent`, `created_at`.
- Sensitive values are redacted before storage: passwords, tokens, hashes, secrets, and full
  bank/account numbers (store masked form only). Audit records must never become a secondary
  leak channel.
- Audit writes happen in the same transaction as the mutation they describe, so an audited
  change cannot be committed without its audit record.
- `before`/`after` are minimized: only fields that changed, plus identifiers needed for
  reconstruction.
- Read access requires `audit.read`; export requires `audit.export`.---

## 17. Time, Timezone, and Business Date

The distinction between "an instant" and "a business day" is a correctness boundary, not a
formatting detail. Getting it wrong breaks attendance, leave and payroll.

- **Instants** are stored as `timestamptz` in UTC and serialized as RFC 3339 UTC. Examples:
  `occurred_at`, `created_at`, `expires_at`, `claimed_at`.
- **Business dates** are stored as `date` and mean "that calendar date in the business
  timezone". Examples: `attendance_records.business_date`, `leaves.start_date`,
  `advances.issued_on`, `payroll_runs.period_year/period_month`.
- The business timezone is `org.timezone` (IANA identifier, e.g. `Asia/Kolkata`), a setting.
  All business-date derivation uses it. Server local time is never used for business logic.
- Day boundary: a business day runs `[00:00:00, 24:00:00)` in the business timezone. A shift
  that crosses midnight (for example 22:00 to 06:00) still belongs to the business date on
  which it started, per `attendance.shift_crosses_midnight` (setting), and the record's
  `business_date` is stamped at check-in time using the business timezone.
- Months and years for payroll/leave use business-timezone boundaries. "September 2026 payroll"
  means `2026-09-01` to `2026-09-30` inclusive in the business timezone.
- DST: timestamps are offset-aware, so arithmetic is performed on instants (no DST arithmetic
  bugs); date-range filters are converted to instants using the business timezone offset rules
  of `zoneinfo`. The business timezone in the initial deployment has no DST, but the code path
  must not assume that.
- Clients send offsets with timestamps and `YYYY-MM-DD` for business dates. Clients must not
  compute authoritative business dates; the server derives and returns them
  (`business_date` is a response field, never a trusted request field).
- Durations are computed from instants, then attributed to a business date using the rule above.

Setting `org.timezone` is one of the 25 client decisions (item 24 in
`docs/00_PRODUCT_SCOPE.md` section 15). Default for development seed data: `Asia/Kolkata`.

---

## 18. Money and Numeric Handling

- All monetary values are PostgreSQL `numeric(14,2)` mapped to Python `Decimal`. Floating point
  (`float`, `REAL`, `DOUBLE PRECISION`) is forbidden for money anywhere in the stack, including
  intermediate calculations, report aggregation and the frontend (the frontend treats money as
  strings and formats with a decimal library).
- Rounding policy: quantize to 2 decimal places with `ROUND_HALF_UP`. The rounding moment is
  defined per rule in `docs/04_BUSINESS_RULES.md`; rounding must not happen more than once in a
  computation chain to avoid drift.
- Currency is `org.currency` (ISO 4217, setting). MVP is single-currency; a `currency` column is
  stored on money-bearing rows so multi-currency does not require a migration.
- Rates (per-hour, per-day) are stored as `numeric(14,2)` or higher precision
  (`numeric(14,4)` for hourly rates) and converted with explicit quantization.
- Totals shown in reports must be recomputed with the same decimal rules as the source
  computation; aggregate SQL uses `SUM(numeric)` (exact), never `sum(float)`.
- Negative amounts are represented by a `direction`/`entry_type` plus a non-negative `amount`
  where a ledger is involved, so sign confusion cannot silently invert a balance. Reversals are
  new entries referencing the reversed entry, never in-place edits.

---

## 19. Duration Handling

- Durations are stored as integer **seconds** (`worked_seconds`, `break_seconds`,
  `overtime_seconds`) and derived displays use decimal hours with 2 decimals
  (`worked_hours = seconds / 3600`, quantized `ROUND_HALF_UP`).
- Using integer seconds avoids fractional accumulation and makes work-hour math exactly
  reproducible and auditable.
- Configurable hour thresholds (required daily hours, full-day threshold, and so on) are stored
  as decimal hours in settings and converted to seconds once, at comparison time, using a single
  documented conversion (`Decimal(hours) * 3600`, quantized to the nearest second
  `ROUND_HALF_UP`).
- Overlapping intervals are merged before summation so double-punching cannot inflate worked
  time.

---

## 20. Transaction Boundaries

- One service method = one transaction (unit of work). The unit of work commits on success and
  rolls back on any exception.
- Inside a transaction, in this order: validate inputs -> load and lock required rows -> read
  settings -> enforce business rules -> write state -> write audit record -> write domain event
  (outbox) -> commit.
- Audit records and domain events are written in the same transaction as the change they
  describe. Notifications and other side effects happen after commit, driven by the outbox.
- No external network calls (S3, web push, email) inside a database transaction. Long or
  failure-prone work is deferred: the transaction records intent, the post-commit handler
  performs it.
- Read-only report endpoints run in a read-only transaction (optionally
  `REPEATABLE READ`/snapshot) so multi-query reports are internally consistent, and must never
  hold locks on hot tables for long periods.
- Nested transactions are expressed as savepoints only where a partial failure must be tolerated
  and documented; they are not a general pattern.
- Every write endpoint's transaction is short and bounded; unbounded loops inside a transaction
  (for example recalculating a year of payroll) are batched.

---

## 21. Concurrency Strategy

The guiding rule: **make the database reject the invalid outcome**, so correctness does not
depend on timing or on the frontend.

| Scenario | Mechanism |
| --- | --- |
| Two employees claim the same order | Conditional `UPDATE` guarded by status and null owner plus a partial unique index on active claims (see 21.1) |
| Duplicate check-in | Partial unique index: at most one open attendance session per employee; service returns the existing open session state with `409 STATE_CONFLICT` or an idempotent replay |
| Duplicate check-out / break start / break end | State machine guard: transition allowed only from the expected current state; otherwise `409 STATE_CONFLICT` |
| Duplicate task submission | `(assignment_id, attempt_no)` unique plus state guard; resubmission requires `RESUBMISSION_REQUESTED` state |
| Duplicate financial submission | `Idempotency-Key` plus unique natural key (`employee_id`, `period_year`, `period_month`) on `salary_records` |
| Concurrent attendance correction approval | `SELECT ... FOR UPDATE` on the correction row; second approver sees `409` |
| Concurrent leave approval affecting balance | `SELECT ... FOR UPDATE` on the `leave_balances` row before applying movements |
| Concurrent balance/ledger updates | All balance-affecting writes take a row lock in a deterministic order (per employee, then per type) to avoid deadlock; ledger rows are append-only |
| Stale edit of a mutable business document | `version` integer column with optimistic locking: `UPDATE ... WHERE id = :id AND version = :expected`; zero rows affected yields `409 STATE_CONFLICT` |
| Scheduler running on multiple replicas | Postgres advisory lock (`pg_try_advisory_lock`) per job name |
| Outbox dispatch by multiple workers | `SELECT ... FOR UPDATE SKIP LOCKED` batch claim |

### 21.1 Order claiming (canonical example)

Order claiming is the highest-risk concurrency path in the product. Exactly one claim may
succeed, and it must be decided by the database.

```
BEGIN;
-- 1) conditional state transition; only one concurrent transaction can match
UPDATE orders
   SET status = 'CLAIMED', current_assignee_id = :employee_id, claimed_at = now()
 WHERE id = :order_id
   AND status = 'BROADCASTED'
   AND current_assignee_id IS NULL;
-- 2) if 0 rows were affected -> another claimant won: ROLLBACK, return 409 CLAIM_ALREADY_TAKEN
-- 3) insert the claim; partial unique index guarantees a single ACTIVE claim even if
--    two different code paths race
INSERT INTO order_claims (order_id, employee_id, status, claimed_at)
VALUES (:order_id, :employee_id, 'ACTIVE', now());
-- 4) append status history, audit record, outbox event
-- 5) COMMIT
```

Supporting database guarantees:

- `UNIQUE (order_id) WHERE status = 'ACTIVE'` on `order_claims`.
- A check constraint that `orders.current_assignee_id IS NULL` for non-assigned states and
  non-null for assigned states (see `docs/02_DATABASE.md`).
- The loser receives `409` with code `CLAIM_ALREADY_TAKEN` and the current order state, so the
  UI can refresh and show a clear conflict.

Agent 2 must write a concurrency test that fires two simultaneous claims at the same order and
asserts exactly one `200` and one `409`, with exactly one `ACTIVE` claim row (see
`docs/09_TEST_PLAN.md` section 7).

---

## 22. Background Jobs and Scheduled Work

All scheduled work is expressed as an idempotent, advisory-locked job that can run on any
replica and be re-run safely. Job bookkeeping lives in `job_runs` (job name, started_at,
finished_at, status, items_processed, last_error).

| Job | Cadence | Purpose |
| --- | --- | --- |
| `outbox_dispatch` | every 5s | Dispatch `domain_events` to handlers (notifications, derived state) |
| `attendance_auto_close` | every 15 min | Apply `attendance.missing_checkout_policy` to stale open sessions per business rules |
| `attendance_recompute` | every 30 min | Recompute derived day classification for open/adjusted records |
| `order_claim_sweeper` | every 1 min | Release claims past `orders.claim_timeout_minutes` (`order.claim_released.v1`, order returns to pool per settings) |
| `task_due_reminder` | hourly | Notify assignees of tasks approaching/overdue, per `tasks.reminder_hours_before_due` |
| `leave_accrual` | monthly (configurable day) | Apply `leaves.accrual_mode` accruals to `leave_balances` |
| `notification_retry` | every 5 min | Retry failed channel deliveries with backoff |
| `qr_token_sweeper` | hourly | Expire/consume stale QR tokens and mark replays as denied |
| `report_export_cleanup` | daily | Remove expired export artifacts per retention settings |
| `retention_purge` | daily | Apply configured retention policy (audit, notifications, exports) where policy allows |

Job requirements: each job must be safe to run twice, must record its run, must log an outcome
summary, and must never perform an unbounded scan (use bounded batches with a documented
watermark). Jobs must not silently mutate historical financial or attendance records; derived
recalculation is allowed only through documented rules and must itself be audited.

---

## 23. Configuration, Secrets, Environments

Two distinct concepts, deliberately separated:

1. **Technical configuration (environment variables)** - database URL, object storage
   credentials/endpoint/bucket, session cookie name/domain, SMTP/web-push provider credentials,
   log level, allowed CORS origins, scheduler enable flag. Loaded at startup and validated; the
   app fails fast if required values are missing or malformed.
2. **Business configuration (database settings)** - geofence coordinates and radius, GPS
   accuracy tolerance, QR validity, required daily hours, thresholds, leave policy, salary
   settings, claim timeout, and everything else in `AGENTS.md` section 3 and
   `docs/04_BUSINESS_RULES.md` section 3. Stored in `business_settings`, editable by an Admin at
   runtime, versioned and audited.

Rules: secrets never appear in the repository, in logs, in API responses, or in the database.
`.env.example` documents required variables with placeholder values only. Business settings are
never read from environment variables and never hard-coded, because they must be changeable by
the client without a deployment. Technical constants that are genuinely technical (JSON content
type, HTTP status codes, hash algorithm choice, batch sizes) are allowed as code constants.

---

## 24. Observability and Logging

- Structured JSON logs to stdout: timestamp, level, logger, message, request_id, user_id (when
  authenticated), route, method, status, duration_ms, and module. No tokens, cookies, passwords,
  secrets, or full PII payloads.
- Central redaction filter for known-sensitive keys (`password`, `token`, `authorization`,
  `cookie`, `csrf`, `secret`, `bank_account`), applied to both logs and audit bodies.
- Health endpoints: `GET /api/v1/health` (liveness, cheap) and `GET /api/v1/health/ready`
  (readiness: database reachable, migrations at head, storage reachable or degraded flag).
- Metrics (if enabled): request counts/latencies by route and status, job durations and
  failures, outbox lag, notification delivery failures. Exposed on an internal endpoint only.
- Error tracking: unexpected exceptions are logged with request id and stack trace server-side;
  clients receive a generic problem-details body without internals.
- Audit log plus structured logs together must be sufficient to reconstruct who changed what,
  when, and why for any audited action.

---

## 25. Security Baseline Mapping

Each item from `AGENTS.md` section 8 is addressed as follows.

| Baseline concern | Where handled |
| --- | --- |
| Authentication | Section 11; Argon2id, server-side sessions, throttling, lockout |
| Authorization / RBAC | Section 12; `docs/05_PERMISSIONS.md` |
| IDOR | Section 12.2 object-level authorization; `docs/09_TEST_PLAN.md` negative authorization tests |
| Privilege escalation | Section 12 (no self-escalation, last-Admin protection), role assignment restricted to `role.manage` |
| Input validation | Section 13.4; Pydantic at edge plus service-level rule checks |
| File upload security | Section 14; private bucket, allow-list, magic-byte checks, presigned URLs, no execution |
| SQL injection | SQLAlchemy parameter binding only; no string-built SQL; identifiers from allow-lists |
| XSS | React escaping by default; no `dangerouslySetInnerHTML` on user content; strict content-type on file responses; CSP at the proxy |
| CSRF | Section 11 double-submit token on unsafe methods |
| Rate limiting | Section 13.7; settings-driven |
| Secure cookies / tokens | Section 11 `HttpOnly`, `Secure`, `SameSite=Lax`; tokens hashed at rest |
| Secret management | Section 23; environment/secret store only |
| Audit logging | Section 16; append-only, transactional, redacted |
| Least privilege | DB roles: app role has no DDL, no `UPDATE`/`DELETE` on audit; `/health` and reports are read-only paths |
| Sensitive data exposure | Section 12.3 field masking, minimal payloads, redacted logs, PII not returned unless permitted |

---

## 26. Business Rule / Settings Layer (overview)

The settings layer is the single mechanism that satisfies "no hidden hard-coding".

- `business_settings` holds the current value of each key: `key` (dotted, unique),
  `value_type` (`STRING`/`INT`/`DECIMAL`/`BOOL`/`JSON`/`TIME`/`TIMEZONE`/`DURATION_SECONDS`),
  `value` (jsonb, typed on read), `description`, `updated_by`, `updated_at`, `version`.
- `business_setting_history` is an append-only snapshot written on every change (old value, new
  value, actor, reason, timestamp), satisfying auditability for rule changes.
- A code-level registry (`SETTING_DEFINITIONS`) declares each key's type, default, validation
  range, unit, and the module that consumes it. Unknown keys are rejected; missing keys fall back
  to declared defaults so the system is never undefined.
- Settings are cached per request (request-scoped, invalidated on change); they are never
  cached across requests in a way that hides an Admin's change for long.
- `settings.changed.v1` is emitted on change and audit-logged with before/after.
- Payroll snapshots the exact settings used for a computation into
  `payroll_rule_snapshots`, so historical salary is reproducible and never silently
  recalculated from today's rules.

The complete key registry, defaults and consumer modules are in `docs/04_BUSINESS_RULES.md`
section 3.

---

## 27. Explicitly Deferred (Non-Goals)

Not built for MVP; the architecture must not prevent them later. Adding any of these requires a
change protocol entry.

- Accounting ERP, inventory management, customer CRM pipeline, complex commission engine,
  multi-company accounting.
- Native Android/iOS applications (PWA is the mobile strategy).
- Microservices, message brokers, distributed transactions, event sourcing.
- Continuous GPS surveillance / location streaming.
- AI features of any kind.
- Multi-location geofencing: MVP supports exactly one configured shop location via settings.
  Supporting several locations requires a `locations` table, `location_id` foreign keys on
  attendance events and QR tokens, and per-location settings - a documented future migration,
  not an MVP deliverable.
- Email/SMS/WhatsApp delivery adapters (interfaces defined, providers not integrated).
- Multi-factor authentication.

---

## 28. Open Client Decisions (`CLIENT_DECISION_REQUIRED`)

These are unresolved client policies. The architecture stores each one as a setting or a
documented switch, with a safe default, so implementation can proceed. Every item must be
confirmed before production. Full detail and defaults are in `docs/04_BUSINESS_RULES.md`
section 10; the list mirrors `docs/00_PRODUCT_SCOPE.md` section 15:

1. Shop location and permitted geofence radius
2. GPS accuracy tolerance
3. Dynamic QR rotation/validity duration
4. Whether GPS and QR are both always required, or one may act as fallback
5. Check-out verification rule
6. Break types and whether only lunch is tracked
7. Full-day / half-day / partial-day formula
8. Overtime calculation
9. Late / early policy
10. Missing checkout handling
11. Field-duty handling
12. Leave types and yearly/monthly balances
13. Salary formula
14. Advance deduction policy
15. Payroll lock / finalization process
16. Order claim timeout
17. Who may reassign orders
18. Order cancellation rules
19. Required proof of delivery
20. Complaint privacy / visibility rules
21. Required report formats
22. Notification channels
23. Data retention policy
24. Business timezone
25. Employee access to salary/ledger details

Until confirmed, the system must not hard-code an answer: it must expose the setting, use the
documented default, and label the behavior as provisional.

---

## 29. Architecture Handoff Summary (Agents 2-5)

**What exists now:** the stack is fixed, module boundaries and dependency rules are defined,
cross-cutting policies (auth, authorization, errors, validation, pagination, idempotency, files,
notifications, audit, time, money, transactions, concurrency, jobs) are specified, and the nine
`docs/` specification documents are the implementation contract.

**Agent 2 (backend) - start here.** Implement in this order: core kernel (config, db, errors,
security, authz, http, time, money, storage, events, logging, audit protocol) -> `identity` +
`directory` + `rbac` -> `settings` -> `attendance` -> `tasks` -> `orders` -> `leaves` ->
`payroll` -> `complaints` -> `notifications` -> `files` -> `audit` -> `reports` -> `platform`
jobs. Enforce section 7 with an import-linter test. Implement section 21.1 and its concurrency
test early, because order claiming is the highest-risk path. Every business number you are
tempted to write as a literal belongs in `business_settings` (see `docs/04_BUSINESS_RULES.md`
section 3).

**Agent 3 (frontend) - start here.** One Next.js app with role-based navigation: admin
(desktop/tablet-first) and employee (mobile-first, PWA). Build the API client, session/CSRF
handling, and permission-driven navigation from `docs/05_PERMISSIONS.md`; then the employee
attendance flow including location and QR, task flow, order claim conflict handling, leave,
complaints, ledger view, notifications; then the admin areas. Never compute authoritative
values client-side; render server results. Follow `docs/07_UI_SPEC.md`.

**Agent 4 (domain) - start here.** Audit implementation against `docs/04_BUSINESS_RULES.md` and
`docs/06_WORKFLOWS.md`, especially attendance verification and work-hour math, atomic claiming,
leave balances, payroll snapshots and absence of silent financial mutation. Produce
`docs/DOMAIN_AUDIT.md`.

**Agent 5 (QA/security) - start here.** Use `docs/09_TEST_PLAN.md` as the test contract,
including concurrency and negative-authorization tests, report cross-checks and production
readiness. Produce `docs/QA_REPORT.md`, `docs/SECURITY_REPORT.md`,
`docs/PRODUCTION_CHECKLIST.md`.

**Known limitations of this specification:** the client decisions in section 28 are unresolved
and currently represented by configurable defaults; multi-location support, provider
integrations and virus scanning are deferred by design; final payroll semantics and report
formats require client confirmation before production sign-off.