# Agent 3 — Senior Frontend Engineer

Read first:
- `/AGENTS.md`
- `/docs/00_PRODUCT_SCOPE.md`
- `/docs/01_ARCHITECTURE.md`
- `/docs/03_API_CONTRACT.md`
- `/docs/05_PERMISSIONS.md`
- `/docs/06_WORKFLOWS.md`
- `/docs/07_UI_SPEC.md`

Build the frontend only.

## Stack

Use the frontend stack finalized by Agent 1, expected to be:
- Next.js/React
- TypeScript
- responsive UI
- PWA capability

## Two experiences

### Admin
Desktop/tablet-first responsive dashboard.

### Employee
Mobile-first, app-like experience.

Prefer one coherent frontend application with role-based navigation unless architecture explicitly requires separation.

## Admin areas

- Dashboard
- Employees
- Attendance
- Tasks
- Orders
- Leaves
- Complaints
- Employee Ledger
- Salary/Advances
- Reports
- Notifications
- Settings
- Audit Logs

## Employee areas

- Dashboard
- Attendance
- Break
- Tasks
- Orders
- Leaves
- Complaints
- Ledger
- Notifications
- Profile

## UX requirements

Critical employee actions must be easy to reach:
- Check In
- Start Break
- End Break
- Check Out
- View Tasks
- Submit Task
- View Orders
- Claim Order
- Update Order
- Apply Leave
- Submit Complaint

Every mutation needs:
- loading state
- success state
- error state
- duplicate-click protection

Network failures must be understandable.

## Attendance UI

Use browser location only when required.

Check-in:
1. request location permission
2. obtain location
3. show verification progress
4. support dynamic QR scan
5. submit to backend
6. display authoritative backend result

The frontend must never decide whether the employee is allowed to check in.

Do not implement continuous GPS tracking.

## Order UI

Handle:
- available order
- claiming
- claim conflict
- lifecycle status
- proof upload
- delivery confirmation

If another employee wins the claim:
- show clear conflict state
- refresh order state

## Settings

Do not hard-code configurable business values into UI.

Build settings screens from the API contract.

## Accessibility/responsiveness

Test:
- mobile
- tablet
- desktop
- touch interaction
- keyboard navigation where applicable
- readable validation/error messages

## Quality

Do not duplicate business calculations in frontend.

Backend remains authoritative for:
- attendance
- salary
- work hours
- order ownership
- permissions

Write meaningful frontend tests for critical flows.

Finish with:
- routes
- components
- API integration
- state/data handling
- validation
- tests
- known issues
- unresolved client decisions
