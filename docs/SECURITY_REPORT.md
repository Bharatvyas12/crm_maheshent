# Workforce CRM — Security & Vulnerability Audit Report (Agent 5)

**Security Lead:** Agent 5 — Security & Integration Engineer  
**Report Date:** October 2, 2026  
**Scope:** Server-Side Authorization, RBAC, Authentication, Input Validation, CSRF, IDOR, Concurrency, and Secret Management.

---

## 1. Security Architecture & Controls

### 1.1 Authentication & Session Security
- **Session Tokens:** 256-bit opaque tokens generated via `secrets.token_urlsafe()`. Tokens are stored as SHA-256 hashes in the database (`sessions` table). Raw tokens are never logged or stored.
- **Session Cookies:** `HttpOnly`, `SameSite=Lax`, `Path=/`.
- **Password Hashing:** Argon2id (`time_cost=3`, `memory_cost=65536`, `parallelism=4`).
- **Password Gate:** Initial accounts and password resets set `must_change_password = true`. Non-password-change endpoints return `403 PERMISSION_DENIED` with `rule_code: "PASSWORD_CHANGE_REQUIRED"` until updated.

### 1.2 Server-Side Authorization (RBAC)
- **Non-Negotiable Server-Side Enforcement:** Every endpoint resolves context via `Ctx = Depends(get_ctx)` and enforces catalog permissions via `require("permission.code")` or `require_authenticated`. No client-side hidden UI buttons or route guards act as authorization controls.
- **Permission Matrix Audit:** Evaluated 96 permissions. Admin accounts hold all 96; standard employees hold exactly the 28 designated self-service permissions (`EMPLOYEE_PERMISSION_CODES`).
- **Self-Service Boundaries:** Employee endpoints (`/api/v1/attendance/me`, `/api/v1/ledger/me`, etc.) filter explicitly by `ctx.actor.employee_id`. Prohibits accessing or modifying another employee's records.

### 1.3 CSRF Protection
- **Double-Submit Scheme:** Unsafe HTTP methods (`POST`, `PUT`, `PATCH`, `DELETE`) require `X-CSRF-Token` header.
- **Hash Validation:** Backend verifies `sha256_hex(X-CSRF-Token)` matches `csrf_token_hash` bound to the active session in constant time (`hmac.compare_digest`).

### 1.4 Financial Integrity & Auditability
- **No Direct Mutation:** Financial ledger entries (`employee_ledger_entries`) and attendance audit records cannot be directly deleted via REST API. Adjustments require explicit reversal entries (`reverses_entry_id`).
- **Audit Logging:** Sensitive actions (logins, password changes, salary computations, role updates) write structured records to `audit_logs` capturing `actor_user_id`, `ip`, `user_agent`, `before`, and `after` snapshots.

---

## 2. Vulnerability Assessment Matrix

| Vulnerability Type | Vector Tested | Result / Mitigation | Status |
|---|---|---|---|
| **Privilege Escalation** | Employee calling admin endpoints (`/api/v1/employees`, `/api/v1/payroll/runs`) | Backend returns `403 PERMISSION_DENIED` | ✅ SECURE |
| **IDOR** | Employee attempting to view another employee's ledger/attendance by ID | Endpoint enforces `ctx.actor.employee_id` filter | ✅ SECURE |
| **CSRF** | Replaying unsafe HTTP requests without matching `X-CSRF-Token` header | Rejected with `403 CSRF_INVALID` | ✅ SECURE |
| **SQL Injection** | Parameterized SQL queries via SQLAlchemy ORM & text constructs | All database calls parameterized | ✅ SECURE |
| **Double-Claim Race** | Concurrent order claim attempts | Solved via DB conditional UPDATE & constraint | ✅ SECURE |
| **Password Theft** | Inspecting database dumps | Argon2id salted hashes | ✅ SECURE |
| **Session Fixation** | Login & password reset | Old session revoked; new session token generated | ✅ SECURE |

---

## 3. Security Checklist Verification

- [x] Server-side authorization enforced on every API route
- [x] Passwords hashed with Argon2id
- [x] Opaque 256-bit session tokens stored as SHA-256 hex hashes
- [x] CSRF double-submit token enforced on all unsafe HTTP methods
- [x] Rate limiting configured on auth endpoints
- [x] Sensitive financial records append-only with immutable reversals
- [x] CORS allowed origins configured via business settings / env
- [x] Security headers attached to all HTTP responses (`X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`, `Referrer-Policy`)
