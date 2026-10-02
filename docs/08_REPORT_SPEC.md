# 08 - Report Specification

| Field | Value |
| --- | --- |
| Document owner | Agent 1 - Architect / Tech Lead |
| Status | Baseline (implementation-ready) |
| Version | 1.0 |
| Source-of-truth rank | 9 |
| Applies to | Agent 2 (implements), Agent 3 (renders), Agent 4/5 (validates) |

This document specifies every report: purpose, permission, filters, columns, calculations,
totals, sorting, export behavior and the reconciliation rules that prove a report matches the
database.

Report calculations must agree with `docs/04_BUSINESS_RULES.md` section 4.13; report data must be
derivable from the views in `docs/02_DATABASE.md` section 20.

---

## 1. General Rules

| Rule | Detail |
| --- | --- |
| Read-only | Reports never mutate business state. Every report runs in a read-only transaction |
| Permissions | Each report declares a permission (section 2). Row scoping follows
`docs/05_PERMISSIONS.md` section 5. A user with no report permission gets `403` |
| Range | Every range report requires `from` and `to`; the span may not exceed
`reports.max_range_days`; `from <= to` is enforced |
| Range semantics | Date ranges are inclusive of `from` and `to` as business dates; the underlying query
uses half-open instants (`>= from 00:00`, `< to+1 00:00`) in the business timezone |
| Grouping timezone | `reports.grouping_timezone` (`BUSINESS` default, or `UTC`) governs day/week/month
grouping only; instants are always returned in UTC |
| Money | Decimal arithmetic only; money is rendered as a decimal string with 2 decimals. Report
totals use SQL `SUM(numeric)`, never floating point |
| Durations | Seconds in the data model; reports render hours with 2 decimals and also expose the raw
seconds for machine consumption |
| Determinism | Every report defines a stable default sort and a tie-breaker, so identical inputs
produce identical row order (required for export diffing and tests) |
| Pagination | Interactive viewing uses `page`/`page_size` (default from
`reports.default_page_size`); exports stream all rows without loading them into memory |
| Sensitive fields | Excluded by default; inclusion requires the specific sensitive permission plus
`reports.include_sensitive_fields` where applicable |
| Employee self-scope | A user holding a report permission without an `all` scope equivalent is
automatically filtered to their own rows |
| Empty results | Return the schema with zero rows and zero totals; never omit the columns, so
consumers do not break |
| Reconciliation | Every report lists its reconciliation rule (section 6); Agent 5 verifies each
against the source tables |

---

## 2. Report Catalog

| ID | Report | Permission | Source views | Primary grouping |
| --- | --- | --- | --- | --- |
| R-01 | Attendance register | `report.attendance` | `v_attendance_daily` | employee x date |
| R-02 | Attendance summary | `report.attendance` | `v_attendance_daily` | employee |
| R-03 | Work hours | `report.attendance` | `v_attendance_daily` | employee |
| R-04 | Breaks | `report.attendance` | `v_break_summary` | employee x break type |
| R-05 | Overtime | `report.attendance` | `v_attendance_daily` | employee |
| R-06 | Punctuality (late/early) | `report.attendance` | `v_attendance_daily` | employee |
| R-07 | Task status | `report.tasks` | `v_task_assignment_current` | employee |
| R-08 | Task completion and review turnaround | `report.tasks` | `v_task_assignment_current` | employee / period |
| R-09 | Order activity | `report.orders` | `v_order_current` | status / employee |
| R-10 | Order stage timings | `report.orders` | `v_order_transition_times` | order / stage |
| R-11 | Leave requests | `report.leaves` | `v_leave_request_detail` | employee x type |
| R-12 | Leave balances | `report.leaves` | `v_leave_balance_current` | employee x type |
| R-13 | Advances | `report.ledger` | `v_advance_outstanding` | employee |
| R-14 | Ledger | `report.ledger` | `v_ledger_entry_detail`, `v_ledger_balance` | employee x entry type |
| R-15 | Salary / payroll | `report.salary` | `v_salary_record_detail` | employee |
| R-16 | Complaints | `report.complaints` | `v_complaint_detail` | status / category |
| R-17 | Dashboard summary | authenticated | aggregates over the above | none (KPI cards) |
| R-18 | Audit log export | `audit.export` | `audit_logs` | time |

---

## 3. Report Definitions

### R-01 Attendance register

- **Purpose:** the authoritative day-by-day attendance record for a date range, used for
  supervision, dispute resolution and payroll auditing.
- **Filters:** `from`, `to` (required); `employee_id`, `department`, `status`,
  `day_classification`, `include_incomplete` (default true), `sort`.
- **Columns:** employee code, employee name, department, business date, status,
  day classification, first check-in, last check-out, worked hours (and seconds), break hours (paid
  and unpaid), overtime hours, late minutes, early-checkout minutes, `is_corrected`, anomaly flag,
  leave type (when on leave).
- **Default sort:** business date descending, then employee code ascending.
- **Totals:** row count; counts by status and classification; sum of worked, break, unpaid-break and
  overtime seconds.
- **Notes:** `INCOMPLETE` days are included and marked; they are never silently treated as absent or
  present. Corrected rows show the flag so a reader knows the punch was superseded.
- **Export:** CSV, XLSX.
- **Reconciliation:** each row must equal its `attendance_records` row, and the worked seconds must
  equal a fresh recomputation (BR-4.3).

### R-02 Attendance summary

- **Purpose:** per-employee attendance outcome for a range, used for monthly review and payroll
  sanity checks.
- **Filters:** `from`, `to` (required); `employee_id`, `department`, `employee_status`.
- **Columns:** employee code, name, department, present days (FULL_DAY), half days, partial days,
  absent days, leave days (paid/unpaid), holiday days, weekly-off days, incomplete days,
  not-marked days, total days in range, attendance percentage.
- **Derived:** `attendance_percentage = (present_days + half_days * 0.5 + paid_leave_days +
  holiday_days + weekly_off_days) / payable_days_in_range * 100`, where the denominator follows
  `payroll.working_days_basis`. The exact formula is computed server-side and returned, never
  recomputed in the client.
- **Default sort:** employee code ascending.
- **Totals:** sum of each day count; overall attendance percentage.
- **Reconciliation:** day counts must sum to the number of business dates in the range for each
  employee (no double counting, no gaps).

### R-03 Work hours

- **Purpose:** worked-time totals for payroll verification and productivity review.
- **Filters:** `from`, `to` (required); `employee_id`, `department`, `group_by`
  (`employee` default, `date`, `week`, `month`).
- **Columns:** employee, period, worked hours (and seconds), break hours, unpaid break hours, days
  worked, average hours per worked day, required hours (from `attendance.required_daily_hours` x
  applicable days), variance.
- **Default sort:** employee code, then period ascending.
- **Totals:** sum of worked, break and unpaid-break seconds; average hours per worked day.
- **Notes:** days with `INCOMPLETE` status are reported separately as "hours pending resolution" and
  are never mixed into the confirmed total.
- **Reconciliation:** sum of per-day worked seconds must equal the sum of session durations minus
  unpaid breaks across the range.

### R-04 Breaks

- **Purpose:** break usage and policy compliance.
- **Filters:** `from`, `to` (required); `employee_id`, `break_type_id`, `group_by`
  (`employee` default, `break_type`, `date`).
- **Columns:** employee, break type, paid flag, break count, total break hours, average break
  minutes, longest break, days exceeding `attendance.break_max_minutes_per_day`.
- **Default sort:** employee code, then break type.
- **Totals:** break counts and total break seconds split by paid/unpaid.
- **Reconciliation:** break counts and durations must equal `break_sessions` rows in range.

### R-05 Overtime

- **Purpose:** overtime accrual per employee for the period, used before payroll.
- **Filters:** `from`, `to` (required); `employee_id`, `department`.
- **Columns:** employee, overtime days, total overtime hours (and seconds), average overtime per
  overtime day, maximum single-day overtime, cap-affected days (days where the cap was applied).
- **Default sort:** total overtime seconds descending, then employee code ascending.
- **Totals:** total overtime seconds; payable overtime estimate using the same hourly-equivalent
  formula as payroll (BR-4.9 step 6) and `payroll.overtime_rate_multiplier`.
- **Notes:** the payable estimate is labelled as an estimate until the payroll run is computed;
  after finalization the salary report is authoritative.
- **Reconciliation:** overtime seconds must equal the sum of `attendance_records.overtime_seconds`
  for the range.

### R-06 Punctuality (late and early checkout)

- **Purpose:** visibility into shift adherence, and the input to late deductions when enabled.
- **Filters:** `from`, `to` (required); `employee_id`, `department`, `min_minutes`.
- **Columns:** employee, late occurrences, total late minutes, average late minutes, worst late
  arrival, early-checkout occurrences, total early minutes, occurrences beyond the grace period.
- **Default sort:** total late minutes descending.
- **Totals:** occurrences and minutes; estimated deduction when `payroll.late_deduction_enabled`.
- **Notes:** only computed when `attendance.shift_tracking_enabled` is true; otherwise the report
  returns an explanatory empty state rather than zeros that look like perfect punctuality.

### R-07 Task status

- **Purpose:** workload and task-state distribution.
- **Filters:** `from`, `to` (by assignment date) or `due_from`/`due_to`; `employee_id`,
  `status`, `priority`, `task_id`.
- **Columns:** task title, assignee, priority, assignment status, due date, assigned date, started
  date, submitted date, reviewed date, attempt count, overdue flag, days overdue.
- **Default sort:** due date ascending (nulls last), then priority descending.
- **Totals:** counts by status (assigned, started, submitted, approved, rejected,
  resubmission-requested, cancelled) and overdue count.
- **Reconciliation:** counts must equal `task_assignments` rows in scope; a task with several
  assignees produces several rows (documented, so totals are per assignment, not per task).

### R-08 Task completion and review turnaround

- **Purpose:** measure throughput and reviewer responsiveness.
- **Filters:** `from`, `to` (by review or completion date); `employee_id`, `reviewer_id`.
- **Columns:** employee, assignments in range, approved, rejected, resubmission-requested,
  completion rate, average attempts per completed assignment, average time from assignment to
  submission, average review turnaround (submission to decision), average total cycle time.
- **Derived:** `completion_rate = approved / (assignments with a decision)`, `average_review_
  turnaround = mean(reviewed_at - submitted_at)` over decided submissions.
- **Default sort:** completion rate descending.
- **Reconciliation:** each metric recomputable from `task_assignments` and `task_submissions`
  timestamps.

### R-09 Order activity

- **Purpose:** order volume, ownership and outcomes.
- **Filters:** `from`, `to` (by creation or broadcast date); `status`, `assignee_employee_id`,
  `payment_mode`, `include_cancelled` (default true).
- **Columns:** order code, created date, broadcast date, current status, assignee, claim date,
  delivered/failed/cancelled date, order amount, payment mode, reassignment count, current age.
- **Default sort:** created date descending.
- **Totals:** order count, total order amount, average order amount, counts by status, delivered /
  failed / cancelled counts, reassignment count.
- **Reconciliation:** counts must equal `orders` rows in scope; each order appears once regardless
  of how many claims it had (history is available in R-10).

### R-10 Order stage timings

- **Purpose:** identify operational bottlenecks and SLA breaches.
- **Filters:** `from`, `to`; `employee_id` (assignee); `stage`
  (`CLAIM`,`PACK`,`READY`,`DISPATCH`,`DELIVERY`).
- **Columns:** order code, claim duration (broadcast to claim), packing duration (claim to packed),
  ready duration (packed to ready), dispatch duration (ready to out-for-delivery), delivery duration
  (dispatch to delivered), total cycle time, reassignment count.
- **Derived:** durations come from `v_order_transition_times`; terminal events use the corresponding
  timestamps and null durations are rendered as empty, never zero.
- **Default sort:** total cycle time descending.
- **Totals:** average and median duration per stage; count of stage SLA breaches if configured.
- **Reconciliation:** stage timestamps must equal `order_status_history` rows.

### R-11 Leave requests

- **Purpose:** leave usage and approval activity.
- **Filters:** `from`, `to` (by leave date or by applied date, selectable); `employee_id`,
  `leave_type_id`, `status`, `department`.
- **Columns:** employee, leave type, paid flag, start date, end date, total days, half-day flag,
  status, applied date, decided date, decided by, decision turnaround, attachment present.
- **Default sort:** start date descending.
- **Totals:** requested, approved, rejected, pending and cancelled day counts; average decision
  turnaround.
- **Reconciliation:** approved days must equal the sum of `USAGE` movements for the corresponding
  requests; pending days must equal outstanding holds.

### R-12 Leave balances

- **Purpose:** current balance position with an explanation.
- **Filters:** `period_year` (required); `employee_id`, `leave_type_id`.
- **Columns:** employee, leave type, entitled, accrued, carried forward, adjustments, used, pending,
  available; plus the derived movement totals from the balance ledger for cross-checking.
- **Default sort:** employee code, then leave type.
- **Totals:** sum per column across the scope.
- **Reconciliation:** `available = entitled + accrued + carried_forward + adjustments - used -
  pending`, and each component must equal the sum of its ledger movements (BR-4.8, DB-14).

### R-13 Advances

- **Purpose:** outstanding advance exposure and recovery progress.
- **Filters:** `from`, `to` (by issue date); `employee_id`, `status`.
- **Columns:** employee, amount, issued date, approved by, repayment mode, installments, recovered
  to date (payroll and cash separately), outstanding, next due period, next due amount, status,
  write-off amount.
- **Default sort:** outstanding descending.
- **Totals:** issued, recovered, outstanding, written-off amounts; counts by status.
- **Reconciliation:** `outstanding = amount - total recovered - written off`; must match
  `advances.outstanding_amount` and the sum of installment recoveries plus cash repayments.

### R-14 Ledger

- **Purpose:** the financial statement per employee.
- **Filters:** `from`, `to` (required); `employee_id`, `entry_type`, `direction`, `period_year`,
  `period_month`.
- **Columns:** employee, business date, entry type, direction, amount, currency, period, reference
  type/id, reason, actor, created at.
- **Derived summary per employee:** opening balance (net before `from`), credits in range, debits in
  range, closing balance (opening + credits - debits).
- **Default sort:** business date ascending, then created at ascending.
- **Totals:** total credits, total debits, net movement across the scope.
- **Notes:** reversals appear as their own rows; the report never nets a reversal away silently, so
  a reader can always see why a balance changed.
- **Reconciliation:** `closing = opening + credits - debits` for every employee; the sum of entries
  must equal the count of `employee_ledger_entries` in range.

### R-15 Salary / payroll

- **Purpose:** the authoritative payroll output for a period.
- **Filters:** `period_year`, `period_month` (required); `employee_id`, `status`
  (`DRAFT`/`FINALIZED`/`PAID`), `payroll_run_id`.
- **Columns:** employee, compensation type, base rate, payable days, present/leave/absent/half/
  weekly-off/holiday day counts, worked hours, overtime hours, gross amount, overtime amount, bonus,
  leave deduction, late deduction, advance deduction, other deduction, total deductions, net amount,
  status, rule snapshot hash, computed/finalized/paid timestamps.
- **Default sort:** employee code ascending.
- **Totals:** sum of each amount column; headcount; total net payable.
- **Notes:** draft rows are clearly labelled as not yet final. Finalized rows are immutable and
  reproducible from their snapshot.
- **Reconciliation:** every row must satisfy `net = gross + overtime + bonus - total_deductions`
  (DB-12) and the day counts must tie to R-02 for the same period.

### R-16 Complaints

- **Purpose:** complaint volume, categories and resolution performance.
- **Filters:** `from`, `to`; `status`, `priority`, `category_id`, `assigned_to`, `include_subject`
  (requires `complaint.read.all`).
- **Columns:** complaint code, category, priority, status, raised by (subject to the caller's
  visibility), raised date, assigned to, resolved date, closed date, resolution time, SLA breached
  flag, comment count, internal comment count.
- **Default sort:** created date descending.
- **Totals:** counts by status, priority and category; average resolution time; SLA breach count.
- **Privacy:** the raiser identity and any subject employee data are omitted for callers without
  `complaint.read.all`; internal notes never appear in a report.
- **Reconciliation:** counts must equal `complaints` rows in scope.

### R-17 Dashboard summary

- **Purpose:** the numbers on the admin and employee dashboards.
- **Permission:** any authenticated user (payload is role-appropriate).
- **Admin payload:** present / absent / incomplete counts for today; open tasks; tasks awaiting
  review; broadcasted-but-unclaimed orders; orders in each active stage; pending corrections; pending
  leave requests; advances outstanding (aggregate only, per permission); open complaints; unread
  notifications.
- **Employee payload:** today's attendance state and next allowed action; my open tasks; available
  orders count; my active claims; leave balance summary; unread notifications.
- **Notes:** every number must come from the same service/query that powers the corresponding list
  or report, so a drill-through link always matches the count.
- **Reconciliation:** each count must equal the number of rows returned by the corresponding
  filtered list endpoint.

### R-18 Audit log export

- **Purpose:** evidence export for investigations or compliance.
- **Permission:** `audit.export` (viewing requires `audit.read`).
- **Filters:** `category`, `action`, `entity_type`, `entity_id`, `actor_user_id`, `from`, `to`.
- **Columns:** timestamp, category, action, actor, actor type, entity type, entity id, reason,
  before, after, request id, IP, user agent.
- **Notes:** before/after values are already redacted; exports are themselves audited; the export
  artifact expires per `files.export_retention_days`.

---

## 4. Common Filter, Sort and Pagination Contract

| Parameter | Behavior |
| --- | --- |
| `from`, `to` | Required for range reports. Business dates (`YYYY-MM-DD`) for date-based reports; UTC timestamps accepted where the endpoint documents it. `from > to` returns `422` |
| `employee_id` | UUID; for a caller without `all` scope it may only be their own id, otherwise `403` |
| `department`, `status`, `priority`, `leave_type_id`, `category_id`, `break_type_id` | Optional filters; unknown values return `422` |
| `group_by` | Enum per report; unknown values return `422` |
| `sort` | Allow-listed fields only, with an implied deterministic tie-breaker |
| `page`, `page_size` | Offset pagination for interactive viewing; `page_size` capped (default `reports.default_page_size`, max 200) |
| `format` | Only for export creation; must be within `reports.export_formats` |
| Unknown parameters | Rejected with `422` so client drift is caught |

Exports use the same filter contract; the export job stores the validated parameter set in
`report_exports.parameters`.

---

## 5. Export Behavior

| Aspect | Rule |
| --- | --- |
| Formats | `CSV` and `XLSX` by default; `PDF` only when the client enables it (`reports.export_formats`, decision 21) |
| Async model | `POST /reports/exports` returns `202` with a job id; the client polls `GET /reports/exports/{id}`; the requester is notified on completion |
| Streaming | Rows stream to object storage; the API never buffers a whole dataset in memory |
| Column headers | Human-readable, stable names; a machine-readable header row is retained for CSV |
| Money in CSV | Decimal strings with 2 decimals, unformatted (no thousands separators) so spreadsheets parse them correctly; XLSX applies number formats and keeps the underlying value exact |
| Dates in CSV | ISO 8601 (`YYYY-MM-DD` for business dates, RFC 3339 UTC for instants) |
| Row count | Recorded on the export job and shown to the user |
| Access | Download only through an authorized, short-lived URL; the export file is private |
| Retention | Artifacts expire after `files.export_retention_days` and are removed by the cleanup job |
| Failure | Status `FAILED` with an error message; no partial artifact is exposed |
| Idempotency | Duplicate export requests with the same key return the original job; an identical in-flight job is refused with `CONFLICT_DUPLICATE` |
| Limits | Rate limited per `security.rate_limit.report_per_minute`; range limited by `reports.max_range_days` |
| Audit | Export creation and download are audited with report type, filters and row count |

---

## 6. Reconciliation and Validation Rules

Agent 5 verifies each report against the database truth. Every report must satisfy its
reconciliation rule under normal operation **and** under the edge cases in
`docs/04_BUSINESS_RULES.md` section 5.

| # | Reconciliation | Verification |
| --- | --- | --- |
| RC-1 | Worked seconds in R-01/R-03 equal a fresh recomputation from events, sessions and breaks | Recompute in SQL/Python for the same range and compare totals and per-row values |
| RC-2 | Day counts in R-02 sum to the number of distinct business dates per employee, with no overlap between statuses | Group by status and compare against the calendar range |
| RC-3 | Break totals in R-04 equal `SUM(break_sessions.duration_seconds)` grouped the same way | Direct aggregate comparison |
| RC-4 | Overtime seconds in R-05 equal `SUM(attendance_records.overtime_seconds)` and never exceed the per-day cap | Direct aggregate plus cap check |
| RC-5 | Punctuality in R-06 equals `late_minutes`/`early_checkout_minutes` sums and is empty when shift tracking is off | Direct aggregate plus a disabled-path test |
| RC-6 | Task counts in R-07 equal `task_assignments` rows, and approved counts equal assignments with an `APPROVED` decision | Direct aggregate comparison |
| RC-7 | Turnarounds in R-08 equal means over `task_submissions` timestamps | Recompute in SQL |
| RC-8 | Order counts in R-09 equal `orders` rows; total amount equals `SUM(order_amount)` exactly | Direct aggregate comparison |
| RC-9 | Stage durations in R-10 match `order_status_history` transitions, with no negative durations | Recompute transitions per order |
| RC-10 | Leave day totals in R-11 equal the corresponding `leave_balance_ledger` movements | Compare per request and in aggregate |
| RC-11 | Balances in R-12 satisfy the balance identity and reconcile with the ledger | Recompute components from the ledger |
| RC-12 | Advance figures in R-13 satisfy `outstanding = amount - recovered - written_off` | Recompute per advance |
| RC-13 | Ledger summaries in R-14 satisfy `closing = opening + credits - debits` per employee and across the scope | Recompute with SQL window functions |
| RC-14 | Salary rows in R-15 satisfy the net-amount identity and tie to R-02 day counts | Database identity check plus cross-report comparison |
| RC-15 | Complaint counts in R-16 equal `complaints` rows in scope and never include internal content | Direct aggregate plus serializer assertion |
| RC-16 | Dashboard counts in R-17 equal the row counts of the corresponding filtered list endpoints | Compare each KPI with its drill-through list under identical filters |
| RC-17 | Exported row counts equal the count reported for the same filters interactively | UI view vs. export comparison |
| RC-18 | Money totals never differ between the interactive report, the export and the underlying `SUM(numeric)` | Three-way comparison with exact decimals |

Any mismatch is a defect (severity set by Agent 5), not a rounding nuance. Money discrepancies and
reconciliation failures in payroll-related reports are treated as `CRITICAL`.

---

## 7. Permissions and Sensitive Data Matrix

| Report | Permission | Sensitive fields excluded by default |
| --- | --- | --- |
| R-01, R-02, R-03, R-04, R-05, R-06 | `report.attendance` | Other employees' verification coordinates (available in the attendance detail view, not in aggregate reports) |
| R-07, R-08 | `report.tasks` | None (task content is internal but not sensitive) |
| R-09, R-10 | `report.orders` | Customer phone numbers masked unless the caller also holds `order.read.all` |
| R-11, R-12 | `report.leaves` | Leave reasons (available in detail, excluded from aggregate reports) |
| R-13, R-14 | `report.ledger` | Bank details never included |
| R-15 | `report.salary` | Bank details and payment references excluded unless `reports.include_sensitive_fields` and the caller holds `employee.read.sensitive` |
| R-16 | `report.complaints` | Raiser identity and subject employee data require `complaint.read.all`; internal comments are never included |
| R-17 | authenticated | Payload is role-scoped; no cross-employee data for employees |
| R-18 | `audit.export` | Secrets, tokens and full bank numbers are redacted at write time and never present |

Report and export generation is audited, and report reads may be audited when `audit.log_reads` is
enabled.

---

## 8. Client Decisions Affecting Reports

| Decision | Effect |
| --- | --- |
| 7, 8, 9 (thresholds, overtime, late/early) | Change the numbers in R-02, R-05 and R-06; the settings used are reported alongside the values |
| 13, 14, 15 (salary, advances, payroll process) | Change R-13 and R-15 semantics and totals |
| 21 (required report formats) | Determines whether `PDF` is offered; CSV/XLSX are always available |
| 23 (retention) | Determines export artifact lifetime and audit retention |
| 24 (business timezone) | Changes date grouping and therefore every range report's totals |
| 25 (employee salary/ledger visibility) | Determines whether employee-scoped runs of R-14 and R-15 are reachable at all |