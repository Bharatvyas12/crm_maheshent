"""The business settings registry (docs/04_BUSINESS_RULES.md section 3).

Every configurable business value lives here: key, type, default, bounds and the
module that consumes it. Nothing outside this registry may invent a business
value, and no business value may be read from the environment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

VALUE_TYPES = frozenset(
    {"STRING", "INT", "DECIMAL", "BOOL", "JSON", "TIME", "TIMEZONE", "DURATION_SECONDS"}
)


@dataclass(frozen=True, slots=True)
class SettingDef:
    key: str
    value_type: str
    default: Any
    group: str
    description: str
    provisional: bool = False
    minimum: Any = None
    maximum: Any = None
    allowed: tuple[Any, ...] | None = None


def _d(*defs: SettingDef) -> list[SettingDef]:
    return list(defs)


SETTING_DEFINITIONS: list[SettingDef] = _d(
    SettingDef("org.name", "STRING", "Workforce CRM", "org", "Displayed business name"),
    SettingDef("org.timezone", "TIMEZONE", "Asia/Kolkata", "org", "Business timezone for all business dates", True),
    SettingDef("org.currency", "STRING", "INR", "org", "Default currency for money fields"),
    SettingDef("org.week_starts_on", "INT", 1, "org", "Report week grouping (0 = Sunday)", False, 0, 6),
    SettingDef("security.session_timeout_minutes", "INT", 720, "security", "Absolute session lifetime", False, 15, 43200),
    SettingDef("security.session_idle_timeout_minutes", "INT", 120, "security", "Idle session timeout", False, 5, 4320),
    SettingDef("security.password_reset_ttl_minutes", "INT", 120, "security", "Reset token validity", False, 5, 10080),
    SettingDef("security.max_failed_logins", "INT", 5, "security", "Failures before lockout", False, 1, 100),
    SettingDef("security.lockout_window_minutes", "INT", 15, "security", "Window in which failures are counted", False, 1, 1440),
    SettingDef("security.lockout_minutes", "INT", 15, "security", "Lockout duration", False, 1, 1440),
    SettingDef("security.password_min_length", "INT", 10, "security", "Password policy minimum length", False, 8, 128),
    SettingDef("security.password_require_complexity", "BOOL", True, "security", "Password policy complexity"),
    SettingDef("security.rate_limit.login_per_minute", "INT", 10, "security", "Login throttle per identity/IP", False, 1, 1000),
    SettingDef("security.rate_limit.checkin_per_minute", "INT", 12, "security", "Attendance event throttle", False, 1, 1000),
    SettingDef("security.rate_limit.upload_per_minute", "INT", 20, "security", "Upload throttle per user", False, 1, 1000),
    SettingDef("security.rate_limit.report_per_minute", "INT", 5, "security", "Export throttle per user", False, 1, 1000),
    SettingDef("security.rate_limit.qr_issue_per_minute", "INT", 6, "security", "QR issuance throttle", False, 1, 1000),
    SettingDef("attendance.verification_mode", "STRING", "GPS_OR_QR", "attendance", "Required check-in evidence", True, None, None, ("GPS_AND_QR", "GPS_OR_QR", "GPS_ONLY", "QR_ONLY")),
    SettingDef("attendance.checkout_verification_mode", "STRING", "SAME_AS_CHECKIN", "attendance", "Check-out evidence requirement", True, None, None, ("SAME_AS_CHECKIN", "NONE", "GPS_ONLY", "QR_ONLY")),
    SettingDef("attendance.geofence_latitude", "DECIMAL", None, "attendance", "Shop latitude (unset until the client confirms)", True, -90, 90),
    SettingDef("attendance.geofence_longitude", "DECIMAL", None, "attendance", "Shop longitude (unset until the client confirms)", True, -180, 180),
    SettingDef("attendance.geofence_radius_m", "DECIMAL", "100.00", "attendance", "Permitted distance from the shop", True, 1, 10000),
    SettingDef("attendance.gps_accuracy_max_m", "DECIMAL", "100.00", "attendance", "Maximum accepted GPS accuracy radius", True, 1, 5000),
    SettingDef("attendance.location_max_age_seconds", "INT", 60, "attendance", "Freshness required for a client location fix", False, 1, 900),
    SettingDef("attendance.qr_validity_seconds", "INT", 60, "attendance", "Dynamic QR validity window", True, 10, 3600),
    SettingDef("attendance.qr_rotation_seconds", "INT", 45, "attendance", "Shop display rotation interval", True, 5, 3600),
    SettingDef("attendance.qr_single_use", "BOOL", True, "attendance", "Reject a QR token already consumed", True),
    SettingDef("attendance.shift_tracking_enabled", "BOOL", True, "attendance", "Enables late/early computation"),
    SettingDef("attendance.shift_start_time", "TIME", "09:00", "attendance", "Nominal shift start"),
    SettingDef("attendance.shift_end_time", "TIME", "19:00", "attendance", "Nominal shift end"),
    SettingDef("attendance.shift_crosses_midnight", "BOOL", False, "attendance", "Shift belongs to the starting business date"),
    SettingDef("attendance.required_daily_hours", "DECIMAL", "10.00", "attendance", "Expected active hours per day", True, 1, 24),
    SettingDef("attendance.full_day_min_hours", "DECIMAL", "10.00", "attendance", "Worked hours for FULL_DAY", True, 0.5, 24),
    SettingDef("attendance.half_day_min_hours", "DECIMAL", "5.00", "attendance", "Worked hours for HALF_DAY", True, 0.5, 24),
    SettingDef("attendance.partial_day_min_hours", "DECIMAL", "0.50", "attendance", "Minimum hours to count as PARTIAL_DAY", True, 0.01, 24),
    SettingDef("attendance.allow_multiple_sessions_per_day", "BOOL", True, "attendance", "Multiple in/out cycles allowed"),
    SettingDef("attendance.max_sessions_per_day", "INT", 6, "attendance", "Abuse guard", False, 1, 50),
    SettingDef("attendance.overtime_enabled", "BOOL", True, "attendance", "Overtime is tracked", True),
    SettingDef("attendance.overtime_threshold_hours", "DECIMAL", "10.00", "attendance", "Hours after which overtime accrues", True, 1, 24),
    SettingDef("attendance.overtime_min_minutes", "INT", 30, "attendance", "Minimum overtime increment", True, 0, 240),
    SettingDef("attendance.overtime_cap_hours_per_day", "DECIMAL", "4.00", "attendance", "Maximum overtime per day", True, 0, 12),
    SettingDef("attendance.late_grace_minutes", "INT", 10, "attendance", "Grace before counting late", True, 0, 240),
    SettingDef("attendance.early_checkout_grace_minutes", "INT", 10, "attendance", "Grace before counting early checkout", True, 0, 240),
    SettingDef("attendance.break_tracking_enabled", "BOOL", True, "attendance", "Employees record breaks", True),
    SettingDef("attendance.auto_break_deduction_minutes", "INT", 60, "attendance", "Fixed daily break deduction when tracking is off", True, 0, 480),
    SettingDef("attendance.break_max_minutes_per_day", "INT", 90, "attendance", "Total break cap for the day", False, 0, 720),
    SettingDef("attendance.missing_checkout_policy", "STRING", "REQUIRE_CORRECTION", "attendance", "Handling for an unclosed session", True, None, None, ("REQUIRE_CORRECTION", "AUTO_CLOSE_AT_SHIFT_END", "AUTO_CLOSE_WITH_MAX", "MARK_INCOMPLETE")),
    SettingDef("attendance.auto_close_grace_minutes", "INT", 60, "attendance", "Grace after shift end before auto-close", False, 0, 1440),
    SettingDef("attendance.auto_close_max_hours", "DECIMAL", "10.00", "attendance", "Cap used by AUTO_CLOSE_WITH_MAX", False, 0.5, 24),
    SettingDef("attendance.field_work_allowed", "BOOL", True, "attendance", "Employees may leave the shop after valid attendance", True),
    SettingDef("attendance.correction_requires_approval", "BOOL", True, "attendance", "Corrections need admin approval"),
    SettingDef("attendance.correction_max_backdate_days", "INT", 7, "attendance", "How far back a correction may reach", True, 0, 365),
    SettingDef("attendance.recompute_open_records", "BOOL", True, "attendance", "Sweep job recomputes open records"),
    SettingDef("tasks.require_evidence_on_submit", "BOOL", True, "tasks", "A submission must include evidence"),
    SettingDef("tasks.attachment_mode", "STRING", "OPTIONAL", "tasks", "Attachment requirement", False, None, None, ("NEVER", "ALWAYS", "OPTIONAL")),
    SettingDef("tasks.max_attachments_per_submission", "INT", 5, "tasks", "Evidence limit", False, 0, 20),
    SettingDef("tasks.reminder_hours_before_due", "INT", 24, "tasks", "Due reminder lead time", False, 1, 336),
    SettingDef("tasks.overdue_escalation_enabled", "BOOL", False, "tasks", "Escalate overdue tasks to Admin"),
    SettingDef("tasks.allow_multiple_assignees", "BOOL", True, "tasks", "A task may be assigned to several employees"),
    SettingDef("tasks.allow_self_review", "BOOL", False, "tasks", "Must remain false (segregation of duties)"),
    SettingDef("tasks.reopen_on_rejection", "BOOL", False, "tasks", "A rejected assignment may be reopened"),
    SettingDef("orders.broadcast_audience", "STRING", "ALL_ACTIVE_EMPLOYEES", "orders", "Default broadcast audience", False, None, None, ("ALL_ACTIVE_EMPLOYEES", "ROLE")),
    SettingDef("orders.claim_timeout_minutes", "INT", 30, "orders", "Claim validity before automatic release", True, 1, 1440),
    SettingDef("orders.auto_release_on_timeout", "BOOL", True, "orders", "Sweeper releases expired claims", True),
    SettingDef("orders.claim_requires_active_attendance", "BOOL", False, "orders", "Only checked-in employees may claim", True),
    SettingDef("orders.max_active_claims_per_employee", "INT", 3, "orders", "Concurrency guard per employee", False, 1, 50),
    SettingDef("orders.allow_rebroadcast_after_release", "BOOL", True, "orders", "Released order returns to the pool"),
    SettingDef("orders.reassignment_requires_reason", "BOOL", True, "orders", "Reassignment needs a reason"),
    SettingDef("orders.reassign_permission", "STRING", "ADMIN_ONLY", "orders", "Who may reassign", True, None, None, ("ADMIN_ONLY", "ADMIN_AND_SELF")),
    SettingDef("orders.max_reassignments", "INT", 5, "orders", "Abuse guard", False, 0, 50),
    SettingDef("orders.cancel_allowed_statuses", "JSON", ["BROADCASTED", "CLAIMED", "PACKING", "PACKED", "READY_FOR_DELIVERY"], "orders", "Cancellable states", True),
    SettingDef("orders.allow_status_skip", "BOOL", False, "orders", "Skip lifecycle states", True),
    SettingDef("orders.pod_required", "BOOL", True, "orders", "Proof of delivery required", True),
    SettingDef("orders.pod_requires_photo", "BOOL", True, "orders", "Photo proof required", True),
    SettingDef("orders.pod_requires_customer_confirmation", "BOOL", False, "orders", "Customer confirmation required", True),
    SettingDef("orders.pod_requires_location", "BOOL", False, "orders", "Location evidence required", True),
    SettingDef("orders.packing_proof_required", "BOOL", False, "orders", "Packing photo required before PACKED"),
    SettingDef("orders.failure_requires_reason", "BOOL", True, "orders", "Failure must be explained"),
    SettingDef("leaves.enabled", "BOOL", True, "leaves", "Leave module availability"),
    SettingDef("leaves.enforce_overlap", "BOOL", True, "leaves", "Overlapping requests rejected", True),
    SettingDef("leaves.allow_half_day", "BOOL", False, "leaves", "Half-day leave allowed", True),
    SettingDef("leaves.max_advance_days", "INT", 60, "leaves", "How early leave may be requested", True, 0, 730),
    SettingDef("leaves.max_backdate_days", "INT", 0, "leaves", "Backdated applications allowed", False, 0, 365),
    SettingDef("leaves.requires_attachment_after_days", "INT", 3, "leaves", "Attachment required beyond this length", True, 0, 365),
    SettingDef("leaves.accrual_mode", "STRING", "MANUAL", "leaves", "How entitlement accrues", True, None, None, ("ANNUAL_UPFRONT", "MONTHLY_ACCRUAL", "MANUAL")),
    SettingDef("leaves.accrual_day_of_month", "INT", 1, "leaves", "Monthly accrual day", False, 1, 28),
    SettingDef("leaves.carry_forward_enabled", "BOOL", False, "leaves", "Unused leave carries forward", True),
    SettingDef("leaves.carry_forward_max_days", "DECIMAL", "0.00", "leaves", "Carry-forward cap", True, 0, 365),
    SettingDef("leaves.balance_reset_month", "INT", 1, "leaves", "Leave-year start month", True, 1, 12),
    SettingDef("leaves.allow_negative_balance", "BOOL", False, "leaves", "Negative balance permitted"),
    SettingDef("leaves.allow_admin_self_approval", "BOOL", False, "leaves", "Admin approving own leave"),
    SettingDef("leaves.weekend_counts_as_leave", "BOOL", False, "leaves", "Weekly offs consume leave days", True),
    SettingDef("payroll.enabled", "BOOL", True, "payroll", "Payroll module availability"),
    SettingDef("payroll.basis", "STRING", "FIXED_MONTHLY", "payroll", "Default pay basis", True, None, None, ("FIXED_MONTHLY", "DAILY_WAGE", "HOURLY")),
    SettingDef("payroll.working_days_basis", "STRING", "WEEKLY_OFF", "payroll", "How payable days are denominated", True, None, None, ("CALENDAR", "WEEKLY_OFF", "BUSINESS_CALENDAR")),
    SettingDef("payroll.weekly_off_days", "JSON", [0], "payroll", "Weekly off day numbers", True),
    SettingDef("payroll.payable_day_basis", "STRING", "ATTENDANCE_DERIVED", "payroll", "Payable day denominator", True, None, None, ("ATTENDANCE_DERIVED", "FIXED_DAYS_IN_MONTH")),
    SettingDef("payroll.fixed_days_in_month", "INT", 30, "payroll", "Denominator for FIXED_DAYS_IN_MONTH", True, 1, 31),
    SettingDef("payroll.rounding_mode", "STRING", "HALF_UP", "payroll", "Money rounding mode", True, None, None, ("HALF_UP", "HALF_EVEN", "FLOOR")),
    SettingDef("payroll.overtime_enabled", "BOOL", True, "payroll", "Overtime is paid", True),
    SettingDef("payroll.overtime_rate_multiplier", "DECIMAL", "1.50", "payroll", "Overtime pay multiplier", True, 1, 5),
    SettingDef("payroll.partial_day_pay_fraction_mode", "STRING", "PRO_RATA_HOURS", "payroll", "How partial days are paid", True, None, None, ("PRO_RATA_HOURS", "FIXED_FRACTION", "NO_PAY")),
    SettingDef("payroll.partial_day_fixed_fraction", "DECIMAL", "0.50", "payroll", "Used by FIXED_FRACTION", True, 0, 1),
    SettingDef("payroll.paid_leave_counts_as_payable", "BOOL", True, "payroll", "Paid leave days are payable", True),
    SettingDef("payroll.holiday_pay_enabled", "BOOL", True, "payroll", "Paid holidays are payable", True),
    SettingDef("payroll.weekly_off_pay_enabled", "BOOL", True, "payroll", "Weekly offs are payable", True),
    SettingDef("payroll.unpaid_leave_deduction_enabled", "BOOL", True, "payroll", "Unpaid leave reduces pay", True),
    SettingDef("payroll.late_deduction_enabled", "BOOL", False, "payroll", "Late arrivals reduce pay", True),
    SettingDef("payroll.late_deduction_per_occurrence", "DECIMAL", "0.00", "payroll", "Late deduction amount", True, 0, 10000000),
    SettingDef("payroll.late_deduction_after_minutes", "INT", 30, "payroll", "Minutes after which a late deduction applies", True, 0, 1440),
    SettingDef("payroll.payroll_lock_day_of_month", "INT", 5, "payroll", "Day the previous period locks", True, 1, 28),
    SettingDef("payroll.require_finalize_before_pay", "BOOL", True, "payroll", "Integrity guard"),
    SettingDef("payroll.require_attendance_corrections_resolved", "BOOL", True, "payroll", "Block finalize while corrections are pending", True),
    SettingDef("advance.enabled", "BOOL", True, "payroll", "Advance module availability"),
    SettingDef("advance.requires_approval", "BOOL", True, "payroll", "Advances need approval", True),
    SettingDef("advance.max_outstanding_percent_of_salary", "DECIMAL", "50.00", "payroll", "Outstanding cap relative to monthly pay", True, 0, 100),
    SettingDef("advance.max_percent_recovered_per_month", "DECIMAL", "25.00", "payroll", "Monthly recovery cap", True, 0, 100),
    SettingDef("advance.min_installment_amount", "DECIMAL", "500.00", "payroll", "Minimum installment", True, 0, 10000000),
    SettingDef("advance.max_installment_count", "INT", 12, "payroll", "Installment count cap", False, 1, 120),
    SettingDef("advance.allow_cash_repayment", "BOOL", True, "payroll", "Cash repayment outside payroll"),
    SettingDef("ledger.allow_manual_entries", "BOOL", True, "payroll", "Manual ledger adjustments allowed"),
    SettingDef("ledger.require_reason", "BOOL", True, "payroll", "Every financial entry needs a reason"),
    SettingDef("complaints.enabled", "BOOL", True, "complaints", "Complaint module availability"),
    SettingDef("complaints.allow_anonymous", "BOOL", False, "complaints", "Anonymous complaints", True),
    SettingDef("complaints.employee_visibility", "STRING", "OWN_ONLY", "complaints", "What employees may see", True, None, None, ("OWN_ONLY", "ALL_NON_INTERNAL")),
    SettingDef("complaints.default_priority", "STRING", "NORMAL", "complaints", "Default priority", False, None, None, ("LOW", "NORMAL", "HIGH", "URGENT")),
    SettingDef("complaints.default_visibility", "STRING", "EMPLOYEE_PRIVATE", "complaints", "Default visibility", True, None, None, ("EMPLOYEE_PRIVATE", "ADMIN_ONLY", "INTERNAL_TEAM")),
    SettingDef("complaints.sla_hours", "INT", 72, "complaints", "Resolution SLA for sla_due_at", True, 1, 8760),
    SettingDef("complaints.employee_can_comment_after_close", "BOOL", False, "complaints", "Post-closure commenting"),
    SettingDef("complaints.employee_may_reference_employee", "BOOL", False, "complaints", "Employees may name a subject employee", True),
    SettingDef("notifications.channels_enabled", "JSON", ["IN_APP", "WEB_PUSH"], "notifications", "Enabled delivery channels", True),
    SettingDef("notifications.web_push_enabled", "BOOL", True, "notifications", "Browser push", True),
    SettingDef("notifications.quiet_hours_enabled", "BOOL", False, "notifications", "Suppress non-critical pushes at night"),
    SettingDef("notifications.quiet_hours_start", "TIME", "21:00", "notifications", "Quiet hours start"),
    SettingDef("notifications.quiet_hours_end", "TIME", "08:00", "notifications", "Quiet hours end"),
    SettingDef("notifications.max_delivery_attempts", "INT", 5, "notifications", "Retry limit", False, 1, 20),
    SettingDef("notifications.retention_days", "INT", 180, "notifications", "In-app notification retention", False, 7, 3650),
    SettingDef("notifications.task_reminder_enabled", "BOOL", True, "notifications", "Task reminder notifications"),
    SettingDef("notifications.order_broadcast_enabled", "BOOL", True, "notifications", "Broadcast notifications"),
    SettingDef("notifications.daily_summary_enabled", "BOOL", False, "notifications", "Daily summary notification"),
    SettingDef("files.max_upload_mb", "INT", 10, "files", "Upload size limit", False, 1, 100),
    SettingDef("files.allowed_mime_types", "JSON", ["image/jpeg", "image/png", "image/webp", "application/pdf"], "files", "Upload allow-list"),
    SettingDef("files.presigned_url_ttl_seconds", "INT", 300, "files", "Download URL validity", False, 30, 3600),
    SettingDef("files.export_retention_days", "INT", 7, "files", "Generated export retention", False, 1, 365),
    SettingDef("files.max_attachments_per_entity", "INT", 10, "files", "Attachment cap per record", False, 1, 100),
    SettingDef("files.virus_scan_enabled", "BOOL", False, "files", "Scanning integration switch"),
    SettingDef("reports.max_range_days", "INT", 366, "reports", "Maximum report range", False, 1, 3650),
    SettingDef("reports.export_formats", "JSON", ["CSV", "XLSX"], "reports", "Offered formats", True),
    SettingDef("reports.default_page_size", "INT", 50, "reports", "Report page size", False, 10, 200),
    SettingDef("reports.include_sensitive_fields", "BOOL", False, "reports", "Include sensitive employee fields in reports"),
    SettingDef("reports.grouping_timezone", "STRING", "BUSINESS", "reports", "Grouping timezone for reports", False, None, None, ("BUSINESS", "UTC")),
    SettingDef("audit.retention_days", "INT", 2555, "audit", "Audit retention", True, 30, 18250),
    SettingDef("audit.log_reads", "BOOL", False, "audit", "Audit read access as well as writes"),
    SettingDef("data.retention_days", "INT", 2555, "data", "General data retention", True, 30, 18250),
    SettingDef("platform.idempotency_ttl_hours", "INT", 24, "platform", "Idempotency key retention", False, 1, 720),
    SettingDef("platform.outbox_batch_size", "INT", 100, "platform", "Outbox dispatch batch size", False, 1, 1000),
    SettingDef("platform.job_batch_size", "INT", 500, "platform", "Job processing batch size", False, 1, 5000),
)

SETTINGS_BY_KEY: dict[str, SettingDef] = {definition.key: definition for definition in SETTING_DEFINITIONS}

assert len(SETTINGS_BY_KEY) == len(SETTING_DEFINITIONS), "duplicate setting key in registry"