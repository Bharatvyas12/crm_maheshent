# 07 - UI Specification

| Field | Value |
| --- | --- |
| Document owner | Agent 1 - Architect / Tech Lead |
| Status | Baseline (implementation-ready) |
| Version | 1.0 |
| Source-of-truth rank | 8 |
| Applies to | Agent 3 (implements), Agent 5 (verifies) |

This document specifies the frontend: information architecture, screens, states, interaction rules
and presentation of server decisions. It is written for a mobile-first employee experience and a
desktop/tablet-first admin experience inside **one** Next.js application with role-based
navigation.

---

## 1. Principles

1. **Backend is authoritative.** The UI displays and pre-validates; it never decides. No screen may
   compute attendance validity, worked hours, payable days, salary, order ownership, approval state
   or permission.
2. **Server-driven actions.** Screens render allowed actions from server-provided
   `next_allowed_action` / `allowed_transitions[]` rather than hard-coding state rules.
3. **Every mutation has four states:** idle, in-flight (loading, control disabled), success
   (explicit confirmation of the server result), failure (specific, actionable message). Duplicate
   clicks are prevented in the UI **and** protected server-side by idempotency keys and database
   constraints.
4. **Errors are translated, not swallowed.** A stable error `code`/`rule_code` maps to a specific
   message and, where relevant, a next step (see section 11).
5. **Mobile-first for employees.** Primary actions are reachable with the thumb, forms are short,
   buttons are large (>= 44 px), and the layout works on a 360 px-wide viewport.
6. **Desktop/tablet-first for admin.** Dense tables, filters, bulk visibility, keyboard
   navigability; still responsive down to tablet.
7. **No hidden secrets in the client.** Sensitive fields are absent from payloads the server does
   not authorize; the UI must not render placeholders that imply data exists.
8. **Configurable values are never hard-coded.** Thresholds, labels for provisional settings, break
   types, leave types, categories and stages come from the API (`/settings/schema`,
   `/break-types`, `/leave-types`, `/complaint-categories`).
9. **Accessible by default.** WCAG 2.1 AA contrast, focus visibility, labelled inputs, screen
   reader status announcements for async results, and no colour-only meaning.

---

## 2. Stack and Application Structure

| Concern | Decision |
| --- | --- |
| Framework | Next.js (App Router) with React and TypeScript |
| Rendering | Server components for admin tables and detail shells; client components for interactive flows (attendance, claiming, uploads) |
| Data layer | TanStack Query for caching, retries, optimistic-free mutations (no optimistic business state), and cache invalidation after mutations |
| API access | A single typed client generated from the OpenAPI schema, with interceptors for CSRF, `Idempotency-Key`, `X-Request-Id` capture and problem-details parsing |
| Forms | React Hook Form + a schema resolver; validation mirrors the documented limits only as a convenience, and always renders the server's errors |
| Styling | Tailwind CSS with design tokens (section 3) |
| Components | Headless accessible primitives (dialog, menu, tabs, combobox) styled with tokens |
| State | Server state in TanStack Query; local UI state in components; no global store of business truth |
| PWA | Web App Manifest + service worker (app shell, static assets, offline page); no offline mutation queue for business writes except explicitly safe retries |
| i18n | Single locale at MVP; all user-facing copy in one place so it can be internationalized later |
| Money/date formatting | Decimal-string money formatter and timezone-aware date/time formatter using the business timezone from settings |

Route structure (App Router):

```
app/
  (auth)/login, (auth)/change-password
  (employee)/app/...          # employee experience
  (admin)/admin/...           # admin experience
  layout.tsx                  # session bootstrap, permission context, error boundary
```

Navigation is built from the permission list returned by `GET /auth/me`; a route the user lacks
permission for is not rendered in navigation, and the server would reject it anyway.

---

## 3. Design Tokens

| Token group | Values / rules |
| --- | --- |
| Breakpoints | `sm` 640, `md` 768, `lg` 1024, `xl` 1280, `2xl` 1536 (px). Employee layout targets `sm` first; admin tables switch to full width at `lg` |
| Spacing scale | 4 px base: 4, 8, 12, 16, 24, 32, 48 |
| Typography | One sans-serif family; sizes 12/14/16/20/24/30; body 16 px on mobile to avoid input zoom |
| Touch targets | Minimum 44 x 44 px; primary attendance actions 56 px tall |
| Colour | Semantic tokens: `primary`, `success`, `warning`, `danger`, `neutral`, plus surfaces. Status colours: `FULL_DAY` success, `HALF_DAY` info, `PARTIAL_DAY` warning, `ABSENT`/`INCOMPLETE` danger, `ON_LEAVE`/`HOLIDAY`/`WEEKLY_OFF` neutral. Status is always also shown as text, never colour alone |
| Motion | 150-200 ms transitions; respect `prefers-reduced-motion` |
| Density | Comfortable on employee screens; compact on admin tables (32 px rows) |
| Dark mode | Not required for MVP; tokens must not prevent it |

---

## 4. Route Map

### 4.1 Employee (mobile-first, PWA)

| Route | Screen | Key permissions | Primary actions |
| --- | --- | --- | --- |
| `/app` | Dashboard | `attendance.read.self`, `task.read.self`, `order.read.self`, `leave.read.self`, `notification.read.self` | Check In / Start Break / End Break / Check Out, open tasks, available orders |
| `/app/attendance` | Attendance home + history | `attendance.read.self` | Attendance actions, view day detail, request correction |
| `/app/attendance/[date]` | Day detail | `attendance.read.self` | View events and verification result, request correction |
| `/app/attendance/corrections` | My corrections | `attendance.correct.request.self` | Track and cancel requests |
| `/app/tasks` | My tasks | `task.read.self` | Filter by status, open task |
| `/app/tasks/[id]` | Task detail | `task.read.self`, `task.submit.self`, `task.comment` | Start, complete, submit evidence, comment |
| `/app/orders` | Orders | `order.read.available`, `order.read.self` | Available / Mine tabs, claim, update status |
| `/app/orders/[id]` | Order detail | `order.read.self` | Status advance, upload proof, view history |
| `/app/leaves` | Leave | `leave.apply.self`, `leave.read.self` | Apply, view balance and history, cancel |
| `/app/ledger` | My ledger (provisional) | `ledger.read.self`, `advance.read.self` | View entries and outstanding advances |
| `/app/complaints` | Complaints | `complaint.create.self`, `complaint.read.self`, `complaint.comment` | Submit, view status, comment, attach evidence |
| `/app/complaints/[id]` | Complaint detail | `complaint.read.self` | Comment, follow status |
| `/app/notifications` | Notifications | `notification.read.self` | Read, mark read, preferences, enable push |
| `/app/profile` | Profile | `employee.read.self`, `profile.update.self` | Edit permitted fields, change password |

### 4.2 Admin (desktop/tablet-first)

| Route | Screen | Key permissions | Primary actions |
| --- | --- | --- | --- |
| `/admin` | Dashboard | `attendance.read.all`, `task.read.all`, `order.read.all` | KPI cards, today's exceptions, quick links |
| `/admin/employees` | Employee list | `employee.read.all` | Create, filter, open |
| `/admin/employees/[id]` | Employee detail | `employee.read.all`, `employee.update`, role/permission codes | Edit profile, sensitive fields, compensation, roles, deactivate |
| `/admin/attendance` | Attendance register | `attendance.read.all` | Filter by date/employee/status, open day, export |
| `/admin/attendance/[id]` | Day detail + evidence | `attendance.read.all` | View events, verifications, recompute, manual event |
| `/admin/attendance/corrections` | Correction queue | `attendance.correct.approve` | Approve, reject, compare with evidence |
| `/admin/attendance/qr` | Shop QR display | `attendance.qr.generate` | Full-screen rotatable QR with countdown |
| `/admin/tasks` | Task list | `task.read.all` | Create, assign, filter |
| `/admin/tasks/[id]` | Task detail | `task.update`, `task.assign`, `task.cancel` | Edit, assign, cancel, view submissions |
| `/admin/tasks/review` | Review queue | `task.review` | Approve, reject, request resubmission |
| `/admin/orders` | Order list | `order.read.all` | Create, broadcast, filter, reassign, cancel |
| `/admin/orders/[id]` | Order detail | `order.read.all` | Broadcast, reassign, cancel, view history and proof |
| `/admin/leaves` | Leave queue | `leave.read.all`, `leave.approve` | Approve, reject, request modification |
| `/admin/leave-balances` | Balances | `leave.read.all`, `leave.balance.manage` | View, adjust with reason |
| `/admin/complaints` | Complaint list | `complaint.read.all` | Triage, assign, set status |
| `/admin/complaints/[id]` | Complaint detail | `complaint.manage`, `complaint.resolve` | Resolve, reject, close, internal notes |
| `/admin/ledger` | Ledger | `ledger.read.all` | Filter, post entry, reverse |
| `/admin/advances` | Advances | `advance.read.all`, `advance.create`, `advance.approve` | Issue, approve, record repayment, write off |
| `/admin/payroll` | Payroll runs | `salary.read.all` | Create, compute, finalize, lock, pay |
| `/admin/payroll/[runId]` | Run detail + records | `salary.read.all` | Inspect breakdowns, resolve blockers, export |
| `/admin/reports` | Reports | `report.*` | Choose report, filters, view/export |
| `/admin/settings` | Settings | `settings.read`, `settings.update` | Registry-driven forms, provisional flags, history |
| `/admin/roles` | Roles & permissions | `role.read`, `role.manage` | Create role, edit permissions, assign roles |
| `/admin/notifications` | Notifications | `notification.manage` | Broadcast, inspect delivery status |
| `/admin/audit` | Audit log | `audit.read` | Filter, inspect, export |
| `/admin/holidays` | Holiday calendar | `attendance.config.manage` | Add/remove holidays and working-day overrides |

---

## 5. Shared Patterns

### 5.1 List screens

- Filter bar with the filters the endpoint documents; a "clear filters" control; filter state
  reflected in the URL so views are shareable and back/forward works.
- Server-side pagination and sorting; loading skeletons; empty state with a next-step hint.
- Row click opens detail; destructive or state-changing actions are explicit buttons with
  confirmation dialogs, never accidental row clicks.
- Bulk actions only where documented (for example marking notifications read); no bulk
  state transitions that bypass per-entity validation.

### 5.2 Detail screens

- Header with the entity's identity, its current status as text plus colour, and the primary
  action(s) from the server's allowed list.
- A history/timeline section for entities with lifecycle (attendance, tasks, orders, complaints,
  payroll).
- An activity/audit affordance for users who hold audit permission (deep link to filtered audit
  log).

### 5.3 Mutation UX

For every mutation, the UI must implement:

1. **In-flight:** control disabled, spinner, other actions on the same entity blocked.
2. **Success:** server result rendered (not a guessed value); toast plus inline state update; query
   cache invalidated for affected lists.
3. **Failure:** the specific message from the problem-details body, with the offending field
   highlighted for validation errors and a clear recovery action.
4. **Duplicate protection:** an `Idempotency-Key` generated per user intent (not per render),
   reused on retry of the same intent, and regenerated for a genuinely new intent.

### 5.4 Conflict handling

| Server code | UI behavior |
| --- | --- |
| `CLAIM_ALREADY_TAKEN` | Show a distinct conflict panel: "Another employee claimed this order.", reveal who (unless not permitted) and when, refresh the order and the available list, and remove the claim button until the order is available again |
| `STATE_CONFLICT` | Refresh the entity, recompute allowed actions, and explain that the state changed |
| `CONFLICT_DUPLICATE` | Show the conflicting field and its existing value where permitted |
| `IDEMPOTENCY_CONFLICT` | Treat as a client bug: show "this request conflicts with an earlier one", do not auto-retry |
| `PERIOD_LOCKED` | Explain the locked period and offer the adjustment path (or direct the Admin to it) |
| `PERMISSION_DENIED` | Remove the action from the UI and explain that permission is required |
| `RESOURCE_NOT_FOUND` | Navigate to a not-found state without implying that the record exists |
| `RATE_LIMITED` | Show a countdown from `Retry-After` and disable the control |

### 5.5 Network failure and offline

- A global connectivity banner appears when the browser goes offline.
- Read-only screens keep serving cached data with a "last updated" timestamp.
- Attendance, claiming, submissions and financial actions must **not** be queued for silent
  background execution: the UI reports that the action could not be completed and asks the user to
  retry, because verification must be evaluated at the recorded event time.
- Every retry after a network error reuses the same idempotency key so a request that actually
  succeeded server-side is not duplicated.

### 5.6 Status presentation

Statuses always appear as human-readable text with a colour accent and, where useful, an icon. No
screen may require the user to interpret a raw enum.

---

## 6. Employee Experience

### 6.1 Dashboard (`/app`)

- Top card: today's attendance state with the single primary action the server allows
  (`CHECK_IN`, `START_BREAK`, `END_BREAK`, `CHECK_OUT`, or a "day complete" summary).
- Secondary cards in priority order: my open tasks (count + nearest due), available orders (count),
  active claims, leave balance summary, unread notifications.
- If the record is `INCOMPLETE` or has an open session from a previous day, show a prominent
  "needs attention" card linking to corrections.

### 6.2 Attendance actions (`/app/attendance`)

Check-in flow (mirrors W-05):

1. Show the current action and the required evidence ("Location required", "Scan shop QR
   required") derived from the server's verification mode (never guessed).
2. On tap: request browser location permission if needed, with a pre-permission explanation.
3. Show a progress state: "Getting location -> Checking geofence -> Verifying QR -> Confirming with
   server".
4. QR step opens the camera scanner; on scan, show the decoded confirmation before submitting.
5. Submit and then display the **server's** result:
   - success: green confirmation with the resulting state and time;
   - failure: the specific reason (`OUTSIDE_GEOFENCE` with distance, `ACCURACY_EXCEEDS_LIMIT` with
     the measured value, `QR_EXPIRED`/`QR_REPLAYED`, `LOCATION_UNAVAILABLE`/`LOCATION_STALE`), plus
     what to do next.
6. Never show a "checked in" state based on local logic. If the response is unknown (network
   failure), show the unresolved state and re-read today's record.

Break actions: choose a break type from `/break-types`, start, and see a live elapsed timer; end
break returns to the work state. A break is not shown as "on break" until the server confirms.

Check-out mirrors check-in and warns if a break is still open (the server will auto-close it).

### 6.3 Orders

- **Available tab:** cards with order code, item summary, amount, broadcast time, and a Claim
  button; sorting defaults to newest broadcast first; a claim timeout countdown is shown when the
  server provides `claim_expires_at` for the user's own claims.
- **Claiming:** the button disables immediately; on success the order moves to the Mine tab with a
  confirmation toast; on `CLAIM_ALREADY_TAKEN` the conflict panel from section 5.4 is shown.
- **Mine tab:** active and past claims with status, next action, and the claim expiry countdown.
- **Order detail:** item and address details, status stepper built from the server's statuses,
  proof upload (photo with optional note/location), delivery confirmation when configured, and the
  transition history.
- Field work is expected: after `READY_FOR_DELIVERY` the employee is out of the shop, and the UI
  must not nag about location.

### 6.4 Tasks

- List grouped by status with due-date urgency; overdue tasks visually flagged with text.
- Detail shows the brief, attachments, due date, current state and the next allowed action.
- Submission screen: description, evidence attachments with preview, upload progress, and a
  confirmation of the attempt number when resubmitting.
- The employee sees reviewer notes from a rejection or resubmission request, and the history of
  previous attempts.
- Approved tasks move to a completed section and are read-only.

### 6.5 Leave

- Balance cards per leave type with a "how it is calculated" affordance showing the component
  breakdown (entitled, accrued, used, pending, carried forward, adjustments).
- Application form: type, dates, half-day toggle (only when the type allows it), reason, attachment
  when required, and a live preview of the server-computed day count after a validation call.
- History with statuses and decision notes; cancellation available where allowed.

### 6.6 Complaints

- Submit form: category, title, description, priority (if the user may set it), evidence.
- Detail: status timeline, own comments, and a clear indication when content is withheld by policy
  (without revealing that internal content exists).

### 6.7 Notifications and PWA

- In-app list with unread badge, cursor pagination and mark-as-read.
- Push permission is requested contextually (after the user opts in), not on first load.
- Deep links from a notification open the relevant record with permission re-checked by the server.

---

## 7. Admin Experience

### 7.1 Dashboard

Cards: present/absent/incomplete today, open claims and broadcasted-but-unclaimed orders, pending
corrections, pending leave requests, tasks awaiting review, open complaints, and unread
notifications. Every card links to the filtered list that produced the number. Numbers come from
`GET /reports/dashboard-summary`, never from client-side aggregation.

### 7.2 Attendance register and evidence

- Table: employee, date, status, classification, worked hours, break, overtime, late/early,
  anomalies.
- Day detail: the event timeline (punches, breaks, auto-closes) and the verification evidence
  (method, result, coordinates, accuracy, distance, QR outcome, failure reason), which is what makes
  an approval decision defensible.
- Correction queue: side-by-side original vs requested values, the employee's reason and evidence,
  and approve/reject with notes.
- Manual event: only for `attendance.manage`, requires a reason, and is visibly flagged as manual.
- QR display screen: full-screen, high-contrast, auto-rotating code with a countdown, and a warning
  if the token cannot be issued.

### 7.3 Payroll

- Run list by period with status; run detail showing blockers (pending corrections, employees
  without compensation) before finalization.
- Per-employee record with the full breakdown (day credits, gross, overtime, each deduction, net)
  and the rule snapshot hash, so an Admin can explain any number to an employee.
- Explicit, confirmed actions for finalize, lock, unlock and pay, each with a reason where required;
  the UI must make the irreversibility of finalization unmistakable.

### 7.4 Settings

- Forms are generated from `GET /settings/schema`, grouped by module, with type-appropriate
  controls (number, boolean, time, timezone, JSON list, enum).
- Provisional settings (client decisions) are grouped and labelled
  "Provisional - awaiting confirmation", with the decision reference shown.
- Every save requires a reason and shows a before/after diff preview.
- Changing a setting that affects historical computations shows which dates are affected and
  requires explicit acknowledgement before offering a bounded recomputation.
- A history view shows who changed what, when and why.

### 7.5 Audit log

- Filters by category, action, entity, actor and date range; cursor pagination; a detail drawer with
  before/after values rendered as a diff; export with permission.

---

## 8. Attendance UI Rules (Critical Path)

Because attendance is the highest-frequency employee action, these rules are explicit:

1. The UI never decides whether check-in is permitted; it only renders the server's
   `next_allowed_action` and the server's required evidence.
2. Location is requested only when the configured mode requires it, and only at the moment of the
   attendance action. **No continuous location tracking of any kind** is implemented, and no
   background geolocation permission is requested.
3. If the mode allows either GPS or QR (`GPS_OR_QR`), the UI offers both and submits whichever the
   user can provide, surfacing the server's evaluation of each.
4. The QR scanner must handle: permission denied, no camera, malformed code, expired code (offer a
   rescan after refresh), and a code belonging to a different purpose.
5. Failure reasons are presented in plain language with a corrective step; raw codes are available
   only in a details expander for support.
6. A day with an open session from a previous day is surfaced as an unresolved item, not silently
   closed in the client.
7. Worked time displayed to the employee is the server's `worked_hours`; the UI must not compute
   totals from events.

---

## 9. Settings-Driven Forms

Rules for any screen rendering configurable data:

- Option lists (break types, leave types, complaint categories, roles, employees, transitions)
  come from the API.
- Thresholds, labels, units and help text come from `/settings/schema`.
- Enum values are rendered from their documented labels; unknown values are shown verbatim rather
  than hidden.
- Provisional values are visually marked, and the UI must never present a provisional default as
  client-approved policy.
- Any list older than the settings cache TTL is refetched when a settings-dependent screen opens.

---

## 10. PWA and Offline Behavior

| Aspect | Requirement |
| --- | --- |
| Manifest | Name, short name, icons (192/512, maskable), theme and background colours, `display: standalone`, start URL `/app` |
| Service worker | Precaches the app shell and static assets; network-first for API calls; provides an offline fallback page |
| Cached reads | Read-only screens may display cached data with an explicit "offline - showing last loaded data" banner and timestamp |
| Mutation policy | No silent background mutations. Actions attempted while offline fail fast with a clear message; retries reuse the same idempotency key |
| Push | Web push subscription is created only after explicit opt-in, and is removed on logout when the user opts out |
| Install prompt | Shown contextually after a successful session, never on first load |
| Updates | A new service worker version prompts "refresh to update"; the app never renders a mix of old and new bundles |
| Session expiry | A 401 redirects to login while preserving the intended destination for safe (GET) navigation only |

---

## 11. Error and Edge Presentation Map

| Server condition | Message style | Required next step shown |
| --- | --- | --- |
| `LOCATION_UNAVAILABLE` | "We could not read your location." | Enable location permission / move to open sky |
| `LOCATION_STALE` | "Your location reading was too old." | Retry |
| `ACCURACY_EXCEEDS_LIMIT` | "Your location accuracy is not good enough (X m)." | Retry where signal is better |
| `OUTSIDE_GEOFENCE` | "You are X m from the shop; the allowed distance is Y m." | Move closer and retry |
| `QR_EXPIRED` | "This code has expired." | Refresh the shop display and rescan |
| `QR_REPLAYED` | "This code was already used." | Scan the current code |
| `QR_INVALID` | "This is not a valid shop code." | Scan the code shown on the shop display |
| `METHOD_NOT_ALLOWED` (unconfigured geofence/location) | "Attendance verification is not configured yet." | Contact the admin |
| `STATE_CONFLICT` | "The record changed since you opened it." | Refresh and continue |
| `CLAIM_ALREADY_TAKEN` | Conflict panel (section 5.4) | Refresh order and available list |
| `ORDER_PROOF_REQUIRED` | "Delivery proof is required." | Upload the missing proof |
| `LEAVE_OVERLAP` | "You already have leave covering these dates." | Adjust the dates |
| `LEAVE_BALANCE_INSUFFICIENT` | "You do not have enough balance (X of Y days)." | Adjust dates or contact admin |
| `TASK_EVIDENCE_REQUIRED` | "Add a description or evidence before submitting." | Complete the submission |
| `PERIOD_LOCKED` | "This period is locked." | Explain the adjustment path |
| `ADVANCE_LIMIT_EXCEEDED` | "This exceeds the allowed outstanding advance." | Reduce the amount |
| `PERMISSION_DENIED` | "You do not have permission for this action." | Remove the action |
| `RATE_LIMITED` | "Too many attempts." | Countdown from `Retry-After` |
| `VALIDATION_ERROR` | Field-level inline errors | Focus the first invalid field |
| `AUTHENTICATION_REQUIRED` / `SESSION_EXPIRED` | Redirect to login | Preserve destination for GET only |
| `DEPENDENCY_UNAVAILABLE` | "A service is temporarily unavailable." | Retry; show status page link if persistent |
| `INTERNAL_ERROR` | "Something went wrong." | Retry; show the request id for support |

---

## 12. Accessibility and Responsiveness Requirements

- All interactive elements are reachable by keyboard with a visible focus ring; dialogs trap focus
  and restore it on close.
- Form inputs have programmatic labels, `aria-describedby` for help and error text, and
  `aria-invalid` when invalid.
- Async results (check-in success/failure, claim result, upload completion) are announced through an
  ARIA live region.
- Colour is never the only status signal; text and icons accompany it.
- Tables scroll horizontally on small screens rather than truncating data invisibly; the employee
  experience avoids tables in favour of cards.
- Text scales to 200% without loss of function; tap targets remain >= 44 px.
- Images and attachments have accessible names; uploaded evidence previews have text alternatives.
- Tested at 360 px, 768 px, 1024 px and 1440 px widths, and with touch and keyboard input.

---

## 13. Frontend Testing Hooks

- Stable `data-testid` attributes on primary actions and state containers, following
  `<screen>-<entity>-<action>` naming (`attendance-checkin-button`, `order-claim-conflict-panel`).
- A single API error boundary that renders problem-details consistently, so tests can assert on
  codes without depending on copy.
- Deterministic formatters that accept an injected "now" so date/time renderings are testable.
- Tests specified in `docs/09_TEST_PLAN.md` section 9 verify these hooks exist for the critical
  flows.

---

## 14. Client Decisions Affecting the UI

| Decision | UI impact while provisional |
| --- | --- |
| 4 - GPS and/or QR required | Which evidence steps are shown in W-05/W-07 |
| 5 - check-out verification | Whether check-out asks for evidence |
| 6 - break types | Break options and labels |
| 7 - day thresholds | Classification labels and explanatory copy |
| 11 - field duty | Whether leaving the shop raises any warning in the order flow |
| 19 - proof of delivery | Which proof fields appear before DELIVERED |
| 21 - report formats | Which export buttons appear |
| 22 - notification channels | Which preference toggles appear |
| 25 - employee salary/ledger visibility | Whether the ledger screen appears in employee navigation and which fields it shows |

Every one of these is rendered from server data, so confirming the decision changes configuration,
not code.