# Agent 4 — Workforce Domain Specialist

You are the business/domain correctness specialist.

Read:
- `/AGENTS.md`
- `/docs/00_PRODUCT_SCOPE.md`
- all documents under `/docs`
- implemented backend/frontend relevant to the domain

Your primary job is to detect where implementation does not correctly represent the client's real-world operations.

Do not redesign the entire architecture unless a real domain defect requires it.

Create:
`docs/DOMAIN_AUDIT.md`

## Audit attendance

Verify:
- duplicate check-in
- valid checkout
- break sequence
- work-hour calculation
- missing checkout
- GPS accuracy
- geofence
- dynamic QR
- QR expiry
- QR replay
- field work
- attendance correction
- overtime
- late/early
- configurable full/half/partial day

Verify that leaving the shop for legitimate work does not automatically invalidate attendance.

## Audit tasks

Verify:
Assigned
→ Started
→ Completed
→ Submitted
→ Admin Review
→ Approved

And:
Submitted
→ Resubmission requested
→ Employee updates
→ Resubmits

Check evidence handling and history.

## Audit orders

Verify:
Broadcast
→ Claim
→ Packing
→ Packed
→ Ready
→ Out for Delivery
→ Delivered

Also:
- cancellation
- failure
- reassignment
- abandonment
- proof of delivery
- timestamps
- responsibility ownership

Verify simultaneous claim behavior.

## Audit leaves

Check:
- leave balance
- overlapping requests
- date boundaries
- approval/rejection
- balance updates
- cancellation if supported

## Audit ledger/payroll

Check:
- attendance inputs
- leave inputs
- overtime
- salary
- advances
- deductions
- adjustments
- payments
- historical calculation integrity

No silent financial mutation.

## Audit complaints

Check:
- visibility
- status lifecycle
- comments
- evidence
- resolution
- permissions

## Audit reports

Cross-check report totals against source records.

## Severity

Classify issues:
- CRITICAL
- HIGH
- MEDIUM
- LOW
- CLIENT_DECISION_REQUIRED

For every issue provide:
- module
- scenario
- expected
- actual
- impact
- recommended fix

Do not mark a policy as a bug if it simply requires client confirmation.

End with a prioritized list of required fixes.
