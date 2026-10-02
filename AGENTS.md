# Workforce CRM — Global Agent Instructions

## 1. Project Mission

Build a production-ready, mobile-first Workforce CRM / Employee Operations Management web application for a small business.

Initial users:
- 1 Admin
- Approximately 20 Employees

The product is a modular monolith, not a microservice system.

Primary goals:
- Reliable employee attendance and work-hour tracking
- Task assignment and approval
- Order broadcasting, claiming, packing and delivery tracking
- Leave management
- Employee ledger / salary / advances
- Complaint management
- Reporting and exports
- Configurable business rules
- Strong auditability and role-based access control

---

## 2. Source-of-Truth Hierarchy

When documents disagree, use this precedence:

1. `docs/00_PRODUCT_SCOPE.md`
2. `docs/04_BUSINESS_RULES.md`
3. `docs/05_PERMISSIONS.md`
4. `docs/06_WORKFLOWS.md`
5. `docs/01_ARCHITECTURE.md`
6. `docs/02_DATABASE.md`
7. `docs/03_API_CONTRACT.md`
8. `docs/07_UI_SPEC.md`
9. `docs/08_REPORT_SPEC.md`
10. `docs/09_TEST_PLAN.md`
11. Agent-specific instructions

If an implementation detail conflicts with a higher-priority product/business requirement, stop and report the conflict before silently changing behavior.

---

## 3. Non-Negotiable Engineering Rules

### No hidden hard-coding

Business rules that may change must not be hard-coded.

Examples:
- shop coordinates
- geofence radius
- GPS accuracy threshold
- QR validity duration
- daily required hours
- full-day / half-day thresholds
- break rules
- late/early thresholds
- overtime rules
- leave policies
- salary calculation settings
- advance deduction rules
- order claim timeout
- order reassignment rules

These belong in a database-backed settings/business-rules layer.

Technical constants are allowed when they are genuinely technical and not business policy.

### Backend is authoritative

Never trust the frontend for:
- permissions
- attendance validity
- work-hour totals
- salary calculations
- order ownership
- leave approval
- task approval
- financial values

The backend must validate and calculate authoritative state.

### Authorization is server-side

Frontend route guards are UX only.

Every protected backend operation must enforce authorization.

Never rely on hidden buttons to protect functionality.

### Preserve auditability

Important changes must be traceable:
- actor
- action
- target/entity
- previous state where appropriate
- new state where appropriate
- timestamp
- reason where required

Do not silently mutate historical financial or attendance records.

### Do not over-engineer

For approximately 20 employees:
- use a modular monolith
- use PostgreSQL
- use REST APIs
- avoid microservices
- avoid distributed systems unless a concrete requirement appears

Design clean module boundaries so future scaling remains possible.

---

## 4. Agent Ownership

### Agent 1 — Architect / Tech Lead
Owns:
- product clarification
- architecture
- database design
- API contracts
- business rules
- permissions
- workflows
- UI specification
- report specification
- test strategy

Agent 1 does NOT implement the full application.

### Agent 2 — Backend Engineer
Owns:
- FastAPI backend
- database models/migrations
- authentication
- authorization
- business logic
- APIs
- storage integration
- notifications abstraction
- backend tests

### Agent 3 — Frontend Engineer
Owns:
- responsive web UI
- PWA behavior
- admin dashboard
- employee mobile-first experience
- forms
- API integration
- client-side validation
- frontend tests

### Agent 4 — Domain / Workforce Specialist
Owns:
- business correctness review
- attendance rules
- work-hour calculation
- task lifecycle
- order lifecycle
- leave rules
- ledger/payroll logic
- complaints
- reports
- domain edge cases

Agent 4 reviews and proposes/fixes domain issues. It must not casually redesign architecture.

### Agent 5 — QA / Security / Integration
Owns:
- end-to-end testing
- authorization/security testing
- concurrency testing
- regression testing
- report validation
- production-readiness review
- final defect verification

---

## 5. File Ownership Rule

An agent must not modify another agent's implementation area unless:
- the change is required to complete its own contract, or
- the current contract is demonstrably incorrect and the change is documented.

Before changing a cross-module contract:
1. identify the issue,
2. update the relevant `/docs` document,
3. update affected implementation,
4. run affected tests.

Do not perform broad unrelated refactors while implementing a feature.

---

## 6. Change Protocol

When requirements or architecture need to change:

1. Do not silently invent a requirement.
2. Identify the ambiguity/conflict.
3. Record it in the appropriate document.
4. Make the smallest safe change.
5. Update dependent contracts.
6. Run regression tests.

If a decision genuinely requires client confirmation, mark it as `CLIENT_DECISION_REQUIRED`.

---

## 7. Definition of Done

A module is not complete merely because code exists.

A module is complete when:
- implementation exists
- API behavior is documented
- authorization is enforced
- validation exists
- important edge cases are handled
- tests exist and pass
- errors are handled
- audit requirements are implemented where applicable
- UI is integrated where applicable
- no known critical defect remains

---

## 8. Security Baseline

Always consider:
- authentication
- authorization/RBAC
- IDOR
- privilege escalation
- input validation
- file upload security
- SQL injection protection
- XSS
- CSRF strategy where applicable
- rate limiting
- secure cookies/tokens
- secret management
- audit logging
- least privilege
- sensitive data exposure

Never log passwords, tokens, secrets, or unnecessary sensitive data.

---

## 9. Attendance Principle

Do NOT continuously track employee GPS.

Attendance verification occurs at configured attendance events such as:
- check-in
- check-out
- break start/end if configured

Initial verification model:
- GPS/geofence
- dynamic shop QR

An employee may legitimately leave the shop for field work/delivery after valid attendance.

Do not automatically mark an employee absent simply because their phone is no longer near the shop.

---

## 10. Order Claiming Principle

Order claiming is a concurrency-sensitive operation.

If multiple employees attempt to claim the same order:
- exactly one valid claim may succeed
- the backend/database must enforce this
- frontend checks alone are insufficient

---

## 11. Time and Money

Use timezone-aware timestamps.

Business timezone must be configurable at the organization/business level.

Do not use floating-point arithmetic for money.

Do not derive historical payroll from today's rules without preserving the rule/version/snapshot required for auditability.

---

## 12. Agent Completion Report

Every coding/review agent must finish with:
- what was changed
- files changed
- tests run
- test result
- migrations if any
- API changes
- documentation changes
- known limitations
- unresolved `CLIENT_DECISION_REQUIRED` items
