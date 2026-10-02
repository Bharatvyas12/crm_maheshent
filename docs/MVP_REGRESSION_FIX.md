# MVP Regression Fix - Investigation and Restoration

Snapshot: 2026-09-28 (Asia/Calcutta)
Scope: regression investigation + MVP restoration for Admin and Employee experiences.
Owners involved: Agent 2 (backend) and Agent 3 (frontend) implementation areas; no architecture change.

> Note: the workspace root is **not** a git repository (`git status`/`git diff`/`git log` all
> report "not a git repository"), so "what changed recently" was reconstructed from file
> modification timestamps and from reading the current source. No `git reset`/revert was used.

---

## 1. Root causes found

### RC-1 (primary) - Frontend did not honour the documented collection envelope

`docs/01_ARCHITECTURE.md` section 13.2 fixes the success contract:

- single resource -> the resource object directly (no envelope);
- **collections -> an object carrying `items`** (`{ "items": [...], "page", "page_size",
  "total_items", "total_pages" }`, or `{ "items": [...] }` for non-paginated lookups).

The backend follows this contract. The frontend API layer did **not**: a block of list
functions were declared as bare arrays (`api.get<X[]>`) and the pages consumed them with
`data.map(...)`, `data.length`, `data.filter(...)`, `for (const x of data)`. Because the actual
response is `{ items: [...] }`, every one of those sites threw
`(intermediate value).map is not a function` or silently rendered nothing.

The originally reported crash is exactly this:

```
src/components/attendance/AttendanceActionPanel.tsx  -> breakTypes.data.map(...)
```

A previous partial "fix" had wrapped a handful of these sites in
`Array.isArray(...) ? ... : data.items ? ... : []`, which hid the symptom instead of matching the
contract. Those defensive shims have been removed.

### RC-2 - Same root cause, wider blast radius

The envelope mismatch was not limited to break types. It also broke (or silently emptied) the
admin/employee pages for complaint categories, complaint comments, leave types, leave balances,
employee compensation, order status history, notification preferences, active sessions, the
permission catalog, the report catalog, and the settings schema/list. This is why "multiple
unrelated sections" appeared broken at once - they all consume collection endpoints.

### RC-3 - Documentation-referenced seed entry point was missing

`app/seed.py` documents that it is "used by `scripts/seed.py`", and `docs/02_DATABASE.md`
(section on seeding) and `docs/05_PERMISSIONS.md` reference idempotent seed bootstrap scripts.
`backend/scripts/` contained only `local_smoke.py`. The safe, data-preserving permission repair
path therefore had no runnable entry point. Added `backend/scripts/seed.py` (RC-3).

### Not a root cause: Admin RBAC seed and QR issuance

Problems 2 (Admin 403 on `/employees`) and 3 (Shop QR "token could not be issued") are **not
reproducible** against the current code + database. Verified live (details in section 6):

- ADMIN role has all 96 catalog permissions in the database (including `employee.read.all`);
  EMPLOYEE has exactly 28. `GET /employees` returns `200` for Admin and `403` for Employee.
- `POST /attendance/qr-tokens` returns `201` with a `qr_payload`, `nonce`, `expires_at` and
  `rotation_seconds`; the required settings (`attendance.qr_validity_seconds`,
  `attendance.qr_rotation_seconds`) and location settings exist.

The most likely earlier cause was stale local state: a session/permission view cached client-side
(`staleTime: 30_000`) or a database whose role/permission rows had not been (re)seeded when the
page was first loaded. The RBAC seed is now confirmed correct and a safe repair path exists.

---

## 2. Recent change that caused each regression

No VCS history is available, so this is evidence-based:

| Regression | Recent change | Evidence |
| --- | --- | --- |
| RC-1 / RC-2 collection `.map is not a function` | Frontend API/page layer drifted from the documented `{items}` envelope. Frontend files were the most recently edited (attendance api/hooks/pages at 09:21-13:35, leaves/complaints pages at 13:34-14:19). Several call sites had `Array.isArray(...)` symptom shims added (attendance/leaves/compensation/comments) instead of matching the contract. | `listBreakTypes`, `listLeaveTypes`, `listComplaintCategories`, `listPermissions`, `getReportCatalog`, `fetchSettingsSchema`/`listSettings`, `listCompensation`, `fetchNotificationPreferences`, `fetchMySessions`, `getOrderHistory` all declared bare arrays while the backend returns `{items}`. The existing `AttendanceActionPanel.test.tsx` mock already supplied `{ items: [...] }`, confirming the intended shape. |
| RC-3 missing seed CLI | The documented `scripts/seed.py` was never committed/created. | `app/seed.py:3` docstring + `docs/02_DATABASE.md` reference it; file absent. |

---

## 3. Files changed

### Frontend - contract type layer

- `frontend/src/lib/types.ts` - added `ListResponse<T> { items: T[]; total?: number }`.
- `frontend/src/features/complaints/api.ts` - `listComplaintCategories`,
  `listComplaintComments` now `ListResponse<...>`.
- `frontend/src/features/rbac/api.ts` - `listPermissions` -> `ListResponse<PermissionCatalogItem>`.
- `frontend/src/features/reports/api.ts` - `getReportCatalog` -> `ListResponse<ReportCatalogItem>`.
- `frontend/src/features/settings/api.ts` - `fetchSettingsSchema`, `listSettings`,
  `updateSettings` -> `ListResponse<...>`.
- `frontend/src/features/employees/api.ts` - `listCompensation` -> `ListResponse<CompensationRow>`.
- `frontend/src/features/notifications/api.ts` - `fetchNotificationPreferences`,
  `updateNotificationPreferences` -> `ListResponse<NotificationPreference>`.
- `frontend/src/features/auth/api.ts` - `fetchMySessions` -> `ListResponse<SessionInfo>`.
- `frontend/src/features/orders/api.ts` - `getOrderHistory` -> `ListResponse<OrderHistoryEntry>`.
- `frontend/src/features/tasks/api.ts` - `assignTask` -> `ListResponse<TaskAssignment>`.

### Frontend - consumers updated to read `.items` (and symptom shims removed)

- `frontend/src/components/attendance/AttendanceActionPanel.tsx` (break types; removes `Array.isArray` shim)
- `frontend/src/app/(employee)/app/attendance/page.tsx` (break types; removes shim)
- `frontend/src/app/(employee)/app/leaves/page.tsx` (leave balances/types; removes shim)
- `frontend/src/app/(admin)/admin/leaves/page.tsx` (leave types)
- `frontend/src/app/(admin)/admin/leave-balances/page.tsx` (leave types x2)
- `frontend/src/app/(employee)/app/complaints/page.tsx` (categories x2)
- `frontend/src/app/(admin)/admin/complaints/page.tsx` (categories)
- `frontend/src/app/(admin)/admin/complaints/[id]/page.tsx` (comments; removes shim)
- `frontend/src/app/(employee)/app/complaints/[id]/page.tsx` (comments)
- `frontend/src/app/(employee)/app/orders/[id]/page.tsx` (status history)
- `frontend/src/app/(admin)/admin/orders/[id]/page.tsx` (status history)
- `frontend/src/app/(admin)/admin/employees/[id]/page.tsx` (compensation; removes shim)
- `frontend/src/app/(employee)/app/profile/page.tsx` (active sessions)
- `frontend/src/app/(admin)/admin/settings/page.tsx` (schema + settings list)
- `frontend/src/app/(admin)/admin/roles/page.tsx` (permission catalog)
- `frontend/src/app/(admin)/admin/reports/page.tsx` (report catalog + settings)
- `frontend/src/app/(employee)/app/notifications/page.tsx` (preferences)
- `frontend/src/app/(admin)/admin/notifications/page.tsx` (preferences)
- `frontend/src/app/(employee)/app/page.tsx` (leave balances on the dashboard)

### Backend

- `backend/scripts/seed.py` - **new** idempotent seed/repair entry point (see section 4).

No backend router/service/model, database migration, permission catalog entry or business-rule
setting was changed. No authorization or attendance verification was weakened or faked.

---

## 4. Database / seed changes

- No schema migration was added or altered.
- No database rows were deleted or reset.
- The seeded RBAC state was verified correct: `ADMIN` = 96 permissions, `EMPLOYEE` = 28
  permissions, matching `app/core/authz.py` and `docs/05_PERMISSIONS.md`.
- Added `backend/scripts/seed.py` and ran it against the `crm` database. It is idempotent and
  created nothing (`settings: 0, break_types: 0, leave_types: 0, complaint_categories: 0,
  admin_created: 0`), proving the reference data and role/permission mappings were already intact.

Safe repair command (does **not** wipe data; safe to re-run):

```powershell
cd C:\Users\admin\Desktop\crm_maheshent\backend
python scripts\seed.py
```

This re-syncs settings, break types, leave types, complaint categories, the permission catalog,
the `ADMIN`/`EMPLOYEE` role -> permission mappings, and ensures the Admin user exists.
It never deletes employees, attendance, orders, ledger or any other business data.

---

## 5. API contract issues

There were **no backend contract defects**; the backend already matched
`docs/01_ARCHITECTURE.md` section 13.2. The defect was on the frontend, which assumed bare
arrays. Resolved by typing and consuming the documented `items` envelope. Confirmed live response
shapes (Admin session unless noted):

| Endpoint | Shape |
| --- | --- |
| `GET /employees` | `{items, page, page_size, total_items, total_pages}` |
| `GET /break-types`, `GET /leave-types`, `GET /complaint-categories` | `{items}` |
| `GET /leave-balances/mine`, `GET /notification-preferences` | `{items}` |
| `GET /auth/sessions`, `GET /orders/{id}/history`, `GET /employees/{id}/compensation`, `GET /complaints/{id}/comments` | `{items}` |
| `GET /permissions`, `GET /reports/catalog`, `GET /settings`, `GET /settings/schema` | `{items, total}` |
| `GET /audit-logs` | `{items, next_cursor}` (cursor page) |
| `POST /tasks/{id}/assignments` | `{items}` |
| `POST /attendance/qr-tokens` | single resource (no envelope) |

No accepted contract (`docs/03_API_CONTRACT.md`) was renamed or changed.

---

## 6. Verification performed

Environment services were (re)started with the project-documented commands:

- PostgreSQL: `.local\pgsql\bin\pg_ctl.exe -D .local\pgdata-full -w -l .local\pg16.log -o "-p 55432 -h 127.0.0.1" start`
- Backend: `cd backend; python run_dev.py`
- Frontend: `cd frontend; npm run dev`

Checks and results:

- **Backend health**: `GET /health` -> `200 {"status":"ok",...}`.
- **Auth / RBAC (live)**: Admin login -> `200`, roles `[ADMIN]`, 96 permissions including
  `employee.read.all`; Employee login -> `200`, roles `[EMPLOYEE]`, 28 permissions.
- **Admin employees (problem 2)**: `GET /employees` -> `200` for Admin (`{items,...}`);
  `403 Missing permission: employee.read.all` for Employee (correct authorization).
- **Admin shop QR (problem 3)**: `POST /attendance/qr-tokens` (SHOP_CHECKIN and SHOP_CHECKOUT)
  -> `201` with a non-empty `qr_payload`; `qr_validity_seconds`/`qr_rotation_seconds` settings
  present.
- **Employee dashboard (problem 1)**: all dashboard endpoints `200`
  (`/attendance/me/today`, `/attendance/me/summary`, `/reports/dashboard-summary`,
  `/orders/available`, `/leave-balances/mine`, `/notifications/unread-count`, `/break-types`).
  `AttendanceActionPanel.test.tsx` (13 tests) passes against the `{items}` break-types mock, so
  the panel no longer throws `.map is not a function`.
- **Frontend typecheck**: `npm run typecheck` -> clean (0 errors).
- **Frontend unit tests**: `npm test` -> **10 files, 80 tests passed**.
- **Frontend production build**: `npm run build` -> compiled successfully, **37 routes**
  generated (including `/admin/tasks/review`, which only failed earlier because a build was run
  concurrently with the dev server sharing `.next`).
- **Frontend dev server page render**: `/login`, `/`, `/app`, `/admin/employees`,
  `/admin/attendance/qr`, `/admin/roles`, `/admin/settings`, `/admin/reports`, `/app/leaves`,
  `/app/complaints`, `/app/notifications`, `/app/profile` all returned `200`.
- **Backend test suite**: `crm_test` with
  `DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:55432/crm_test` -> **72 passed**.
- **End-to-end smoke** (`backend/scripts/local_smoke.py`) -> **49 passed / 7 failed**. The 7
  failures are accumulated-development-state, not code defects:
  - `employee claims order` and the 5 cascading order transitions -> the seeded `employee` already
    holds `orders.max_active_claims_per_employee` (3) active claims left by previous smoke runs.
  - `employee applies for leave` -> the smoke picks a random date 45-325 days ahead, exceeding
    the configured maximum advance window.

---

## 7. Remaining known issues / notes

1. **Smoke test is not idempotent against accumulated state** (active claims cap, random future
   leave date). It passes on a fresh dev database; repeated runs require the older claims to be
   released/closed or the smoke date window to be adjusted. This is a test-harness concern, not
   an application defect, and was left unchanged to avoid widening scope.
2. **`frontend/.env.local` uses `http://localhost:8000/api/v1`** while `python run_dev.py` binds
   `127.0.0.1:8000` (IPv4 only). Browsers fall back from `::1` to `127.0.0.1`, so the app works
   in-browser, but some non-browser clients that resolve `localhost` to `::1` first fail to
   connect. If this becomes a problem, point `NEXT_PUBLIC_API_BASE_URL` at `127.0.0.1` or let the
   `next.config.mjs` rewrite (`/api/*` -> `127.0.0.1:8000`) handle it by unsetting the variable.
   Left as-is because it is existing environment configuration.
3. **`localhost`-vs-`127.0.0.1` cookie note**: login and CSRF cookies are host-scoped. Use a single
   host consistently (the current `.env.local` uses `localhost` throughout), otherwise the
   session/CSRF cookies set for one host are not sent to the other.
4. No `CLIENT_DECISION_REQUIRED` item was resolved or invented during this work; the standing list
   in `docs/04_BUSINESS_RULES.md` section 10 remains open.