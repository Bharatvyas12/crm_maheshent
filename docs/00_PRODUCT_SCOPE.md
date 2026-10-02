# Workforce CRM — Product Scope

## 1. Product Overview

A web-based Workforce CRM / Employee Operations Management System for a small business with one Admin and approximately twenty Employees.

The system combines:
- employee operations
- attendance
- task management
- order operations
- leave management
- employee ledger/payroll records
- complaints
- reporting
- notifications
- configurable business rules

The employee experience must be mobile-first and PWA-capable because employees are expected to use phones during shop-floor and field operations.

The admin experience should be optimized for desktop/tablet while remaining responsive.

A native mobile application is not required for MVP.

---

## 2. Initial Roles

### ADMIN
Can:
- manage employees
- configure business rules
- monitor attendance
- assign/review tasks
- create/broadcast/manage orders
- approve/reject leave
- manage employee ledger/advances/salary records
- manage complaints
- generate reports
- inspect audit history
- manage notifications/settings

### EMPLOYEE
Can:
- check in/out subject to configured verification
- manage configured breaks
- view/complete assigned tasks
- submit task evidence
- view and claim eligible orders
- update order status according to permissions
- submit delivery/order proof
- apply for leave
- view own leave balance/history
- view own ledger/pay information allowed by policy
- submit complaints
- receive notifications
- manage own profile fields permitted by policy

---

## 3. Core Modules

1. Authentication
2. User/Employee Management
3. Role & Permission Management
4. Admin Dashboard
5. Employee Dashboard
6. Attendance
7. Break Management
8. Location Verification
9. Dynamic QR Attendance Verification
10. Task Management
11. Task Submission & Approval
12. Order Management
13. Order Broadcasting
14. Order Claiming
15. Order Fulfillment
16. Leave Management
17. Employee Ledger
18. Salary/Payroll Calculation
19. Employee Advances
20. Complaints
21. Notifications
22. Reports
23. Attachments/File Storage
24. Audit Logs
25. Business Settings
26. Search/Filtering
27. Export

---

## 4. Attendance Scope

The employee must be physically present at the configured shop/location for normal check-in.

The initial verification model is layered:

1. GPS/geofence verification
2. Dynamic shop QR verification

The system must not rely on GPS alone.

The system must not continuously track GPS throughout the workday.

Attendance events may include:
- check-in
- check-out
- break start
- break end
- attendance correction

The system records verification evidence such as:
- timestamp
- latitude/longitude where collected
- location accuracy
- verification method
- verification result
- relevant anomaly/rejection reason

The exact radius, accuracy threshold and QR validity are configurable.

Employees may leave the shop for legitimate work such as delivery/order fulfillment. Such field activity should be represented through operational records rather than continuous surveillance.

---

## 5. Work-Hour Scope

The business currently expects a configurable rule where approximately ten hours of active work may count as one full working day.

This MUST NOT be hard-coded.

The system must support configurable:
- required daily hours
- full-day threshold
- half-day threshold
- overtime threshold
- break policy
- late threshold
- early checkout threshold

The system should calculate active work duration from attendance/work sessions and configured break rules.

It should support:
- full day
- half day
- partial day
- overtime
- late arrival
- early checkout
- missing checkout
- attendance correction

Final payroll semantics require client confirmation.

---

## 6. Task Management

Admin assigns tasks to employees.

Task data may include:
- title
- description
- priority
- assigned employee
- due date/time
- attachments
- status
- comments

Employee workflow:

Assigned
→ Start
→ Complete
→ Submit for Review

Evidence can include:
- photo
- description
- file if enabled

Admin workflow:

Submitted
→ Approve

or

Submitted
→ Reject / Request Resubmission
→ Employee resubmits

Task history must be preserved.

---

## 7. Order Management

When an order arrives, Admin can create/register it and broadcast it to eligible employees.

Employees see available broadcast orders.

An employee can claim an order.

Claiming must be atomic so only one employee obtains ownership.

Initial lifecycle:

BROADCASTED
→ CLAIMED
→ PACKING
→ PACKED
→ READY_FOR_DELIVERY
→ OUT_FOR_DELIVERY
→ DELIVERED

Additional lifecycle states:
- CANCELLED
- FAILED
- REASSIGNED

Every meaningful transition should have:
- timestamp
- actor
- previous status
- new status

Delivery/order proof can be configurable and may include:
- photo
- note
- timestamp
- customer confirmation
- optional location evidence

---

## 8. Leave Management

Employee can apply for leave.

Application includes:
- leave type
- start date
- end date
- reason
- attachment where required

Admin can:
- approve
- reject
- request modification

System maintains:
- available balance
- used balance
- pending requests
- approved requests
- rejected requests
- history

Leave policy is configurable.

---

## 9. Employee Ledger / Payroll Scope

The employee ledger is an HR/payroll-style record, not a complete accounting ERP.

Potential records:
- salary
- advances
- deductions
- attendance-derived payable days/hours
- overtime
- leave-related deductions where configured
- payments
- manual adjustments

Financial adjustments require:
- amount
- reason
- actor
- timestamp
- audit trail

Salary calculation must be configurable.

Historical salary/payroll calculations must remain auditable.

---

## 10. Complaint Management

Employees can create complaints.

Admin can create employee-related operational/disciplinary issues where permitted.

Complaint fields:
- category
- title
- description
- priority
- evidence
- status
- comments
- resolution
- timestamps

Initial statuses may include:
- OPEN
- IN_REVIEW
- ACTION_REQUIRED
- RESOLVED
- CLOSED
- REJECTED

---

## 11. Reporting

Admin can generate employee and operational reports for a selected date range.

Potential report sections:
- attendance
- work hours
- breaks
- overtime
- tasks
- task completion
- orders
- order status
- leaves
- advances
- salary/ledger
- complaints where policy allows

Exports:
- CSV
- XLSX and/or PDF if confirmed as required

Report scope and sensitive fields must respect permissions.

---

## 12. Notifications

Initial notification channels:
- in-app
- browser/PWA notifications where supported

Events:
- task assigned
- task approved/rejected/resubmission
- order broadcast
- order claimed
- order status changed
- leave approved/rejected
- complaint updated
- configured ledger/salary notifications

Architecture should permit future email/SMS/WhatsApp integrations without coupling core business logic to one provider.

---

## 13. Auditability

Important actions require audit records.

Examples:
- authentication/security events
- employee changes
- settings changes
- attendance corrections
- task review decisions
- order reassignment
- leave decisions
- salary/advance changes
- complaint resolution
- permission changes

---

## 14. Non-Goals for MVP

Do not build unless explicitly requested:
- full accounting ERP
- inventory management
- customer CRM pipeline
- complex commission engine
- multi-company accounting
- native Android/iOS applications
- microservice architecture
- continuous employee GPS surveillance
- advanced AI features

The architecture should not prevent these in future, but MVP should remain focused.

---

## 15. Important Client Decisions Required

The following must be finalized before production:

1. Exact shop location and permitted geofence radius
2. GPS accuracy tolerance
3. Dynamic QR rotation/validity duration
4. Whether both GPS and QR are always required or one can act as fallback
5. Check-out verification rule
6. Break types and whether lunch is the only tracked break
7. Full-day/half-day/partial-day formula
8. Overtime calculation
9. Late/early policy
10. Missing checkout handling
11. Field-duty handling
12. Leave types and yearly/monthly balances
13. Salary formula
14. Advance deduction policy
15. Payroll lock/finalization process
16. Order claim timeout
17. Who can reassign orders
18. Order cancellation rules
19. Required proof of delivery
20. Complaint privacy/visibility rules
21. Required report formats
22. Notification channels
23. Data retention policy
24. Business timezone
25. Employee access to salary/ledger details
