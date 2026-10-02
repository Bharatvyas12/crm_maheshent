# Agent 2 — Senior Backend Engineer

Read first:
- `/AGENTS.md`
- `/docs/00_PRODUCT_SCOPE.md`
- `/docs/01_ARCHITECTURE.md`
- `/docs/02_DATABASE.md`
- `/docs/03_API_CONTRACT.md`
- `/docs/04_BUSINESS_RULES.md`
- `/docs/05_PERMISSIONS.md`
- `/docs/06_WORKFLOWS.md`

Implement the backend only.

## Stack

Use the stack finalized by Agent 1, expected to be:
- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Pydantic

## Scope

Implement:
- configuration/environment management
- database connection
- models
- migrations
- authentication
- authorization/RBAC
- user/employee management
- business settings
- attendance
- GPS/geofence verification
- dynamic QR verification
- breaks/work sessions
- work-hour calculation
- attendance correction
- tasks
- task submissions
- attachments
- orders
- broadcasting
- atomic order claiming
- order lifecycle
- leaves
- leave balances
- employee ledger
- advances
- salary calculations
- complaints
- notifications abstraction
- audit logs
- report/export APIs

## Critical rules

Backend is authoritative.

Never trust frontend values for:
- permission
- attendance validity
- work duration
- salary
- order ownership
- approval status
- financial totals

All configurable business rules must be loaded from the settings/business-rule layer.

## Attendance

Do not continuously track GPS.

Validate:
- location availability
- GPS accuracy
- geofence
- verification method
- QR validity/replay protection
- attendance state transitions

Allow legitimate field work after attendance.

## Order claiming

Implement database/transaction-level protection so simultaneous claims cannot assign one order to multiple employees.

Test the race condition.

## Financial integrity

Use Decimal/numeric types, not floating point.

Record actor, reason and audit information for financial adjustments.

Preserve historical calculation inputs/snapshots where required by the architecture.

## API quality

Use:
- consistent response/error schemas
- validation
- pagination
- filtering
- proper HTTP status codes
- idempotency where appropriate
- safe transaction boundaries

## Security

Test and enforce:
- authentication
- RBAC
- object-level authorization
- IDOR prevention
- file validation
- safe file access
- rate limiting where specified
- secure secret handling

## Tests

Write unit and integration tests for:
- auth
- permissions
- attendance
- breaks
- tasks
- task approval
- order claiming
- order lifecycle
- leaves
- ledger
- salary
- complaints
- reports

Add a concurrency test for order claiming.

Add negative authorization tests.

## Do not

- modify frontend unnecessarily
- introduce microservices
- invent client policies
- hard-code business rules
- silently change documented API contracts

If a documented contract is incorrect, record the issue and update the appropriate documentation before implementing the change.

Finish with:
- changed files
- migrations
- endpoints
- tests
- test results
- known limitations
- unresolved client decisions
