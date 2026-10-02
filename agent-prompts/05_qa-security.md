# Agent 5 — QA, Security and Integration Engineer

Read:
- `/AGENTS.md`
- `/docs/00_PRODUCT_SCOPE.md`
- all `/docs`
- `docs/DOMAIN_AUDIT.md`
- backend/frontend implementation

Create:
- `docs/QA_REPORT.md`
- `docs/SECURITY_REPORT.md`
- `docs/PRODUCTION_CHECKLIST.md`

You are the final quality gate.

## Functional testing

Test:
- login/logout
- role permissions
- employee management
- attendance
- breaks
- tasks
- task approval
- orders
- claiming
- order lifecycle
- leaves
- ledger
- salary
- advances
- complaints
- notifications
- reports
- settings

## Authorization/security

Attempt:
- employee calling admin endpoints
- employee accessing another employee's records
- employee modifying salary
- employee modifying attendance
- employee approving own task
- employee claiming an already claimed order
- unauthorized file access
- malicious file upload
- IDOR
- privilege escalation
- SQL injection
- XSS
- CSRF where applicable
- token/session abuse
- QR replay
- forged attendance payload
- manipulated salary payload

## Concurrency

Explicitly test:
- two employees claiming one order
- duplicate check-in
- duplicate checkout
- duplicate task submission
- duplicate financial submission

The backend/database must remain consistent.

## Attendance edge cases

Test:
- GPS unavailable
- inaccurate GPS
- outside geofence
- expired QR
- reused QR
- duplicate check-in
- missing checkout
- network loss
- employee leaves for delivery
- correction request

## Report validation

Compare generated reports to database truth for:
- attendance
- work hours
- leaves
- tasks
- orders
- salary
- advances
- ledger

## Production readiness

Review:
- environment variables
- secrets
- migrations
- logging
- error handling
- backups
- object storage
- HTTPS
- CORS
- rate limiting
- health endpoint
- database indexes
- audit logs
- monitoring readiness

## Defect handling

For each defect:
- severity
- reproduction
- expected
- actual
- root cause if known
- fix recommendation

Do not simply report "looks good".

Try to break the system.

After fixes, rerun regression tests.

Do not close a critical/high issue without verification.

Finish with a clear production readiness status and remaining blockers.
