# 04 - Business Rules

| Field | Value |
| --- | --- |
| Document owner | Agent 1 - Architect / Tech Lead |
| Status | Baseline (implementation-ready; policy items provisional) |
| Version | 1.0 |
| Source-of-truth rank | 2 (only `docs/00_PRODUCT_SCOPE.md` outranks it) |
| Applies to | Agents 2, 3, 4, 5 |

This document defines every business rule of the system, the settings that make those rules
configurable, and the exact behavior for edge cases. `AGENTS.md` section 3 forbids hard-coding
business policy: every value in section 3 of this document is stored in `business_settings` and
read at runtime.

If an implementation detail conflicts with this document, stop and report the conflict
(`AGENTS.md` section 6) before changing behavior.

---

## 1. Purpose and Scope

Three things are specified here:

1. **The settings registry** (section 3) - every configurable business value, its type, default,
   bounds and consuming module.
2. **The rules** (section 4) - attendance, work hours, tasks, orders, leave, ledger/salary,
   complaints and report calculations, each with its formula, decision points and settings.
3. **Edge cases** (section 5) - explicit required behavior for every ambiguous or failure
   scenario listed in the architect brief.

Section 10 records the 25 `CLIENT_DECISION_REQUIRED` items with the provisional default the
system uses until the client confirms a value.

---

## 2. Rule Expression Model

Rules are expressed in four layers, from most to least flexible:

| Layer | Where | Changeable by | Examples |
| --- | --- | --- | --- |
| Business settings | `business_settings` (runtime, versioned, audited) | Admin via `PATCH /settings` | geofence radius, required daily hours, claim timeout, salary basis |
| Configuration data | Tables seeded as data | Admin through CRUD endpoints | break types, leave types, complaint categories, holiday calendar, compensation rates |
| Versioned policy data | Append-only tables | System, with audit | payroll rule snapshots, ledger entries, status history, balance ledger |
| Code | Repository | Release | state machine topology, arithmetic invariants, security checks |

Rules that must never be configurable (because they are integrity or security properties):
atomic claim protection, append-only ledger, no silent mutation of finalized payroll,
self-approval prohibition, authorization enforcement, and the arithmetic identities in
`docs/02_DATABASE.md` section 18.

**Rule versioning.** Attendance records store `settings_snapshot` (the values used for the last
computation). Payroll stores a `payroll_rule_snapshots` row per run and references it from every
salary record. When a setting changes:

- new computations use the new value;
- existing finalized salary records are never recomputed;
- existing attendance records are recomputed only through an explicit, audited action
  (`POST /attendance/{record_id}/recompute`) or a documented sweep job, and the recomputation
  records `computation_version` and the new snapshot;
- the client is warned (in the UI and in the change response) when a setting affects historical
  or in-flight computations.

**Precedence:** a documented product requirement in `docs/00_PRODUCT_SCOPE.md` outranks this
document; this document outranks architecture, database, API, UI, report and test documents.

---

## 3. Settings and Business Rule Registry

Every key below is stored in `business_settings` with the stated type and default. The Admin UI
builds settings forms from `GET /settings/schema`, which is generated from this table
(`docs/03_API_CONTRACT.md` section 7). `PROVISIONAL` marks keys whose default is an assumption
awaiting client confirmation (section 10).

### 3.1 Organization

| Key | Type | Default | Bounds / allowed | Purpose |
| --- | --- | --- | --- | --- |
| `org.name` | STRING | `"Workforce CRM"` | 1..120 chars | Displayed business name |
| `org.timezone` | TIMEZONE | `"Asia/Kolkata"` | valid IANA zone | Business timezone for all business dates - PROVISIONAL (decision 24) |
| `org.currency` | STRING | `"INR"` | ISO 4217 | Default currency for money fields |
| `org.week_starts_on` | INT | `1` | 0..6 (0 = Sunday) | Report week grouping |

### 3.2 Security

| Key | Type | Default | Bounds / allowed | Purpose |
| --- | --- | --- | --- | --- |
| `security.session_timeout_minutes` | INT | `720` | 15..43200 | Absolute session lifetime |
| `security.session_idle_timeout_minutes` | INT | `120` | 5..4320 | Idle session timeout |
| `security.password_reset_ttl_minutes` | INT | `120` | 5..10080 | Reset token validity |
| `security.max_failed_logins` | INT | `5` | 1..100 | Failures before lockout |
| `security.lockout_window_minutes` | INT | `15` | 1..1440 | Window in which failures are counted |
| `security.lockout_minutes` | INT | `15` | 1..1440 | Lockout duration |
| `security.password_min_length` | INT | `10` | 8..128 | Password policy |
| `security.password_require_complexity` | BOOL | `true` | - | Password policy |
| `security.rate_limit.login_per_minute` | INT | `10` | 1..1000 | Login throttle per identity/IP |
| `security.rate_limit.checkin_per_minute` | INT | `12` | 1..1000 | Attendance event throttle per employee |
| `security.rate_limit.upload_per_minute` | INT | `20` | 1..1000 | Upload throttle per user |
| `security.rate_limit.report_per_minute` | INT | `5` | 1..1000 | Export throttle per user |
| `security.rate_limit.qr_issue_per_minute` | INT | `6` | 1..1000 | QR issuance throttle per admin |

### 3.3 Attendance verification

| Key | Type | Default | Bounds / allowed | Purpose |
| --- | --- | --- | --- | --- |
| `attendance.verification_mode` | STRING | `"GPS_AND_QR"` | `GPS_AND_QR`, `GPS_OR_QR`, `GPS_ONLY`, `QR_ONLY` | Required check-in evidence - PROVISIONAL (decision 4) |
| `attendance.checkout_verification_mode` | STRING | `"SAME_AS_CHECKIN"` | `SAME_AS_CHECKIN`, `NONE`, `GPS_ONLY`, `QR_ONLY` | Check-out evidence requirement - PROVISIONAL (decision 5) |
| `attendance.geofence_latitude` | DECIMAL | `null` | -90..90 | Shop latitude - PROVISIONAL (decision 1) |
| `attendance.geofence_longitude` | DECIMAL | `null` | -180..180 | Shop longitude - PROVISIONAL (decision 1) |
| `attendance.geofence_radius_m` | DECIMAL | `100.00` | 1..10000 | Permitted distance from the shop - PROVISIONAL (decision 1) |
| `attendance.gps_accuracy_max_m` | DECIMAL | `100.00` | 1..5000 | Maximum accepted GPS accuracy radius - PROVISIONAL (decision 2) |
| `attendance.location_max_age_seconds` | INT | `60` | 1..900 | Freshness required for a client location fix |
| `attendance.qr_validity_seconds` | INT | `60` | 10..3600 | Dynamic QR validity window - PROVISIONAL (decision 3) |
| `attendance.qr_rotation_seconds` | INT | `45` | 5..3600 | Shop display rotation interval - PROVISIONAL (decision 3) |
| `attendance.qr_single_use` | BOOL | `true` | - | Reject a QR token already consumed - PROVISIONAL (decision 3) |

### 3.4 Attendance, shifts and work hours

| Key | Type | Default | Bounds / allowed | Purpose |
| --- | --- | --- | --- | --- |
| `attendance.shift_tracking_enabled` | BOOL | `true` | - | Enables late/early computation from shift times |
| `attendance.shift_start_time` | TIME | `"09:00"` | valid time | Nominal shift start |
| `attendance.shift_end_time` | TIME | `"19:00"` | valid time | Nominal shift end |
| `attendance.shift_crosses_midnight` | BOOL | `false` | - | Shift belongs to the starting business date |
| `attendance.required_daily_hours` | DECIMAL | `10.00` | 1..24 | Expected active hours per day - PROVISIONAL (decision 7) |
| `attendance.full_day_min_hours` | DECIMAL | `10.00` | 0.5..24 | Worked hours for FULL_DAY - PROVISIONAL (decision 7) |
| `attendance.half_day_min_hours` | DECIMAL | `5.00` | 0.5..24 | Worked hours for HALF_DAY - PROVISIONAL (decision 7) |
| `attendance.partial_day_min_hours` | DECIMAL | `0.50` | 0.01..24 | Minimum worked hours to count as PARTIAL_DAY - PROVISIONAL (decision 7) |
| `attendance.allow_multiple_sessions_per_day` | BOOL | `true` | - | Multiple in/out cycles allowed |
| `attendance.max_sessions_per_day` | INT | `6` | 1..50 | Abuse guard |
| `attendance.overtime_enabled` | BOOL | `true` | - | Overtime is tracked - PROVISIONAL (decision 8) |
| `attendance.overtime_threshold_hours` | DECIMAL | `10.00` | 1..24 | Hours after which overtime accrues - PROVISIONAL (decision 8) |
| `attendance.overtime_min_minutes` | INT | `30` | 0..240 | Minimum overtime increment - PROVISIONAL (decision 8) |
| `attendance.overtime_cap_hours_per_day` | DECIMAL | `4.00` | 0..12 | Maximum overtime per day - PROVISIONAL (decision 8) |
| `attendance.late_grace_minutes` | INT | `10` | 0..240 | Grace before counting late - PROVISIONAL (decision 9) |
| `attendance.early_checkout_grace_minutes` | INT | `10` | 0..240 | Grace before counting early checkout - PROVISIONAL (decision 9) |
| `attendance.break_tracking_enabled` | BOOL | `true` | - | Employees record breaks - PROVISIONAL (decision 6) |
| `attendance.auto_break_deduction_minutes` | INT | `60` | 0..480 | Fixed daily break deduction when break tracking is disabled - PROVISIONAL (decision 6) |
| `attendance.break_max_minutes_per_day` | INT | `90` | 0..720 | Total break cap for the day |
| `attendance.missing_checkout_policy` | STRING | `"REQUIRE_CORRECTION"` | `REQUIRE_CORRECTION`, `AUTO_CLOSE_AT_SHIFT_END`, `AUTO_CLOSE_WITH_MAX`, `MARK_INCOMPLETE` | Handling for an unclosed session - PROVISIONAL (decision 10) |
| `attendance.auto_close_grace_minutes` | INT | `60` | 0..1440 | Grace after shift end before auto-close |
| `attendance.auto_close_max_hours` | DECIMAL | `10.00` | 0.5..24 | Cap used by `AUTO_CLOSE_WITH_MAX` |
| `attendance.field_work_allowed` | BOOL | `true` | - | Employees may leave the shop after valid attendance - PROVISIONAL (decision 11) |
| `attendance.correction_requires_approval` | BOOL | `true` | - | Corrections need admin approval |
| `attendance.correction_max_backdate_days` | INT | `7` | 0..365 | How far back a correction may reach - PROVISIONAL (decision 10) |
| `attendance.recompute_open_records` | BOOL | `true` | - | Sweep job recomputes open records |

### 3.5 Tasks

| Key | Type | Default | Bounds / allowed | Purpose |
| --- | --- | --- | --- | --- |
| `tasks.require_evidence_on_submit` | BOOL | `true` | - | A submission must include a description or attachment |
| `tasks.attachment_mode` | STRING | `"OPTIONAL"` | `NEVER`, `ALWAYS`, `OPTIONAL` | Attachment requirement |
| `tasks.max_attachments_per_submission` | INT | `5` | 0..20 | Evidence limit |
| `tasks.reminder_hours_before_due` | INT | `24` | 1..336 | Due reminder lead time |
| `tasks.overdue_escalation_enabled` | BOOL | `false` | - | Escalate overdue tasks to Admin |
| `tasks.allow_multiple_assignees` | BOOL | `true` | - | A task may be assigned to several employees |
| `tasks.allow_self_review` | BOOL | `false` | - | Must remain false (segregation of duties) |
| `tasks.reopen_on_rejection` | BOOL | `false` | - | A rejected assignment may be reopened instead of requiring a new task |

### 3.6 Orders

| Key | Type | Default | Bounds / allowed | Purpose |
| --- | --- | --- | --- | --- |
| `orders.broadcast_audience` | STRING | `"ALL_ACTIVE_EMPLOYEES"` | `ALL_ACTIVE_EMPLOYEES`, `ROLE` | Default broadcast audience |
| `orders.claim_timeout_minutes` | INT | `30` | 1..1440 | Claim validity before automatic release - PROVISIONAL (decision 16) |
| `orders.auto_release_on_timeout` | BOOL | `true` | - | Sweeper releases expired claims - PROVISIONAL (decision 16) |
| `orders.claim_requires_active_attendance` | BOOL | `false` | - | Only checked-in employees may claim - PROVISIONAL (decision 11) |
| `orders.max_active_claims_per_employee` | INT | `3` | 1..50 | Concurrency guard per employee |
| `orders.allow_rebroadcast_after_release` | BOOL | `true` | - | Released order returns to the pool |
| `orders.reassignment_requires_reason` | BOOL | `true` | - | Reassignment needs a reason |
| `orders.reassign_permission` | STRING | `"ADMIN_ONLY"` | `ADMIN_ONLY`, `ADMIN_AND_SELF` | Who may reassign - PROVISIONAL (decision 17) |
| `orders.max_reassignments` | INT | `5` | 0..50 | Abuse guard |
| `orders.cancel_allowed_statuses` | JSON | `["BROADCASTED","CLAIMED","PACKING","PACKED","READY_FOR_DELIVERY"]` | subset of statuses | Cancellable states - PROVISIONAL (decision 18) |
| `orders.allow_status_skip` | BOOL | `false` | - | Skip lifecycle states - PROVISIONAL (decision 18) |
| `orders.pod_required` | BOOL | `true` | - | Proof of delivery required - PROVISIONAL (decision 19) |
| `orders.pod_requires_photo` | BOOL | `true` | - | Photo proof required - PROVISIONAL (decision 19) |
| `orders.pod_requires_customer_confirmation` | BOOL | `false` | - | Customer confirmation required - PROVISIONAL (decision 19) |
| `orders.pod_requires_location` | BOOL | `false` | - | Location evidence required - PROVISIONAL (decision 19) |
| `orders.packing_proof_required` | BOOL | `false` | - | Packing photo required before PACKED |
| `orders.failure_requires_reason` | BOOL | `true` | - | Failure must be explained |

### 3.7 Leave

| Key | Type | Default | Bounds / allowed | Purpose |
| --- | --- | --- | --- | --- |
| `leaves.enabled` | BOOL | `true` | - | Leave module availability |
| `leaves.enforce_overlap` | BOOL | `true` | - | Overlapping requests rejected - PROVISIONAL (decision 12) |
| `leaves.allow_half_day` | BOOL | `false` | - | Half-day leave allowed - PROVISIONAL (decision 12) |
| `leaves.max_advance_days` | INT | `60` | 0..730 | How early leave may be requested - PROVISIONAL (decision 12) |
| `leaves.max_backdate_days` | INT | `0` | 0..365 | Backdated applications allowed |
| `leaves.requires_attachment_after_days` | INT | `3` | 0..365 | Attachment required beyond this length - PROVISIONAL (decision 12) |
| `leaves.accrual_mode` | STRING | `"MANUAL"` | `ANNUAL_UPFRONT`, `MONTHLY_ACCRUAL`, `MANUAL` | How entitlement accrues - PROVISIONAL (decision 12) |
| `leaves.accrual_day_of_month` | INT | `1` | 1..28 | Monthly accrual day |
| `leaves.carry_forward_enabled` | BOOL | `false` | - | Unused leave carries forward - PROVISIONAL (decision 12) |
| `leaves.carry_forward_max_days` | DECIMAL | `0.00` | 0..365 | Carry-forward cap - PROVISIONAL (decision 12) |
| `leaves.balance_reset_month` | INT | `1` | 1..12 | Leave-year start month - PROVISIONAL (decision 12) |
| `leaves.allow_negative_balance` | BOOL | `false` | - | Negative balance permitted |
| `leaves.allow_admin_self_approval` | BOOL | `false` | - | Admin approving own leave (segregation of duties) |
| `leaves.weekend_counts_as_leave` | BOOL | `false` | - | Weekly offs consume leave days - PROVISIONAL (decision 12) |

### 3.8 Payroll, ledger and advances

| Key | Type | Default | Bounds / allowed | Purpose |
| --- | --- | --- | --- | --- |
| `payroll.enabled` | BOOL | `true` | - | Payroll module availability |
| `payroll.basis` | STRING | `"FIXED_MONTHLY"` | `FIXED_MONTHLY`, `DAILY_WAGE`, `HOURLY` | Default pay basis - PROVISIONAL (decision 13) |
| `payroll.working_days_basis` | STRING | `"WEEKLY_OFF"` | `CALENDAR`, `WEEKLY_OFF`, `BUSINESS_CALENDAR` | How payable days are denominated - PROVISIONAL (decision 13) |
| `payroll.weekly_off_days` | JSON | `[0]` | array of 0..6 | Weekly off day numbers - PROVISIONAL (decision 13) |
| `payroll.payable_day_basis` | STRING | `"ATTENDANCE_DERIVED"` | `ATTENDANCE_DERIVED`, `FIXED_DAYS_IN_MONTH` | Payable day denominator - PROVISIONAL (decision 13) |
| `payroll.fixed_days_in_month` | INT | `30` | 1..31 | Denominator for `FIXED_DAYS_IN_MONTH` - PROVISIONAL (decision 13) |
| `payroll.rounding_mode` | STRING | `"HALF_UP"` | `HALF_UP`, `HALF_EVEN`, `FLOOR` | Money rounding mode - PROVISIONAL (decision 13) |
| `payroll.overtime_enabled` | BOOL | `true` | - | Overtime is paid - PROVISIONAL (decision 8) |
| `payroll.overtime_rate_multiplier` | DECIMAL | `1.50` | 1..5 | Overtime pay multiplier - PROVISIONAL (decision 8) |
| `payroll.partial_day_pay_fraction_mode` | STRING | `"PRO_RATA_HOURS"` | `PRO_RATA_HOURS`, `FIXED_FRACTION`, `NO_PAY` | How partial days are paid - PROVISIONAL (decision 7) |
| `payroll.partial_day_fixed_fraction` | DECIMAL | `0.50` | 0..1 | Used by `FIXED_FRACTION` - PROVISIONAL (decision 7) |
| `payroll.paid_leave_counts_as_payable` | BOOL | `true` | - | Paid leave days are payable - PROVISIONAL (decision 13) |
| `payroll.holiday_pay_enabled` | BOOL | `true` | - | Paid holidays are payable - PROVISIONAL (decision 13) |
| `payroll.weekly_off_pay_enabled` | BOOL | `true` | - | Weekly offs are payable - PROVISIONAL (decision 13) |
| `payroll.unpaid_leave_deduction_enabled` | BOOL | `true` | - | Unpaid leave reduces pay - PROVISIONAL (decision 13) |
| `payroll.late_deduction_enabled` | BOOL | `false` | - | Late arrivals reduce pay - PROVISIONAL (decision 9) |
| `payroll.late_deduction_per_occurrence` | DECIMAL | `0.00` | 0..1e7 | Late deduction amount - PROVISIONAL (decision 9) |
| `payroll.late_deduction_after_minutes` | INT | `30` | 0..1440 | Minutes after which a late deduction applies - PROVISIONAL (decision 9) |
| `payroll.payroll_lock_day_of_month` | INT | `5` | 1..28 | Day the previous period locks - PROVISIONAL (decision 15) |
| `payroll.require_finalize_before_pay` | BOOL | `true` | - | Integrity guard |
| `payroll.require_attendance_corrections_resolved` | BOOL | `true` | - | Block finalize while corrections are pending - PROVISIONAL (decision 15) |
| `advance.enabled` | BOOL | `true` | - | Advance module availability |
| `advance.requires_approval` | BOOL | `true` | - | Advances need approval - PROVISIONAL (decision 14) |
| `advance.max_outstanding_percent_of_salary` | DECIMAL | `50.00` | 0..100 | Outstanding cap relative to monthly pay - PROVISIONAL (decision 14) |
| `advance.max_percent_recovered_per_month` | DECIMAL | `25.00` | 0..100 | Monthly recovery cap - PROVISIONAL (decision 14) |
| `advance.min_installment_amount` | DECIMAL | `500.00` | 0..1e7 | Minimum installment - PROVISIONAL (decision 14) |
| `advance.max_installment_count` | INT | `12` | 1..120 | Installment count cap |
| `advance.allow_cash_repayment` | BOOL | `true` | - | Cash repayment outside payroll |
| `ledger.allow_manual_entries` | BOOL | `true` | - | Manual ledger adjustments allowed |
| `ledger.require_reason` | BOOL | `true` | - | Every financial entry needs a reason |

### 3.9 Complaints

| Key | Type | Default | Bounds / allowed | Purpose |
| --- | --- | --- | --- | --- |
| `complaints.enabled` | BOOL | `true` | - | Complaint module availability |
| `complaints.allow_anonymous` | BOOL | `false` | - | Anonymous complaints - PROVISIONAL (decision 20) |
| `complaints.employee_visibility` | STRING | `"OWN_ONLY"` | `OWN_ONLY`, `ALL_NON_INTERNAL` | What employees may see - PROVISIONAL (decision 20) |
| `complaints.default_priority` | STRING | `"NORMAL"` | `LOW`,`NORMAL`,`HIGH`,`URGENT` | Default priority |
| `complaints.default_visibility` | STRING | `"EMPLOYEE_PRIVATE"` | `EMPLOYEE_PRIVATE`,`ADMIN_ONLY`,`INTERNAL_TEAM` | Default visibility - PROVISIONAL (decision 20) |
| `complaints.sla_hours` | INT | `72` | 1..8760 | Resolution SLA for `sla_due_at` - PROVISIONAL (decision 20) |
| `complaints.employee_can_comment_after_close` | BOOL | `false` | - | Post-closure commenting |
| `complaints.employee_may_reference_employee` | BOOL | `false` | - | Employees may name a subject employee - PROVISIONAL (decision 20) |

### 3.10 Notifications, files, reports, audit and platform

| Key | Type | Default | Bounds / allowed | Purpose |
| --- | --- | --- | --- | --- |
| `notifications.channels_enabled` | JSON | `["IN_APP","WEB_PUSH"]` | subset of channels | Enabled delivery channels - PROVISIONAL (decision 22) |
| `notifications.web_push_enabled` | BOOL | `true` | - | Browser push - PROVISIONAL (decision 22) |
| `notifications.quiet_hours_enabled` | BOOL | `false` | - | Suppress non-critical pushes at night |
| `notifications.quiet_hours_start` | TIME | `"21:00"` | valid time | Quiet hours start |
| `notifications.quiet_hours_end` | TIME | `"08:00"` | valid time | Quiet hours end |
| `notifications.max_delivery_attempts` | INT | `5` | 1..20 | Retry limit |
| `notifications.retention_days` | INT | `180` | 7..3650 | In-app notification retention |
| `notifications.task_reminder_enabled` | BOOL | `true` | - | Task reminder notifications |
| `notifications.order_broadcast_enabled` | BOOL | `true` | - | Broadcast notifications |
| `notifications.daily_summary_enabled` | BOOL | `false` | - | Daily summary notification |
| `files.max_upload_mb` | INT | `10` | 1..100 | Upload size limit |
| `files.allowed_mime_types` | JSON | `["image/jpeg","image/png","image/webp","application/pdf"]` | MIME list | Upload allow-list |
| `files.presigned_url_ttl_seconds` | INT | `300` | 30..3600 | Download URL validity |
| `files.export_retention_days` | INT | `7` | 1..365 | Generated export retention |
| `files.max_attachments_per_entity` | INT | `10` | 1..100 | Attachment cap per record |
| `files.virus_scan_enabled` | BOOL | `false` | - | Scanning integration switch |
| `reports.max_range_days` | INT | `366` | 1..3650 | Maximum report range |
| `reports.export_formats` | JSON | `["CSV","XLSX"]` | subset of `CSV`,`XLSX`,`PDF` | Offered formats - PROVISIONAL (decision 21) |
| `reports.default_page_size` | INT | `50` | 10..200 | Report page size |
| `reports.include_sensitive_fields` | BOOL | `false` | - | Include sensitive employee fields in reports |
| `reports.grouping_timezone` | STRING | `"BUSINESS"` | `BUSINESS`,`UTC` | Grouping timezone for reports |
| `audit.retention_days` | INT | `2555` | 30..18250 | Audit retention - PROVISIONAL (decision 23) |
| `audit.log_reads` | BOOL | `false` | - | Audit read access as well as writes |
| `data.retention_days` | INT | `2555` | 30..18250 | General data retention - PROVISIONAL (decision 23) |
| `platform.idempotency_ttl_hours` | INT | `24` | 1..720 | Idempotency key retention |
| `platform.outbox_batch_size` | INT | `100` | 1..1000 | Outbox dispatch batch |
| `platform.job_batch_size` | INT | `500` | 1..5000 | Job processing batch |

Total: 157 settings. Any newly needed business value must be added to this registry (with a
migration and a `business_settings` seed row) before it may be used in code.---

## 4. Business Rules

### 4.1 Attendance verification (BR-4.1)

Attendance is verified at discrete events only - check-in, check-out and break start/end. The
system must never continuously track location (`AGENTS.md` section 9,
`docs/00_PRODUCT_SCOPE.md` section 4).

**Verification decision procedure (check-in):**

1. **State check.** The employee must have no open work session
   (`attendance_sessions` partial unique index) and `attendance.field_work_allowed` does not
   bypass this. A duplicate check-in is rejected with `STATE_CONFLICT` and the existing open
   session is returned.
2. **Method resolution.** `mode = attendance.verification_mode`:
   - `GPS_AND_QR`: GPS must pass **and** QR must pass.
   - `GPS_OR_QR`: at least one must pass; the other is recorded but not required. A missing
     required-evidence case never occurs; a failed-but-not-required method is recorded as
     `PASSED_WITH_WARNING` on the overall result.
   - `GPS_ONLY` / `QR_ONLY`: only that method is evaluated; the other evidence is ignored.
3. **GPS evaluation** (when applicable):
   - `latitude`, `longitude`, `accuracy_meters`, `location_captured_at` are required. Absence is
     a failure with `failure_code = LOCATION_UNAVAILABLE`.
   - `location_captured_at` must be within `attendance.location_max_age_seconds` of the server
     time, otherwise `LOCATION_STALE`.
   - `accuracy_meters` must be `<= attendance.gps_accuracy_max_m`, otherwise
     `ACCURACY_EXCEEDS_LIMIT`.
   - Distance from (`attendance.geofence_latitude`, `attendance.geofence_longitude`) is computed
     with the haversine formula using an earth radius of 6371000 m; if
     `distance_meters > attendance.geofence_radius_m` the result is `OUTSIDE_GEOFENCE`.
   - If `attendance.geofence_latitude`/`longitude` are unset, GPS verification cannot pass:
     the request fails with `METHOD_NOT_ALLOWED` and an explicit "location not configured"
     message. This prevents silently accepting attendance at an unconfigured shop.
4. **QR evaluation** (when applicable): the submitted payload is hashed and matched by `nonce`
   against `attendance_qr_tokens`. Required checks: token exists (`QR_INVALID`), not revoked,
   `expires_at > now()` (`QR_EXPIRED`), not consumed when `attendance.qr_single_use` is true
   (`QR_REPLAYED`), and `purpose` matches the event being recorded. Consumption is atomic
   (`UPDATE ... WHERE consumed_at IS NULL`); zero rows affected means another request consumed it
   first and the result is `QR_REPLAYED`.
5. **Outcome.** Passing evidence creates the attendance event, the session row and one
   `attendance_verifications` row per evaluated method, then the day recomputation runs
   (BR-4.3). A failing outcome creates only `attendance_verifications` rows (no event, no
   session) and returns `422 RULE_VIOLATION` with `rule_code = ATTENDANCE_VERIFICATION_FAILED`
   and the specific `failure_code`.
6. **Anti-forgery.** The server ignores any client-supplied notion of "verified", distance,
   business date, employee identity or worked duration. `employee_id` always comes from the
   session.

Check-out uses the same procedure with `mode = attendance.checkout_verification_mode`
(`SAME_AS_CHECKIN` resolves to `attendance.verification_mode`). The client decision on the
check-out rule is item 5.

Manual override: an Admin with `attendance.manage` may record an attendance event with
`method = MANUAL_OVERRIDE` and a mandatory reason; it is audited and flagged in the record.

### 4.2 Break calculation (BR-4.2)

- Break types are configuration data (`break_types`) with `is_paid`, `max_minutes`,
  `requires_approval` and `counts_toward_max_per_day`.
- Only one break may be open at a time; only one work session may be open per employee
  (database-enforced partial unique indexes).
- A break may only start while a work session is open, and must end before check-out. Check-out
  with an open break closes the break first (recording `close_reason = AUTO_CLOSE`) and audits
  the implicit action.
- `break_sessions.duration_seconds` is computed at close as `ended_at - started_at`.
- `is_paid` is snapshotted from the break type at break start, so later policy changes cannot
  silently rewrite already computed work hours.
- Daily break totals are compared against `attendance.break_max_minutes_per_day`; exceeding the
  cap is recorded as an anomaly on the attendance record (`notes` plus an audit entry) and, where
  the client configures it, requires a correction. It never silently deletes break time.
- If `attendance.break_tracking_enabled` is false, no break sessions are recorded and
  `attendance.auto_break_deduction_minutes` is deducted once per day from worked time
  (only when total session time exceeds the deduction). This branch exists because client
  decision 6 may reduce break tracking to lunch only, or remove it.
- Paid breaks do **not** reduce worked hours; unpaid breaks do (BR-4.3).

### 4.3 Work hours, day classification, overtime and late/early (BR-4.3)

**Worked time (canonical formula).**

```
sessions        = closed attendance_sessions for the record, merged so overlaps are counted once
session_seconds = sum of merged session durations
unpaid_break    = sum of durations of closed break_sessions where is_paid = false,
                  intersected with open work intervals (so a break outside a session is not double-counted)
worked_seconds  = max(0, session_seconds - unpaid_break)
```

If break tracking is disabled:

```
worked_seconds = max(0, session_seconds - (auto_break_deduction_minutes * 60))
```

while `session_seconds > auto_break_deduction_minutes * 60`, otherwise `session_seconds`.

`worked_hours` is derived as `worked_seconds / 3600` quantized to 2 decimals (display only; the
authoritative value is `worked_seconds`).

**Day classification.** Evaluated in this order, using `worked_seconds`:

| Condition | `day_classification` |
| --- | --- |
| Record status is `ON_LEAVE`, `HOLIDAY` or `WEEKLY_OFF` | `NONE` (the `status` carries the meaning) |
| `worked_hours >= attendance.full_day_min_hours` | `FULL_DAY` |
| `worked_hours >= attendance.half_day_min_hours` | `HALF_DAY` |
| `worked_hours >= attendance.partial_day_min_hours` | `PARTIAL_DAY` |
| otherwise | `NONE` |

**Status.** `PRESENT` when at least one closed session exists and the record is closed;
`INCOMPLETE` when a session is open or required evidence is missing per BR-4.4; `NOT_MARKED`
when no events exist; `ON_LEAVE`/`HOLIDAY`/`WEEKLY_OFF` are set by the day-initialization
routine from approved leave and `business_holidays`/`payroll.weekly_off_days`; `ABSENT` is set
for a completed business date with no valid attendance and no leave/holiday coverage.

**Overtime.**

```
threshold_seconds = attendance.overtime_threshold_hours * 3600
raw_ot            = max(0, worked_seconds - threshold_seconds)
if attendance.overtime_enabled = false: overtime_seconds = 0
else:
  steps = floor(raw_ot / (attendance.overtime_min_minutes * 60))
  overtime_seconds = min(steps * (attendance.overtime_min_minutes * 60),
                         attendance.overtime_cap_hours_per_day * 3600)
```

**Late arrival and early checkout** (only when `attendance.shift_tracking_enabled` is true):

```
late_minutes = max(0, (first_check_in_at - shift_start_at - late_grace) / 60)   # floor to whole minutes
early_minutes = max(0, (shift_end_at - early_grace - last_check_out_at) / 60)   # floor to whole minutes
```

`shift_start_at`/`shift_end_at` are the shift times on the record's business date in the business
timezone; when `attendance.shift_crosses_midnight` is true the shift end belongs to the next
calendar day. Minutes are informational unless `payroll.late_deduction_enabled` is true.

**Recomputation.** Every attendance event, break close, correction approval and auto-close
triggers recomputation of the affected record. Recomputation is idempotent, bumps
`computation_version`, stores `settings_snapshot`, sets `computed_at`, and audits
`before`/`after` only when derived values actually change.

### 4.4 Missing checkout, attendance correction and field work (BR-4.4)

**Missing checkout** is handled per `attendance.missing_checkout_policy`:

| Policy | Behavior |
| --- | --- |
| `REQUIRE_CORRECTION` | The record stays `INCOMPLETE` with an open session. A reminder notification is sent. The employee must file a correction (BR-4.4). Attendance for the day is not finalized, and payroll treats `INCOMPLETE` days as neither present nor absent until resolved |
| `AUTO_CLOSE_AT_SHIFT_END` | The `attendance_auto_close` job closes the session at `shift_end + auto_close_grace_minutes`, records an `AUTO_CLOSE` event with `close_reason = AUTO_CLOSE`, and flags the record `is_corrected = false` but adds an anomaly note and an audit entry |
| `AUTO_CLOSE_WITH_MAX` | As above, but the closed duration is capped at `attendance.auto_close_max_hours`, and the anomaly is recorded |
| `MARK_INCOMPLETE` | The session is closed at the last known event with `close_reason = AUTO_CLOSE`, and the record remains `INCOMPLETE` pending a correction |

Under every policy the original events are preserved; auto-close adds events and never rewrites
punches. If the employee later files a correction proving a different check-out time, the
correction supersedes the auto-close by adding a new `CORRECTION` event, and the derived values
are recomputed.

**Corrections** (BR-4.4):

- An employee may request a correction for their own record, for a date within
  `attendance.correction_max_backdate_days`.
- A correction carries a mandatory `reason`, an optional attachment, and the requested times.
- Corrections affecting a date inside a `LOCKED` payroll period are rejected with
  `PERIOD_LOCKED`; the Admin must instead post a ledger adjustment (BR-4.10). This is the
  "no silent mutation of finalized payroll" rule.
- Approval (`attendance.correct.approve`) applies the correction: it creates a `CORRECTION`
  attendance event carrying `occurred_at` equal to the corrected time, links it via
  `correction_id`, recomputes the record, stores `previous_computation` on the correction row,
  and audits the decision and the recomputation.
- When `attendance.correction_requires_approval` is false, the correction is applied immediately
  and is still audited with the acting user recorded; the client decision on correction policy is
  item 10.
- Rejection requires notes and changes nothing.
- Self-approval of one's own correction is not permitted; a second actor with
  `attendance.correct.approve` must decide.

**Field work.** An employee may legitimately leave the shop for delivery or field duty. Therefore:

- Location is verified only at attendance events; the system never marks an employee absent or
  invalid because their device is no longer near the shop after a valid check-in.
- Field activity is represented by operational records: order status transitions and proof
  (`OUT_FOR_DELIVERY` -> `DELIVERED`), or a task assignment.
- If `attendance.field_work_allowed` is false, the Admin must still be able to correct or annotate
  the record; the setting governs whether field absence is treated as an anomaly in reports, not
  whether the employee is auto-marked absent.

### 4.5 Duplicate prevention, state machine and recomputation (BR-4.5)

**Attendance state machine** (enforced by the service and by database constraints):

```
NOT_MARKED --check_in--> OPEN (PRESENT, session open)
OPEN --break_start--> OPEN_WITH_BREAK
OPEN_WITH_BREAK --break_end--> OPEN
OPEN --check_out--> CLOSED (PRESENT, classification computed)
OPEN_WITH_BREAK --check_out--> CLOSED (break auto-closed, audited)
OPEN --auto_close--> INCOMPLETE or CLOSED (per missing_checkout_policy)
CLOSED / INCOMPLETE --correction_approved--> recomputed (is_corrected = true)
```

Invalid transitions:

| Attempt | Result |
| --- | --- |
| Check-in while a session is open | `409 STATE_CONFLICT` + current session returned, no event created |
| Check-out with no open session | `409 STATE_CONFLICT` |
| Break start while a break is open | `409 STATE_CONFLICT` + current break returned |
| Break start with no open session | `422 RULE_VIOLATION` (`rule_code = BREAK_WITHOUT_SESSION`) |
| Break end with no open break | `409 STATE_CONFLICT` |
| Check-in exceeding `attendance.max_sessions_per_day` | `422 RULE_VIOLATION` |
| Attendance event for another employee's record | `403`/`404` - the actor always comes from the session |

Duplicate submissions from the UI are additionally protected by `Idempotency-Key`; the database
constraints (DB-1, DB-2) make the guarantee unconditional.

**Recomputation triggers:** attendance event creation, break close, correction approval, holiday
or weekly-off data change affecting the date, approved leave affecting the date, and the
`attendance_recompute` sweep for open records. Each recomputation:

1. loads the record's events, sessions and breaks;
2. reads the current settings (or the snapshot when replaying a historical period);
3. recomputes `worked_seconds`, `break_seconds`, `unpaid_break_seconds`, `overtime_seconds`,
   `late_minutes`, `early_checkout_minutes` and `day_classification`;
4. writes the record with `computation_version + 1` and a new `settings_snapshot`;
5. emits `attendance.record_recalculated.v1` and an audit entry when values changed.

**Reconciliation invariant:** `attendance_records.worked_seconds` must always equal the value
recomputed from sessions and breaks. Agent 4 and Agent 5 verify this by recomputation over the
whole dataset; any mismatch is a defect, not a rounding nuance.---

### 4.6 Task lifecycle and approval (BR-4.6)

**Per-assignment state machine** (`task_assignments.status`):

```
ASSIGNED --start--> STARTED --mark complete--> (work done; still STARTED until submitted)
STARTED --submit--> SUBMITTED
SUBMITTED --approve--> APPROVED            (terminal, success)
SUBMITTED --request_resubmission--> RESUBMISSION_REQUESTED --submit--> SUBMITTED (attempt_no + 1)
SUBMITTED --reject--> REJECTED              (terminal, failure)
ASSIGNED or STARTED --cancel--> CANCELLED   (admin action)
ASSIGNED --unassign--> (assignment removed, only if never started)
```

Rules:

- `start` requires `ASSIGNED`. Submitting requires `STARTED` (or `RESUBMISSION_REQUESTED`).
  Any other combination returns `409 STATE_CONFLICT`.
- `task_assignments.completed_at` records the employee's "work complete" marker; it does not
  imply approval.
- A submission records `attempt_no = previous attempts + 1`, and `task_assignments.attempt_count`
  is incremented in the same transaction. Uniqueness of `(assignment_id, attempt_no)` prevents
  duplicate attempts from a double click.
- Evidence: when `tasks.require_evidence_on_submit` is true, a submission must contain a
  non-empty description or at least one attachment. When `tasks.attachment_mode = ALWAYS` an
  attachment is mandatory; when `NEVER`, attachments are rejected. Attachment count is capped by
  `tasks.max_attachments_per_submission`.
- Submission is only allowed while the task is not cancelled and the assignment is not in a
  terminal state.

**Review rules** (`task.review`):

- Review requires the assignment to be `SUBMITTED` with a submission that has no decision yet.
  A second decision on the same submission returns `409 STATE_CONFLICT`.
- Self-review is forbidden: if the acting user is the assignee (or the assignee's own user
  record), the request is rejected with `403`/`422` regardless of `tasks.allow_self_review`
  (that setting exists only to document the policy and must remain false).
- `approve` sets the submission decision `APPROVED` and the assignment `APPROVED`, and emits
  `task.approved.v1`.
- `request_resubmission` sets the submission decision `RESUBMISSION_REQUESTED` and the assignment
  `RESUBMISSION_REQUESTED`; the employee may then submit again, preserving the previous attempt
  including its evidence and the reviewer's notes.
- `reject` sets `REJECTED` and is terminal for that assignment. Follow-up work requires a new
  task or a new assignment (`tasks.reopen_on_rejection` exists for a future policy and defaults
  to false).
- Review notes are required for `reject` and `request_resubmission`.

**Task-level status rollup** (`tasks.status`): maintained in the same transaction as any
assignment change, using the definitions below. The API returns both the rollup and per-assignment
states; the rollup exists for admin list views and reports.

| `tasks.status` | Condition over assignments |
| --- | --- |
| `CANCELLED` | the task was cancelled |
| `COMPLETED` | every assignment is `APPROVED` (or the task has no assignments left and was explicitly completed) |
| `SUBMITTED` | no `APPROVED`/`REJECTED` pending work remains and at least one assignment is `SUBMITTED` |
| `IN_PROGRESS` | at least one assignment is `STARTED` or `RESUBMISSION_REQUESTED` and none is `SUBMITTED` |
| `ASSIGNED` | otherwise (no work started) |

**Task history:** comments, submissions with decisions, attachments and audit entries are never
deleted. Task edits after a submission are restricted by `task.update` and are audited with
before/after values.

### 4.7 Order broadcast, claiming, lifecycle and reassignment (BR-4.7)

**Registration.** `POST /orders` creates an order and registers the lifecycle start. An order is
only visible to employees once broadcast.

**Broadcast.** `POST /orders/{id}/broadcast` creates an `order_broadcasts` round:

- `audience_scope` defaults to `orders.broadcast_audience`. `ALL_ACTIVE_EMPLOYEES` targets all
  `employment_status = 'ACTIVE'` employees; `ROLE` targets holders of the role(s) in
  `audience_payload`; `EXPLICIT` targets the listed employee ids.
- Only one broadcast round is active per order (partial unique index DB-17). Broadcasting again
  increments `round_no` and deactivates the previous round.
- Broadcasting is allowed when the order is in a pre-delivery state with no active claim, or when
  returning from `REASSIGNED`.
- The broadcast sets `broadcast_at` and emits `order.broadcasted.v1`, which drives the
  notification to the audience.
- A broadcast may carry `expires_at`; after it passes, the order is no longer listed in
  `GET /orders/available` (but remains visible to admins).

**Eligibility to claim.**

1. caller is an employee with `employment_status = 'ACTIVE'` and permission `order.claim`;
2. the order is `BROADCASTED` with an active, non-expired broadcast round that includes them;
3. `orders.claim_requires_active_attendance` is false, or the caller has an open work session
   today;
4. the caller's active claim count is below `orders.max_active_claims_per_employee`;
5. the caller is not the order's creator when the creator is an employee (self-dealing guard).

**Atomic claim.** Claiming is the concurrency-critical operation; the authoritative mechanism is
described in `docs/01_ARCHITECTURE.md` section 21.1. Contract:

- Exactly one concurrent claim may succeed. The winner receives `200` with the order in
  `CLAIMED`; every loser receives `409 CLAIM_ALREADY_TAKEN` including the current order state.
- The database - not the frontend and not a read-then-write check in application code - decides
  the winner, via the conditional `UPDATE` plus the partial unique index on active claims.
- On success the order sets `current_assignee_id`, `claimed_at`,
  `claim_expires_at = now() + orders.claim_timeout_minutes` (when auto-release is enabled),
  appends `order_status_history`, writes the claim row, writes an audit record and emits
  `order.claimed.v1`.
- A retried claim with the same `Idempotency-Key` returns the original success response instead of
  a conflict.

**Order lifecycle** (`docs/00_PRODUCT_SCOPE.md` section 7):

```
BROADCASTED -> CLAIMED -> PACKING -> PACKED -> READY_FOR_DELIVERY -> OUT_FOR_DELIVERY -> DELIVERED
                    \-> REASSIGNED -> BROADCASTED
any pre-delivery -> CANCELLED
any pre-delivery -> FAILED
```

Rules:

- Transitions must follow the graph; skipping states is rejected with
  `422 RULE_VIOLATION` (`rule_code = ORDER_INVALID_TRANSITION`) unless
  `orders.allow_status_skip` is true (client decision 18; default false).
- Only the current holder may perform fulfillment transitions (with `order.update.status.self`),
  or an Admin with `order.update.status.any`.
- Every transition appends `order_status_history` with `from_status`, `to_status`, actor,
  assignee, timestamp, optional reason, and writes an audit record.
- `PACKED` requires packing proof when `orders.packing_proof_required` is true.
- `DELIVERED` requires proof per `orders.pod_required` /
  `orders.pod_requires_photo` / `orders.pod_requires_customer_confirmation` /
  `orders.pod_requires_location`; a missing requirement returns
  `422 RULE_VIOLATION` with `rule_code = ORDER_PROOF_REQUIRED`.
- `FAILED` requires a reason when `orders.failure_requires_reason` is true.
- `DELIVERED` closes the active claim as `COMPLETED` and sets `delivered_at`. Terminal states
  cannot be left.
- `CANCELLED` is allowed only from statuses in `orders.cancel_allowed_statuses` and requires a
  reason (`cancellation_requires_reason` is implied by `orders.failure_requires_reason` and the
  database check `ck_orders_cancelled_reason`).

**Claim release and abandonment.**

- The holder may release a claim they cannot fulfil (`POST /orders/{id}/release`) with a reason.
  The claim closes as `RELEASED`; the order moves to `REASSIGNED` and then `BROADCASTED` when
  `orders.allow_rebroadcast_after_release` is true, creating a new broadcast round.
- An expired claim is released by the `order_claim_sweeper` job when the claim passes
  `claim_expires_at` and `orders.auto_release_on_timeout` is true. The claim closes as `EXPIRED`,
  the order returns to the pool, and both the employee and the Admin are notified
  (`order.claim_released.v1`).
- If auto-release is disabled, an expired claim stays `ACTIVE` until an Admin acts; the order
  remains visible to the Admin as overdue.

**Reassignment** (client decision 17 governs who may reassign; `orders.reassign_permission`
defaults to `ADMIN_ONLY`):

- Reassignment is allowed for pre-delivery statuses; a reason is mandatory when
  `orders.reassignment_requires_reason` is true.
- With `new_assignee_employee_id`, the previous claim closes as `REASSIGNED` and a new claim is
  created atomically for the target employee (still protected by the active-claim unique index).
  Without a target, the order returns to the pool via a new broadcast round.
- `reassign_count` is incremented and capped by `orders.max_reassignments`; exceeding the cap
  requires an explicit override and is audited.
- Reassignment never deletes the previous claim or history; the audit trail keeps prior
  responsibility visible.

**Proof of delivery.** Stored in `order_attachments` with a `purpose`. Optional location evidence
captures `latitude`, `longitude`, `accuracy_meters` for the proof, which is different from
attendance location: it documents delivery, not attendance. Customer confirmation is recorded
with a method and timestamp.

### 4.8 Leave balance and approval (BR-4.8)

**Balance model.** A balance row exists per employee, leave type and leave year.
`available_days` is a stored generated column:

```
available_days = entitled_days + accrued_days + carried_forward_days + adjustment_days
                 - used_days - pending_days
```

Every change to a component happens together with an append-only `leave_balance_ledger` row
(positive increases availability, negative decreases it). The balance row is a cache of the
ledger and must always reconcile with it.

**Application.**

1. Validate the leave type is active, dates are ordered, the leave year is open, the request is
   within `leaves.max_advance_days` in the future and no further back than
   `leaves.max_backdate_days`.
2. Half-day requests require `leaves.allow_half_day` and exactly one day with a
   `half_day_period`.
3. `total_days` is computed server-side: working days between `start_date` and `end_date`
   inclusive, excluding weekly offs and holidays unless `leaves.weekend_counts_as_leave` is true;
   a half day counts 0.5.
4. Overlap with any other `PENDING` or `APPROVED` leave of the same employee is rejected with
   `422 RULE_VIOLATION` (`rule_code = LEAVE_OVERLAP`). This is enforced by the database exclusion
   constraint (DB-7) as well.
5. Attachments are required when the requested duration exceeds
   `leaves.requires_attachment_after_days` or the leave type sets
   `requires_attachment_after_days`.
6. Consecutive-day limits per leave type are enforced.
7. If `leaves.allow_negative_balance` is false and the balance is insufficient, the request is
   rejected with `rule_code = LEAVE_BALANCE_INSUFFICIENT`. When it is sufficient, a negative
   `PENDING_HOLD` movement is posted immediately (so two concurrent applications cannot both
   consume the same days), inside a `FOR UPDATE` lock on the balance row.

**Decision.**

- `approve`: requires `leave.approve`, a `PENDING` request, no self-approval unless
  `leaves.allow_admin_self_approval` is explicitly enabled, sufficient balance and no overlap
  introduced since application. Effects (one transaction): status `APPROVED`, `decided_by`/
  `decided_at`/`decision_notes`, hold converted to `USAGE` (`PENDING_RELEASE` + `USAGE`
  movements, or a single net movement pattern documented in the code), `used_days` incremented,
  `pending_days` decremented, attendance records for the covered dates moved to `ON_LEAVE`, and
  `leave.approved.v1` emitted.
- `reject`: requires notes, releases the hold with `PENDING_RELEASE`, and never touches attendance.
- `request_modification`: sets `MODIFICATION_REQUESTED`, keeps the hold in place, and notifies the
  employee. The employee may edit and resubmit (which returns the request to `PENDING`) or cancel.
- Self-approval by the leave holder is prohibited (`rule_code = SELF_APPROVAL_NOT_ALLOWED`).

**Cancellation.**

- A `PENDING` request may be cancelled by its owner (`leave.cancel.self`) with a reason; the hold
  is released.
- An `APPROVED` request may be cancelled by its owner or by `leave.cancel.any` when the covered
  dates are not inside a `LOCKED` payroll period; cancellation posts a `REVERSAL`/`USAGE` reversal
  movement, decrements `used_days`, and re-runs attendance classification for the affected dates.
- Cancellation inside a locked period is rejected with `PERIOD_LOCKED`; the correction must be
  handled as a balance adjustment plus a ledger adjustment in the current open period.

**Accrual and carry-forward.**

- `leaves.accrual_mode`: `MANUAL` (no automatic changes; Admin posts adjustments),
  `ANNUAL_UPFRONT` (full entitlement posted on the first day of the leave year, or on joining
  pro-rata), `MONTHLY_ACCRUAL` (entitlement / 12 posted on `accrual_day_of_month`).
- Leave-year boundaries use `leaves.balance_reset_month` and the business timezone.
- `leaves.carry_forward_enabled` moves unused days at year end, capped by
  `leaves.carry_forward_max_days`, recording `CARRY_FORWARD` and `EXPIRY` movements as separate
  ledger rows so the history explains the net balance change.

### 4.9 Employee ledger, advances and salary (BR-4.9)

**Ledger sign convention** (must match `docs/02_DATABASE.md` section 13.1):

- `CREDIT` increases the amount owed to the employee: `SALARY_PAYABLE`, `OVERTIME_PAY`,
  `BONUS`, positive `ADJUSTMENT`.
- `DEBIT` reduces it: `ADVANCE_ISSUED`, `ADVANCE_REPAYMENT` (cash), `LEAVE_DEDUCTION`,
  `LATE_DEDUCTION`, `OTHER_DEDUCTION`, `PAYMENT_MADE`.
- `net_balance = sum(CREDIT) - sum(DEBIT)`. A fully paid period nets to zero.
- Entries are append-only. Corrections are `REVERSAL` entries referencing the original
  (`reverses_entry_id`); an entry may be reversed at most once, and both rows stay visible.

**Advance rules.**

- Issuing an advance (BR: `advance.requires_approval`) creates the advance in `PENDING_APPROVAL`
  and, on approval, posts an `ADVANCE_ISSUED` ledger entry and generates
  `installment_count` installments whose amounts sum exactly to `amount` (the last installment
  absorbs rounding).
- Guard: total outstanding advances for the employee must not exceed
  `advance.max_outstanding_percent_of_salary` of the monthly gross equivalent; otherwise
  `422 RULE_VIOLATION` (`rule_code = ADVANCE_LIMIT_EXCEEDED`).
- Recovery: during payroll computation the deduction for the period is
  `min(outstanding_amount, next due installment amount, max_percent_recovered_per_month *
  gross_amount)`. Recovered advance is recorded in `salary_records.advance_deduction`, reduces
  `advances.outstanding_amount`, marks installment(s) `PARTIALLY_RECOVERED`/`RECOVERED`, and
  closes the advance (`CLOSED`) at zero. No separate `ADVANCE_REPAYMENT` ledger entry is posted
  for payroll recovery (double-counting guard).
- `advance.allow_cash_repayment`: a cash repayment outside payroll posts an `ADVANCE_REPAYMENT`
  entry and reduces the outstanding amount; it never exceeds the outstanding amount.
- Write-off closes the advance as `WRITTEN_OFF` with a required reason, is audited, and posts an
  adjustment so the books reflect the decision.

**Salary computation** (client decision 13; the whole formula is settings-driven):

```
1. Resolve the employee's compensation row effective for the period:
   compensation_type, rate  (from employee_compensation)
2. Resolve the working-day denominator for the period:
   working_days =
     CALENDAR          -> number of calendar days in the period
     WEEKLY_OFF        -> calendar days minus payroll.weekly_off_days occurrences
     BUSINESS_CALENDAR -> WEEKLY_OFF result minus non-working days in business_holidays
                          plus is_working_day overrides
3. Resolve day counts from attendance: present_days, half_days, leave_days (paid/unpaid split),
   absent_days, weekly_off_days, holiday_days, partial days, worked_seconds, overtime_seconds
4. payable_days = sum of DayCredit per day, where:
     FULL_DAY           -> 1.00
     HALF_DAY           -> 0.50
     PARTIAL_DAY        -> pro-rata per payroll.partial_day_pay_fraction_mode:
                            PRO_RATA_HOURS -> worked_hours / required_daily_hours   (capped at 1.00)
                            FIXED_FRACTION -> payroll.partial_day_fixed_fraction
                            NO_PAY         -> 0.00
     paid leave day     -> 1.00 when payroll.paid_leave_counts_as_payable
     holiday            -> 1.00 when payroll.holiday_pay_enabled and the holiday is_paid
     weekly off         -> 1.00 when payroll.weekly_off_pay_enabled
     absent / unpaid    -> 0.00
5. Gross:
     FIXED_MONTHLY -> rate * (payable_days / denominator),
                      where denominator = working_days, or payroll.fixed_days_in_month
                      when payroll.payable_day_basis = FIXED_DAYS_IN_MONTH
     DAILY_WAGE    -> rate * payable_days
     HOURLY        -> rate * (worked_seconds / 3600)
6. Overtime amount:
     hourly_equivalent =
       FIXED_MONTHLY -> rate / (working_days * attendance.required_daily_hours)
       DAILY_WAGE    -> rate / attendance.required_daily_hours
       HOURLY        -> rate
     overtime_amount = (overtime_seconds / 3600) * hourly_equivalent *
                       payroll.overtime_rate_multiplier      (0 when payroll.overtime_enabled = false)
7. Deductions:
     leave_deduction   = unpaid_leave_days * daily_rate   (when payroll.unpaid_leave_deduction_enabled)
                         daily_rate = FIXED_MONTHLY -> rate / working_days
                                      DAILY_WAGE    -> rate
                                      HOURLY        -> rate * attendance.required_daily_hours
     late_deduction    = late_occurrences_beyond_threshold * payroll.late_deduction_per_occurrence
                         (0 when payroll.late_deduction_enabled = false)
     advance_deduction = per advance rules above
     other_deduction   = sum of period-tagged manual deduction entries
8. net_amount = gross_amount + overtime_amount + bonus_amount - total_deductions
9. Quantization: every monetary component is quantized to 2 decimals using
   payroll.rounding_mode; sums use exact Decimal arithmetic; rounding happens once per
   component, never repeatedly along the chain
```

Integrity requirements:

- `salary_records.rule_snapshot_id` is mandatory; the snapshot contains every setting read
  during computation, hashed into `settings_hash`.
- `inputs_snapshot` records the attendance/leave/advance inputs used, so a record can be explained
  without recomputing.
- `calculation_breakdown` records each step's intermediate value for explainability and dispute
  resolution.
- The database check `net_amount = gross + overtime + bonus - total_deductions` must hold.
- A record may be recomputed only while the run is `DRAFT`/`COMPUTED` and the record is `DRAFT`.
  `FINALIZED`/`PAID` records are immutable (database trigger, DB-13).
- `net_amount` below zero is allowed only when settings permit recovery beyond pay; the default
  policy is to cap the deduction at the gross payable and carry the remainder forward, which is
  recorded in the breakdown.---

### 4.10 Payroll run lifecycle, locking and post-payroll correction (BR-4.10)

**Run lifecycle:** `DRAFT -> COMPUTED -> FINALIZED -> LOCKED -> PAID` (with `CANCELLED` from a
non-paid state).

| Transition | Requirements | Effects |
| --- | --- | --- |
| create (`DRAFT`) | `salary.compute`, one run per period (DB-6) | Run row created |
| `COMPUTED` | `salary.compute` | Salary records created/recomputed for all active employees with a compensation row; `payroll_rule_snapshots` written; `computed_at` set |
| `FINALIZED` | `salary.finalize`; no pending attendance corrections for the period when `payroll.require_attendance_corrections_resolved` is true (unless an explicit audited override) | Every record becomes immutable; `finalized_by`/`finalized_at` recorded |
| `LOCKED` | `payroll.lock` | Period is closed for attendance corrections and leave changes; `locked_at` recorded |
| `PAID` | `payroll.pay`; requires `payroll.require_finalize_before_pay` | `PAYMENT_MADE` ledger entry per employee; `paid_at` recorded |
| `CANCELLED` | `salary.compute` + reason | Only before finalization |

**Lock semantics.** A locked period rejects: attendance corrections targeting dates inside the
period (`423 PERIOD_LOCKED`), leave cancellations covering those dates, and edits to salary
records. An Admin with `payroll.unlock` may unlock with a mandatory reason; unlocking is audited
and notifies the reviewer.

**Post-payroll attendance correction** (required edge case). If a correction is needed for a date
inside a finalized or locked period:

1. the correction is not applied to the historical record;
2. the Admin creates an adjustment in the current open period:
   - an `ADJUSTMENT` or `LEAVE_DEDUCTION`/`OVERTIME_PAY` ledger entry with a reason referencing
     the original period and the correction, or
   - a `leave_balances` adjustment for leave-related effects;
3. the next payroll run picks up the adjustment through the normal "period-tagged manual entries"
   step in the salary formula (step 7d) or as an explicit adjustment entry;
4. the original finalized salary record remains unchanged and is still explainable from its rule
   snapshot.

This is the only permitted way to reflect a late correction; silently recomputing a finalized
period is a defect (`AGENTS.md` section 3, "Do not silently mutate historical financial or
attendance records").

**Month-end payroll.** The period boundary is the business-timezone month. Attendance records
whose `business_date` belongs to a shift that started before the boundary but ended after
midnight belong to the **starting** business date (BR-4.3 shift rule), so a night shift is not
split across two payroll periods. All evidence timestamps stay absolute (`timestamptz`); only the
grouping uses business dates.

### 4.11 Complaint lifecycle and visibility (BR-4.11)

**Statuses:** `OPEN -> IN_REVIEW -> ACTION_REQUIRED -> RESOLVED -> CLOSED`, plus `REJECTED`
(terminal) and back-transitions `ACTION_REQUIRED -> IN_REVIEW` and `RESOLVED -> IN_REVIEW` when
a resolution is disputed.

| Transition | Who | Requirements |
| --- | --- | --- |
| create -> `OPEN` | any employee with `complaint.create.self`; Admin with `complaint.manage` | category, title, description; priority and visibility defaulted from the category or settings |
| `OPEN` -> `IN_REVIEW` | `complaint.manage` | optional assignment to a reviewer |
| `IN_REVIEW` -> `ACTION_REQUIRED` | `complaint.manage` | reason; notifies the raiser unless the complaint is `ADMIN_ONLY` |
| `ACTION_REQUIRED` -> `RESOLVED` | `complaint.resolve` | `resolution_summary` mandatory |
| `IN_REVIEW` -> `RESOLVED` | `complaint.resolve` | `resolution_summary` mandatory |
| `RESOLVED` -> `CLOSED` | `complaint.close` | closes the thread; further comments blocked unless `complaints.employee_can_comment_after_close` |
| any open state -> `REJECTED` | `complaint.resolve` | `rejection_reason` mandatory |
| `RESOLVED` -> `IN_REVIEW` | `complaint.manage` | reason mandatory; reopens a disputed resolution |

`resolved_at`, `closed_at` and `rejection_reason` are required by database check constraints for
the corresponding statuses. Every transition writes `complaint_status_history` and an audit record
(`COMPLAINT` category), and emits `complaint.status_changed.v1`.

**Visibility rules.**

| Visibility | Visible to |
| --- | --- |
| `EMPLOYEE_PRIVATE` | the raiser and holders of `complaint.read.all` |
| `ADMIN_ONLY` | holders of `complaint.read.all` only (the raiser still sees their own submission and its status, but not internal content) |
| `INTERNAL_TEAM` | the raiser, holders of `complaint.read.all` and holders of `complaint.read.internal` |

- `is_internal` comments are visible only with `complaint.read.internal` and are never returned to
  a raiser.
- A complaint about another employee (`subject_employee_id`) is never visible to that subject
  employee unless the client explicitly enables it; the default is that subjects cannot see
  complaints about them.
- Employees may reference another employee as subject only when
  `complaints.employee_may_reference_employee` is true (client decision 20).
- Anonymous complaints (`complaints.allow_anonymous`, default false): when enabled, the raiser is
  hidden from non-admin users but the actor is still recorded internally for audit - the system
  never loses the ability to attribute an action.
- Visibility changes are audited because reducing visibility hides information from the raiser.

### 4.12 Employee lifecycle effects (BR-4.12)

**Onboarding.** Creating an employee creates the user account, the profile, initial role
assignment (`EMPLOYEE`) and optionally the initial compensation row, all in one transaction. The
account starts with `must_change_password = true` when an initial password is generated.

**Profile edits.** Self-service edits are limited to the allow-list in
`docs/03_API_CONTRACT.md` section 5. Identity fields (`employee_code`, `date_of_joining`,
`employment_status`), bank details, compensation and role assignment require the corresponding
admin permissions. Every change is audited with before/after values.

**Deactivation.** Deactivation (`employment_status = 'EXITED'`, `date_of_exit`, user `DISABLED`,
sessions revoked) does **not** delete anything. Consequences:

| Area | Behavior |
| --- | --- |
| Authentication | All sessions revoked immediately; login rejected with `ACCOUNT_DISABLED` |
| Attendance | Existing records unchanged; no new events can be created (check-in requires an active employee) |
| Orders | Active claims must be released/reassigned. Deactivation returns `RULE_VIOLATION` listing the blocking orders unless `force` is used with the additional permissions, in which case claims are released as `REVOKED` and the orders return to the pool in the same transaction |
| Tasks | Open assignments remain for the Admin to reassign or cancel; they are never auto-approved or auto-deleted |
| Leave | Pending requests remain for a decision; approved future leave remains recorded (it may be cancelled by `leave.cancel.any`) |
| Ledger / salary | All history remains; an employee with an outstanding advance cannot be closed out without an explicit write-off or settlement decision |
| Reports and audit | Historical rows continue to include the employee, labeled as exited |
| Rehire | Reactivation restores login; historical records continue in the same employee identity (no duplicate employee record), so service history is continuous |

**Last-admin protection.** The system refuses to deactivate, disable or strip the Admin role from
the last remaining active user holding `role.manage`, returning
`422 RULE_VIOLATION` (`rule_code = LAST_ADMIN_PROTECTED`).

### 4.13 Report calculations (BR-4.13)

Every report is derived from the views in `docs/02_DATABASE.md` section 20. All ranges are
half-open on timestamps (`>= from`, `< to`) and inclusive on business dates; grouping uses the
business timezone unless `reports.grouping_timezone` is `UTC`.

| Report | Definitions |
| --- | --- |
| Attendance summary | Per employee: `present_days` = count of records with `status = 'PRESENT'` and classification `FULL_DAY`; `half_days` = count of `HALF_DAY`; `partial_days` = count of `PARTIAL_DAY`; `absent_days` = count of `ABSENT`; `leave_days` = count of `ON_LEAVE`; `holiday_days`, `weekly_off_days`, `incomplete_days` similarly. A day is counted once by classification, and counts are disjoint by construction |
| Work hours | Sum of `worked_seconds`, `break_seconds`, `unpaid_break_seconds` over the range; `worked_hours` derived per employee and overall. Days with `INCOMPLETE` status are reported separately and never mixed into totals silently |
| Breaks | Sum of `break_sessions.duration_seconds` grouped by employee and break type; paid/unpaid split; count of breaks per day; cap violations counted from anomaly notes |
| Overtime | Sum of `overtime_seconds`; `overtime_days` = records with `overtime_seconds > 0`; average overtime per overtime day; overtime payable uses `payroll.overtime_rate_multiplier` and the same hourly equivalent as BR-4.9 step 6 |
| Tasks | `assigned_count`, `started_count`, `submitted_count`, `approved_count`, `rejected_count`, `resubmission_count`, `overdue_count` (open assignment with `due_at < now()`), `completion_rate = approved_count / assigned_count`, `average_review_turnaround` = mean of (`reviewed_at - submitted_at`) over decided submissions |
| Orders | Counts by current status, plus: `claimed_count` (orders with at least one claim in range), `delivered_count`, `failed_count`, `cancelled_count`, `reassigned_count`, `average_claim_time` (`claimed_at - broadcast_at`), `average_pack_time` (`packed_at - claimed_at`), `average_delivery_time` (`delivered_at - dispatched_at`), `total_order_amount` (decimal sum), `average_order_amount` |
| Leaves | `days_requested`, `days_approved`, `days_rejected`, `days_pending`, grouped by leave type, employee and status; balance summary = `entitled + accrued + carried_forward + adjustment - used - pending` per employee/type/year, which must reconcile with `v_leave_balance_current` |
| Advances | `issued_total`, `recovered_total` (payroll recovery + cash repayment), `outstanding_total`, `written_off_total`, `closed_count`, `open_count`, count and value of overdue installments |
| Ledger | Per employee: `credit_total`, `debit_total`, `net` over the range, plus opening/closing balance computed as the net of all entries before `from` and through `to`. Entries are never netted in a way that hides a reversal: reversals are shown as their own rows |
| Salary | Per employee for the period: all salary components, `total_deductions`, `net_amount`, run status, rule snapshot hash. Totals across employees sum the exact decimals |
| Complaints | Counts by status, priority and category; `open_count`, `resolved_count`, `closed_count`, `rejected_count`, `average_resolution_time` (mean of `resolved_at - created_at` over resolved complaints), `sla_breached_count` (`resolved_at > sla_due_at` or unresolved past `sla_due_at`). Subject employee data appears only with `complaint.read.all` and is omitted for users without it |
| Dashboard summary | Admin: today's present/absent/incomplete counts, open tasks, broadcasted/unclaimed orders, pending leaves, pending corrections, open complaints, unread notifications. Employee: own today's attendance state and next allowed action, own open tasks, own available orders and active claims, own leave balance, unread notifications. All values are computed by the same services the detail endpoints use - never by duplicated frontend logic |

Report rules: sensitive fields (`reports.include_sensitive_fields`) are excluded by default;
ranges above `reports.max_range_days` are rejected; totals are computed with exact decimal
arithmetic; a report never returns rows the caller could not obtain individually.---

## 5. Edge Cases - Required Handling

Each row is a mandatory behavior. "Mechanism" names the enforcement point so an implementer
cannot satisfy the requirement with a frontend check alone.

### 5.1 Attendance edge cases

| # | Scenario | Required behavior | Mechanism |
| --- | --- | --- | --- |
| E-01 | Duplicate check-in (double tap, retry, two devices) | Exactly one open session; the second attempt returns the existing open session with `409 STATE_CONFLICT` and creates no event | Partial unique index on open sessions (DB-1), state guard, `Idempotency-Key` replay |
| E-02 | Check-out after midnight | The session closes normally; the event belongs to the session's `business_date` (the starting date) when `shift_crosses_midnight` is true, otherwise to the date of the check-out instant | BR-4.3 shift rule; `business_date` derived server-side |
| E-03 | Missing checkout at end of day | Behavior per `attendance.missing_checkout_policy`; original events preserved; auto-close adds an `AUTO_CLOSE` event and an anomaly note; a later correction supersedes it | BR-4.4, `attendance_auto_close` job |
| E-04 | Employee realizes the next morning they never checked out | Correction request for the previous date, within `correction_max_backdate_days`; approved correction recomputes the day and audits before/after | BR-4.4 |
| E-05 | Network failure or app killed during check-in | The backend either recorded the event or it did not - there is no partial state (single transaction). The client retries with the same `Idempotency-Key`; a successful original returns the stored response, otherwise a fresh attempt runs. The UI must show an unambiguous "unknown" state until resolved, and must re-read `GET /attendance/me/today` rather than assuming success | Transaction boundary + idempotency (section 13.6 of the architecture document) |
| E-06 | Offline employee at the shop (no connectivity) | The client may not queue an offline check-in as if verified, because verification evidence must be evaluated server-side at the recorded event time. The UI shows "cannot verify while offline" and the employee must retry with connectivity or request a correction | BR-4.1; verification is server-authoritative |
| E-07 | Location permission denied | Failure with `LOCATION_UNAVAILABLE`; the employee is told precisely what to enable; no event is created | BR-4.1 step 3 |
| E-08 | Location reported but wildly inaccurate (e.g. accuracy 2000 m) | Rejected with `ACCURACY_EXCEEDS_LIMIT`; recorded as evidence with the measured value | `attendance.gps_accuracy_max_m` |
| E-09 | Stale location fix (client caches an old position) | Rejected with `LOCATION_STALE` when older than `attendance.location_max_age_seconds` | BR-4.1 step 3 |
| E-10 | Location genuine but outside the geofence | Rejected with `OUTSIDE_GEOFENCE` and the computed distance; the UI shows the distance so the employee understands | Haversine vs `attendance.geofence_radius_m` |
| E-11 | Geofence not configured (fresh install) | GPS verification fails with `METHOD_NOT_ALLOWED` and an explicit configuration message; attendance is never silently accepted at an unconfigured location | BR-4.1 step 3 |
| E-12 | Expired QR token | Rejected with `QR_EXPIRED`; recorded as evidence; the UI refreshes the displayed code by calling `GET /attendance/qr-tokens/current` | BR-4.1 step 4, `attendance.qr_validity_seconds` |
| E-13 | Replayed QR token (screenshot shared, or two employees scanning one code) | The first consumption wins atomically; subsequent attempts fail with `QR_REPLAYED` and are recorded. Both attempts are visible to the Admin as evidence | Atomic conditional update on `consumed_at`, `attendance.qr_single_use` |
| E-14 | QR clock skew between display device and server | Validity uses server time only; a device whose clock is wrong cannot widen the window. Skew beyond the validity window is simply expiry | Server-side timestamp checks |
| E-15 | Employee checks in at the shop and then leaves for delivery | Attendance stays valid. Field activity is represented by order/task records. No automatic absence, no continuous tracking | `AGENTS.md` section 9, BR-4.4 field work |
| E-16 | Break not ended, then check-out attempted | Break is auto-closed at check-out with `close_reason = AUTO_CLOSE`, audited, then the session closes | BR-4.2 |
| E-17 | Break taken outside a work session (e.g. after check-out) | Rejected: `BREAK_WITHOUT_SESSION` | State guard |
| E-18 | Break exceeds `break_max_minutes_per_day` | Time is still recorded; an anomaly is flagged; the day may require a correction depending on policy. Break time is never silently deleted | BR-4.2 |
| E-19 | Multiple work sessions in one day (split shift) | Supported when `allow_multiple_sessions_per_day` is true; worked time is the sum of sessions minus unpaid breaks; overlapping intervals are merged so time cannot be double counted | BR-4.3 formula |
| E-20 | Sessions exceed `max_sessions_per_day` | Rejected with `RULE_VIOLATION`; an Admin correction can still record legitimate events | Settings guard |
| E-21 | Attendance correction requested for a locked payroll period | Rejected with `423 PERIOD_LOCKED`; the Admin is directed to the adjustment path | BR-4.10 |
| E-22 | Two Admins approve the same correction simultaneously | The first wins; the second receives `409 STATE_CONFLICT` (row lock + status guard). Only one `CORRECTION` event exists | `SELECT ... FOR UPDATE` on the correction row |
| E-23 | Approving a correction creates a duplicate punch (same time already recorded) | The service detects the equivalent existing event and applies the correction idempotently, recording the intent; no duplicate session is created | BR-4.3/4.5 recomputation logic |
| E-24 | Employee's phone clock is wrong (client_time mismatch) | `client_time` is informational only; all authoritative timing uses server time. For corrections, the Admin decides the corrected time | BR-4.1 step 6 |

### 5.2 Task edge cases

| # | Scenario | Required behavior | Mechanism |
| --- | --- | --- | --- |
| E-25 | Task resubmission after `RESUBMISSION_REQUESTED` | A new submission attempt is created with `attempt_no + 1`; previous attempts, evidence and reviewer notes remain visible | DB-10, BR-4.6 |
| E-26 | Double-click on "Submit for review" | One attempt is created; the second call replays the first response | `Idempotency-Key`, `attempt_no` uniqueness |
| E-27 | Employee submits without evidence while evidence is required | Rejected with `RULE_VIOLATION` (`rule_code = TASK_EVIDENCE_REQUIRED`) | `tasks.require_evidence_on_submit`, `tasks.attachment_mode` |
| E-28 | Assignee attempts to review their own submission | Rejected, always, regardless of settings | BR-4.6 self-review prohibition |
| E-29 | Two reviewers decide the same submission simultaneously | Exactly one decision is recorded; the other receives `409 STATE_CONFLICT` | State guard on the submission row |
| E-30 | Task cancelled while an employee is working on it | Assignment becomes `CANCELLED`; the employee is notified; any already-created submission history remains for the record | BR-4.6, `task.cancelled.v1` |
| E-31 | Rejected task needs more work | `REJECTED` is terminal; the Admin creates a new task or a new assignment. The default `tasks.reopen_on_rejection = false` documents this policy | BR-4.6 |
| E-32 | Task due date passes while assigned | The task is reported as overdue (not auto-failed); reminders and optional escalation apply | `tasks.reminder_hours_before_due`, `tasks.overdue_escalation_enabled` |
| E-33 | Assignment to a deactivated employee | Rejected with `VALIDATION_ERROR` (inactive assignee) | BR-4.12 |

### 5.3 Order edge cases

| # | Scenario | Required behavior | Mechanism |
| --- | --- | --- | --- |
| E-34 | Two employees claim the same order simultaneously | Exactly one `200`, exactly one `ACTIVE` claim; the loser receives `409 CLAIM_ALREADY_TAKEN` with the current order state and the UI shows a conflict and refreshes | Conditional update + partial unique index (DB-3) + `Idempotency-Key` |
| E-35 | Employee claims, then abandons (no activity, claim expires) | The `order_claim_sweeper` releases the claim as `EXPIRED` when `auto_release_on_timeout` is true; the order returns to the pool with a new broadcast round; both employee and Admin are notified. When auto-release is off, the order stays with the employee and is surfaced as overdue to the Admin | BR-4.7, `order.claim_released.v1` |
| E-36 | Employee explicitly releases an order they cannot fulfil | Claim closes as `RELEASED` with a reason; order returns to the pool when `allow_rebroadcast_after_release` is true | `POST /orders/{id}/release` |
| E-37 | Reassignment to another employee | Previous claim closes as `REASSIGNED`, new claim created atomically for the target; history and audit preserve prior responsibility; `reassign_count` capped | BR-4.7, DB-3 |
| E-38 | Reassignment without a target (back to pool) | Order moves `REASSIGNED -> BROADCASTED` with an incremented broadcast round | BR-4.7 |
| E-39 | Reassignment attempted after `OUT_FOR_DELIVERY` | Rejected with `RULE_VIOLATION` (not reassignable once dispatched) | BR-4.7 |
| E-40 | Delivery attempted without required proof | Rejected with `RULE_VIOLATION` (`ORDER_PROOF_REQUIRED`) naming the missing requirement (photo, customer confirmation or location) | `orders.pod_*` |
| E-41 | Order cancelled while claimed | Claim closes as `CANCELLED`; the holder is notified; the order is terminal | `orders.cancel_allowed_statuses` |
| E-42 | Order cancelled after delivery | Rejected: `DELIVERED` is terminal | Lifecycle graph |
| E-43 | Broadcast to an audience that includes no eligible employees | Broadcast succeeds but the order is flagged as unclaimed-overdue for the Admin; no silent failure | `order.broadcasted.v1` + admin dashboard |
| E-44 | Employee claims an order whose broadcast expired | Rejected with `RULE_VIOLATION` (not currently available) | Broadcast expiry |
| E-45 | Employee holds the maximum number of active claims | Rejected with `RULE_VIOLATION` (`ACTIVE_CLAIM_LIMIT_REACHED`) | `max_active_claims_per_employee` |
| E-46 | Employee attempts to update an order they do not hold | `404` (hidden) with no information leakage; an Admin with `order.update.status.any` may still act | Object-level authorization |
| E-47 | Status skip attempted (e.g. `CLAIMED` -> `PACKED`) | Rejected unless `orders.allow_status_skip` is explicitly enabled by the client | BR-4.7 |
| E-48 | Order status updated twice with the same target status | The second call returns `409 STATE_CONFLICT` (no-op transitions are not silently accepted) | Transition guard |

### 5.4 Leave edge cases

| # | Scenario | Required behavior | Mechanism |
| --- | --- | --- | --- |
| E-49 | Overlapping leave requests | Rejected with `LEAVE_OVERLAP`; database exclusion constraint makes it unconditional | DB-7, BR-4.8 |
| E-50 | Two overlapping requests submitted simultaneously | Exactly one succeeds; the other fails with a constraint violation mapped to `LEAVE_OVERLAP`; balance holds prevent double consumption | Exclusion constraint + `FOR UPDATE` on the balance row |
| E-51 | Leave request spanning a month or year boundary | Days are counted per business date; balance movements are posted against the leave year of each date's period as configured, and the request records the total; payroll attributes each day to its own period | BR-4.8, BR-4.10 |
| E-52 | Leave request spanning a payroll boundary | Each day is attributed to the period containing that business date; no day is double counted or dropped | BR-4.10 month boundary |
| E-53 | Approval when the balance has been consumed since application | Approval re-checks the balance under a row lock; insufficient balance returns `LEAVE_BALANCE_INSUFFICIENT` and the Admin must reject or adjust | BR-4.8 decision |
| E-54 | Rejection releases the hold exactly once | Idempotent release keyed on the leave status; the ledger row is written once | `balance_pending_hold_applied` flags |
| E-55 | Cancellation of approved leave after attendance was marked `ON_LEAVE` | Attendance for the covered dates is reclassified (to `ABSENT`/`NOT_MARKED` per policy) and recomputed; the reversal is audited | BR-4.8 cancellation |
| E-56 | Half-day request when `allow_half_day` is false | Rejected with `VALIDATION_ERROR` | Settings |
| E-57 | Leave requested for a date that is a weekly off or holiday | Not counted as leave days unless `leaves.weekend_counts_as_leave` is true | BR-4.8 step 3 |
| E-58 | Employee applies for leave earlier than allowed | Rejected when beyond `max_advance_days` | Settings |
| E-59 | Admin attempts to approve their own leave | Rejected (`SELF_APPROVAL_NOT_ALLOWED`) unless `leaves.allow_admin_self_approval` is explicitly enabled | BR-4.8 |
| E-60 | Leave balance adjusted manually into a negative value | Rejected unless `leaves.allow_negative_balance` is true; the resulting balance may never be below `used_days` | BR-4.8, API rule |

### 5.5 Financial edge cases

| # | Scenario | Required behavior | Mechanism |
| --- | --- | --- | --- |
| E-61 | Salary rule changes mid-period or before re-running payroll | New computation uses the new rules and snapshots them; already-finalized records are untouched and remain explainable from their own snapshot | BR-4.9, `payroll_rule_snapshots` |
| E-62 | Attendance correction needed after payroll is finalized/locked | Correction is rejected for the period; an adjustment entry is posted in the current open period; the finalized record is never rewritten | BR-4.10 |
| E-63 | Payroll run re-computed while still `COMPUTED` | Allowed: records are recomputed and replaced in place while `DRAFT`/`COMPUTED`; the previous values are overwritten only because nothing has been finalized, and the recomputation is audited | BR-4.10 |
| E-64 | Payroll finalized with pending attendance corrections | Blocked by `payroll.require_attendance_corrections_resolved`; an explicit audited override is possible with the additional permission | BR-4.10 |
| E-65 | Advance recovery exceeds outstanding amount | Capped at the outstanding amount; the advance closes at zero, never negative | BR-4.9 |
| E-66 | Advance recovery would reduce net pay below zero (or below policy floor) | Deduction is capped by policy and the remainder carries forward, recorded in the breakdown and in the advance's outstanding amount | BR-4.9 |
| E-67 | Advance repayment double-posted (cash repayment and payroll recovery in the same period) | Both are applied sequentially under a row lock; outstanding can never go below zero; the second attempt beyond outstanding is rejected | BR-4.9 |
| E-68 | Manual ledger adjustment keyed twice | `Idempotency-Key` replay returns the original entry; only one ledger row exists | Section 13.6 of the architecture document |
| E-69 | Reversal of an already-reversed entry | Rejected with `RULE_VIOLATION` (`rule_code = ALREADY_REVERSED`) | BR-4.9 |
| E-70 | Salary record edited directly after finalization | Rejected by the immutability trigger, not only by the service | DB-13 |
| E-71 | Employee with no compensation row included in a payroll run | Skipped and reported with a reason in the compute response; the run does not silently pay zero | BR-4.9 |
| E-72 | Dismissed/exited employee mid-period | Included up to `date_of_exit` using the same formulas; payable days are limited to days up to the exit date | BR-4.12 |
| E-73 | Rounding drift (many components, many employees) | Each component is rounded once to 2 decimals; sums use exact decimal arithmetic; the database identity check must hold for every row | BR-4.9 step 9, DB-12 |

### 5.6 Complaint, notification, file and platform edge cases

| # | Scenario | Required behavior | Mechanism |
| --- | --- | --- | --- |
| E-74 | Employee attempts to read a complaint that is not theirs | `404` (hidden), never `403` with details | BR-4.11 visibility |
| E-75 | Employee attempts to read internal comments on their own complaint | Internal comments are never returned to the raiser | `complaint.read.internal` |
| E-76 | Complaint status changed backwards without a reason | Rejected; reopening a resolved complaint requires a reason | BR-4.11 |
| E-77 | Notification delivery fails (push endpoint gone) | The in-app notification still exists; delivery is retried with backoff and marked `FAILED` after `max_delivery_attempts`; business state is unaffected | Outbox + delivery retry |
| E-78 | Duplicate notification for one event | Handlers are idempotent on `event_id`; at-least-once dispatch cannot create two notifications for one event/recipient | Outbox handler idempotency |
| E-79 | File upload interrupted mid-transfer | No `files` row is committed for a failed upload; the object is orphaned at worst and is removed by the storage cleanup job | Upload transaction ordering |
| E-80 | File uploaded with a spoofed extension/MIME | Rejected by magic-byte validation and the allow-list | Files security, section 14 of the architecture document |
| E-81 | Unauthorized file access attempt (guessing a file id) | `404`; the relying entity's authorization decides | Files module authorization |
| E-82 | Download URL leaked after expiry | Presigned URL expires after `presigned_url_ttl_seconds`; issuance is audited | Files module |
| E-83 | Employee tries to access another employee's data by changing an id | `404`/`403`; every list endpoint applies an ownership filter, never a post-filter | Object-level authorization |
| E-84 | Duplicate request from a flaky network (any mutation) | Idempotency key replay for the protected operations; database uniqueness for the rest | Section 18 of the API contract |
| E-85 | Two Admins change the same setting simultaneously | The last committed write wins with an incremented `version`, and both changes are visible in `business_setting_history`; no silent loss of the audit trail | Settings versioning |
| E-86 | Clock/timezone mismatch between server and client | All authoritative time is server-side UTC; client time is informational. Business dates derive from the business timezone | Section 17 of the architecture document |
| E-87 | Server timezone changes (deployment moved) | Business behavior is unaffected because business dates use `org.timezone`, not server local time | Section 17 of the architecture document |
| E-88 | Month-end payroll crossing a month boundary with an open shift | The shift belongs to its starting business date, so it lands wholly in one period | BR-4.3, BR-4.10 |
| E-89 | Settings changed that would alter an already-computed open attendance record | The record is recomputed only by an explicit action or the documented sweep; the change response warns the Admin about affected dates, and recomputation is audited | Section 2 rule versioning |
| E-90 | Database constraint violated by application bug (defense in depth) | The transaction fails with a mapped error (`409`/`422`), never a silent partial write; the error is logged with the constraint name and returned as a generic conflict | DB constraints + error mapping |---

## 6. Validation Rules and Limits

Server-side validation that must hold regardless of client behavior. Rejections use
`422 VALIDATION_ERROR` with a field-level `errors[]` entry naming the failing rule.

| Domain | Rules |
| --- | --- |
| User | Username 3..60 chars, lower-case, `[a-z0-9._-]`, immutable. Email valid and unique (case-insensitive). Password honours `security.password_min_length` and complexity when enabled |
| Employee | `employee_code` 1..30 chars, unique, immutable after creation; `date_of_joining` not in the future by more than 1 day; `date_of_exit >= date_of_joining`; `manager_employee_id != id`; `full_name` 1..120 |
| Compensation | `rate > 0`; one currency per employee history; periods must not overlap; `effective_to >= effective_from` |
| Attendance evidence | `latitude` -90..90, `longitude` -180..180; `accuracy_meters >= 0` and `<= 100000`; `location_captured_at` not more than `location_max_age_seconds` in the past and not in the future by more than 60 s (clock tolerance) |
| Correction | `reason` 5..1000 chars; requested times must be in the past (or within 60 s of now); `requested_check_out_at > requested_check_in_at` when both present; correction type must be consistent with the supplied times |
| Task | `title` 1..200; `due_at` in the future at creation (past dates allowed only for an explicit backdated assignment by an Admin); attachments count and total size within limits |
| Task submission | `description` <= 4000 chars; attachment count <= `tasks.max_attachments_per_submission`; evidence presence per `tasks.require_evidence_on_submit` / `tasks.attachment_mode` |
| Order | `order_code` 3..40, unique, immutable; `order_amount >= 0` with <= 2 decimals; `item_count >= 0`; phone/address length limits; `customer_name` 1..120 |
| Order transition | target status must be an allowed successor for the current status and caller; required proof present; reason present when required |
| Leave | `start_date <= end_date`; `total_days > 0`; half-day requires a single date plus period; reason 5..1000; attachment when required; within `max_advance_days` and `max_backdate_days`; consecutive-day cap per type |
| Ledger entry | `amount > 0` with <= 2 decimals; `direction` in (`CREDIT`,`DEBIT`); `entry_type` permitted for manual creation; `business_date` not in the future; `reason` required when `ledger.require_reason`; period must not be locked |
| Advance | `amount > 0`; installment count 1..`max_installment_count`; installment sum equals amount; outstanding cap check |
| Salary | Period must exist as a run; status transitions valid; finalized records read-only |
| Complaint | `title` 1..200; `description` 10..8000; `priority` in the enum; comment 1..4000; internal comment requires the internal permission; attachments within limits |
| File | Size <= `files.max_upload_mb`; MIME in `files.allowed_mime_types`; magic bytes must match the declared type; filename sanitized (never used as a path); total attachments per entity <= `files.max_attachments_per_entity` |
| Settings | Key must exist in the registry; value must satisfy type, bounds and allowed values; `reason` required |
| Report | `from < to`; range <= `reports.max_range_days`; `format` in `reports.export_formats`; unknown filters rejected |
| Pagination | `page >= 1`; `1 <= page_size <= 100`; sort fields allow-listed per endpoint |

---

## 7. Data Integrity, Recalculation and Reconciliation Rules

1. **Single source of truth per fact.** Punches live in `attendance_events`; worked time is
   derived from sessions/breaks; balances live in ledger tables; cached aggregates
   (`attendance_records`, `leave_balances`, `advances.outstanding_amount`, `orders.status`) are
   always recomputable and are updated in the same transaction as the change that affects them.
2. **No silent mutation.** Status history, ledger entries, submissions, decisions and audit rows
   are append-only. Corrections create new rows that reference the corrected one.
3. **Recomputation is auditable.** Every recomputation records the settings snapshot and bumps a
   version, and writes an audit entry when derived values change.
4. **Reconciliation is testable.** The following equalities must hold on any dataset and are
   verified by Agent 4/5:
   - `attendance_records.worked_seconds` = recomputed worked seconds (BR-4.3);
   - `leave_balances.available_days` = sum of non-expired `leave_balance_ledger` movements, and
     `used_days` equals the sum of `USAGE` magnitudes;
   - `leave_balances.pending_days` = sum of open `PENDING_HOLD` magnitudes;
   - `advances.outstanding_amount` = `amount` - total recovered (installments + cash repayments
     + write-off);
   - `salary_records.net_amount` = `gross + overtime + bonus - total_deductions` (DB-12);
   - `orders.current_assignee_id` matches the single `ACTIVE` claim (or is null);
   - `tasks.status` matches the rollup table in BR-4.6.
5. **Backfill on rule change.** When a setting that affects derived attendance values changes, the
   system does not retroactively rewrite history. An Admin may trigger a bounded, audited
   recomputation for a date range, which records the new snapshot and keeps `before`/`after`
   evidence.
6. **Failure atomicity.** A failure at any point of a multi-step operation leaves no partial
   state: either the whole unit of work commits or none of it does.

---

## 8. Rounding, Time and Money Rules for Calculations

| Topic | Rule |
| --- | --- |
| Rounding mode | `payroll.rounding_mode` (default `HALF_UP`), applied with Python `Decimal.quantize` to 2 decimal places for money and 2 for hours |
| Rounding frequency | Once per component, then exact arithmetic for sums. Never round intermediate ratios and then round again |
| Money type | `numeric(14,2)` in the database, `Decimal` in code, decimal strings over the API. Floating point is forbidden |
| Rates | Stored at `numeric(14,4)` where an hourly rate needs precision; converted with an explicit quantization step |
| Time storage | `timestamptz` in UTC for instants; `date` for business dates |
| Business date derivation | Always in `org.timezone`; never from server local time or from a client-supplied date |
| Duration storage | Integer seconds; hours derived for display and for threshold comparisons via a single documented conversion |
| Threshold comparison | `worked_hours >= threshold` is evaluated on seconds (`worked_seconds >= round(threshold * 3600)`), so a 10.00 threshold is exactly 36000 seconds |
| Date ranges | Half-open on instants (`>= from`, `< to`); inclusive on business dates. Documented per endpoint |
| Month/year boundaries | Business-timezone month and year; leave year starts at `leaves.balance_reset_month` |
| Percentages | Stored as decimal percentages (for example `25.00` = 25%) and applied as `amount * percent / 100` with exact decimal arithmetic, then rounded once |
| Negative values | Money amounts are non-negative with a `direction`; balances may be negative only when a setting explicitly permits it |

---

## 9. Business Rules That Exist for Security and Integrity

These are business rules with a security purpose; they are enforced in the service and must not be
made configurable to the point of being disableable.

1. **Self-approval prohibition** for attendance corrections, leave, task submissions, advances
   and payroll finalization: the acting user must not be the subject of the decision.
   `leaves.allow_admin_self_approval` is the single documented exception and defaults to false.
2. **Segregation of duties** for payroll: computing, finalizing and paying are separate
   permissions, and finalization requires that pending corrections are resolved.
3. **No historical rewrite**: finalized payroll, ledger entries and audit rows are immutable.
4. **Atomic ownership**: order ownership and task assignment cannot be taken by a write that
   does not go through the documented state machine.
5. **Attribution**: every change records an actor. Anonymous complaints still record the actor
   internally for audit while hiding them from other users.
6. **Least privilege in payloads**: sensitive fields (bank details, salary, others' data) are
   omitted server-side, not hidden by the UI.
7. **Evidence integrity**: verification evidence and its outcome are stored as produced; a failed
   verification cannot be edited into a success.
8. **Status history integrity**: lifecycle history rows cannot be inserted or modified through
   public APIs, only by the transitions that generate them.

---

## 10. `CLIENT_DECISION_REQUIRED` Register

Twenty-five policies from `docs/00_PRODUCT_SCOPE.md` section 15 are unresolved. Each has a
provisional default so implementation can proceed. **No item may be treated as final.** Every
defaulted setting carries `is_provisional = true` in `business_settings` and is labeled as
provisional in the admin UI.

| # | Decision | Provisional default | Stored as | Impact if changed |
| --- | --- | --- | --- | --- |
| 1 | Shop location and geofence radius | Coordinates unset; radius 100 m | `attendance.geofence_latitude/longitude/radius_m` | GPS verification cannot pass until coordinates are set - deliberately safe |
| 2 | GPS accuracy tolerance | 100 m | `attendance.gps_accuracy_max_m` | More rejections when lowered; weaker proof when raised |
| 3 | Dynamic QR rotation/validity | Valid 60 s, rotate 45 s, single-use | `attendance.qr_validity_seconds`, `attendance.qr_rotation_seconds`, `attendance.qr_single_use` | Affects offline/scan friction and replay risk |
| 4 | Both GPS and QR required, or fallback | Both required | `attendance.verification_mode` | Changing to `GPS_OR_QR` weakens verification |
| 5 | Check-out verification rule | Same as check-in | `attendance.checkout_verification_mode` | Affects field employees most |
| 6 | Break types; is lunch the only tracked break | Break tracking on, `LUNCH` unpaid 60 min, 60 min auto-deduction when tracking is off | `break_types`, `attendance.break_tracking_enabled`, `attendance.auto_break_deduction_minutes` | Directly changes worked hours and pay |
| 7 | Full/half/partial-day formula | Full 10 h, half 5 h, partial from 0.5 h; partial paid pro-rata by hours | `attendance.full_day_min_hours`, `attendance.half_day_min_hours`, `attendance.partial_day_min_hours`, `payroll.partial_day_pay_fraction_mode` | Changes attendance classification and payroll |
| 8 | Overtime calculation | Enabled; beyond 10 h; 30 min increments; 4 h/day cap; 1.5x | `attendance.overtime_*`, `payroll.overtime_rate_multiplier` | Direct pay impact |
| 9 | Late/early policy | Grace 10 min each; recorded but not deducted | `attendance.late_grace_minutes`, `attendance.early_checkout_grace_minutes`, `payroll.late_deduction_*` | Direct pay impact when deductions are enabled |
| 10 | Missing checkout handling | Require correction; corrections need approval; 7-day backdate | `attendance.missing_checkout_policy`, `attendance.correction_requires_approval`, `attendance.correction_max_backdate_days` | Affects incomplete-day volume and payroll readiness |
| 11 | Field-duty handling | Field work allowed; claiming does not require active attendance | `attendance.field_work_allowed`, `orders.claim_requires_active_attendance` | Affects order claiming eligibility |
| 12 | Leave types and balances | `CASUAL`/`SICK`/`UNPAID` seeded, no entitlement, overlap enforced, half-day off, attachment after 3 days, manual accrual, no carry-forward | `leave_types`, `leaves.*` | Determines leave usability |
| 13 | Salary formula | Fixed monthly; weekly-off-aware working days; attendance-derived payable days; paid leave/holiday/weekly off payable; unpaid leave deducted; half-up rounding | `payroll.*` | Core pay impact; must be confirmed before first payroll |
| 14 | Advance deduction policy | Approval required; outstanding cap 50% of monthly pay; recovery cap 25% per month; min installment 500 | `advance.*` | Cash-flow and pay impact |
| 15 | Payroll lock/finalization process | Compute -> finalize -> lock -> pay; lock day 5; pending corrections block finalization | `payroll.payroll_lock_day_of_month`, `payroll.require_attendance_corrections_resolved` | Operational process |
| 16 | Order claim timeout | 30 min, auto-release on | `orders.claim_timeout_minutes`, `orders.auto_release_on_timeout` | Order throughput vs. hoarding |
| 17 | Who may reassign orders | Admin only | `orders.reassign_permission` | Operational flexibility |
| 18 | Order cancellation rules | Cancellable up to `READY_FOR_DELIVERY`; no status skipping | `orders.cancel_allowed_statuses`, `orders.allow_status_skip` | Lifecycle flexibility |
| 19 | Required proof of delivery | Required: photo; optional: customer confirmation, location | `orders.pod_*` | Dispute risk vs. friction |
| 20 | Complaint privacy/visibility | Employees see own only; not anonymous; employees may not name a subject; SLA 72 h; default visibility `EMPLOYEE_PRIVATE` | `complaints.*` | Confidentiality and trust |
| 21 | Required report formats | CSV and XLSX | `reports.export_formats` | Adds PDF work if required |
| 22 | Notification channels | In-app and web push; email/SMS/WhatsApp adapters not configured | `notifications.channels_enabled`, `notifications.web_push_enabled` | Provider integration work |
| 23 | Data retention policy | 7 years for audit and employment data; 180 days for notifications; 7 days for exports | `audit.retention_days`, `data.retention_days`, `notifications.retention_days`, `files.export_retention_days` | Legal/compliance exposure |
| 24 | Business timezone | `Asia/Kolkata` | `org.timezone` | Changes business-date boundaries, attendance and payroll grouping |
| 25 | Employee access to salary/ledger details | Permissions `salary.read.self` and `ledger.read.self` exist and are grantable; the EMPLOYEE role is seeded with `ledger.read.self` and **without** `salary.read.self` pending confirmation | `rbac` role-permission mapping | Visibility of personal financial data |

Additional provisional assumptions made by Agent 1 that are **not** in the client's list but need
confirmation (recorded here so they are not mistaken for settled policy):

| Item | Provisional default | Stored as |
| --- | --- | --- |
| Employee usernames | Derived from `employee_code` | `users.username` |
| Leave year | Calendar year (January) | `leaves.balance_reset_month` |
| Complaint SLA | 72 hours | `complaints.sla_hours` |
| Report week start | Monday | `org.week_starts_on` |
| Advance approval authority | `advance.approve` held by Admin only | `role_permissions` |
| Whether employees may see colleagues' names on orders | Names not returned to other employees; only their own claim | API serialization (order payloads never include other employees' data) |

---

## 11. Final Verification (Agent 1, Business Rules)

Checklist required by `agent-prompts/01_architect.md`, confirmed for this document:

| Verification | Result |
| --- | --- |
| All modules in Product Scope are covered | Yes - attendance, breaks, location verification, QR, tasks, task submission/approval, orders, broadcasting, claiming, fulfillment, leave, ledger, payroll, advances, complaints, notifications, reports, attachments, audit, settings, search/filter, export |
| Every configurable business rule has a storage/configuration strategy | Yes - 157 keys in section 3, all stored in `business_settings`; break types, leave types, complaint categories and holidays are configuration data; compensation is effective-dated data; rule snapshots preserve historical computations |
| Permissions match workflows | Yes - each rule in section 4 names the permission it requires; the catalog is in `docs/05_PERMISSIONS.md` and the role mapping grants each workflow to the correct role |
| API contracts support the workflows | Yes - the workflow coverage matrix in `docs/03_API_CONTRACT.md` section 21 maps every workflow to endpoints |
| Database supports API requirements | Yes - `docs/02_DATABASE.md` section 18 lists the invariants; section 24 maps modules to tables |
| Reports can be generated from the schema | Yes - `docs/02_DATABASE.md` section 20 defines the views; section 4.13 defines every calculation; `docs/08_REPORT_SPEC.md` specifies the outputs |
| No business policy hard-coded | Yes - any number that a client could change is a setting; code-level constants are limited to integrity/security properties (listed in section 2) |
| Edge cases handled | Yes - 90 explicit cases in section 5 |
| Ambiguity not invented | Yes - 25 client decisions plus 6 additional documented assumptions, all with provisional defaults and explicit `CLIENT_DECISION_REQUIRED` labeling |

Blocking items before production (must be confirmed by the client):
decisions 1, 2, 6, 7, 8, 13, 14, 15 and 24 have direct financial or legal impact and must be
confirmed before the first live payroll run.