# Agent 1 — Principal Architect / Product Architect

Read:
- `/AGENTS.md`
- `/docs/00_PRODUCT_SCOPE.md`

Your job is to turn the product scope into an implementation-ready specification for the other agents.

DO NOT build the full application yet.

## Deliverables

Create/update:

- `docs/01_ARCHITECTURE.md`
- `docs/02_DATABASE.md`
- `docs/03_API_CONTRACT.md`
- `docs/04_BUSINESS_RULES.md`
- `docs/05_PERMISSIONS.md`
- `docs/06_WORKFLOWS.md`
- `docs/07_UI_SPEC.md`
- `docs/08_REPORT_SPEC.md`
- `docs/09_TEST_PLAN.md`

## Architecture

Use a modular monolith.

Recommended:
- Frontend: Next.js/React + TypeScript
- Backend: FastAPI + Python
- Database: PostgreSQL
- ORM: SQLAlchemy
- Migrations: Alembic
- Object storage: S3-compatible
- Optional Redis only where justified

Do not introduce microservices for this MVP.

## Required design work

Specify:
- module boundaries
- dependency boundaries
- authentication strategy
- authorization/RBAC
- API conventions
- error format
- validation
- pagination/filtering/sorting
- file upload strategy
- notification abstraction
- audit logging
- time/timezone handling
- money/decimal handling
- transaction boundaries
- concurrency strategy

## Database

Design a normalized relational model.

Evaluate entities including:
- users
- roles
- permissions
- role_permissions
- business_settings
- attendance_records
- attendance_sessions
- break_sessions
- attendance_verifications
- tasks
- task_assignments
- task_submissions
- task_comments
- task_attachments
- orders
- order_claims
- order_status_history
- order_attachments
- leaves
- leave_types
- leave_balances
- employee_ledger
- salary_records
- advances
- complaints
- complaint_comments
- notifications
- audit_logs
- files

Do not create tables merely because they were listed. Choose a coherent normalized model and explain relationships.

## Business Rules

Explicitly specify:
- attendance verification
- GPS/geofence
- GPS accuracy
- dynamic QR
- break calculation
- work-hour calculation
- full/half/partial day
- overtime
- late/early
- missing checkout
- attendance correction
- task lifecycle
- task approval
- order broadcast
- atomic order claim
- order lifecycle
- reassignment
- leave balance
- salary calculation
- advance handling
- complaint lifecycle
- report calculations

No business policy may be silently hard-coded.

## Security

Specify:
- authentication
- RBAC
- object-level authorization
- file security
- rate limiting
- audit requirements
- secret handling
- session/token strategy
- sensitive-data boundaries

## Edge Cases

Explicitly define handling for:
- duplicate check-in
- missing checkout
- offline/network failure
- inaccurate GPS
- expired/replayed QR
- field work
- simultaneous order claims
- order abandonment
- reassignment
- task resubmission
- overlapping leave
- salary-rule changes
- post-payroll attendance correction
- employee deactivation
- duplicate requests
- timezone/date boundaries
- month-end payroll

## Ambiguities

Do not invent uncertain client policy.

Mark unresolved items as:
`CLIENT_DECISION_REQUIRED`

## Final verification

Before finishing:
- check that all modules in Product Scope are covered
- check that permissions match workflows
- check API contracts support workflows
- check database supports API requirements
- check reports can be generated from the schema
- check every configurable business rule has a storage/configuration strategy

Do not implement the full application.
End with a concise architecture handoff summary for Agents 2–5.
