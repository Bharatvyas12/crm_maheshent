# Workforce CRM — Domain Audit Report (Agent 4)

**Auditor:** Agent 4 — Domain Specialist  
**Audit Date:** October 2, 2026  
**Scope:** Verification of business domain logic against `docs/00_PRODUCT_SCOPE.md` to `docs/09_TEST_PLAN.md`.

---

## 1. Domain Module Audits

### 1.1 Attendance Module Audit
- **Check-in / Check-out Validation:** Verified. Enforces open/close transitions, prevents duplicate check-ins on active sessions, and validates maximum session durations.
- **Verification Modes (GPS / QR):** Backend validates dynamic shop QR nonces and geofence distance server-side. Coordinates and radius threshold are database-backed settings (`attendance.geofence_latitude`, `attendance.geofence_longitude`, `attendance.geofence_radius_meters`), avoiding hard-coded technical constants.
- **Field Work Exemption:** Verified. Leaving shop geofence for field delivery work does NOT invalidate active attendance. Verification occurs strictly during configured attendance check-in/check-out events.
- **Work-Hour & Overtime Calculation:** Computed server-side based on configurable daily hours (`attendance.required_daily_hours`), overtime grace periods, and break deductions.
- **Attendance Corrections:** Support for request-and-approve lifecycle for missing check-in/out with backdate limit controls (`attendance.correction_max_backdate_days`).

### 1.2 Task Management Module Audit
- **Lifecycle Flow:** Enforces state transition path: `ASSIGNED` → `STARTED` → `SUBMITTED` → `APPROVED` or `RESUBMISSION_REQUESTED`.
- **Evidence & Attachments:** Enforces required evidence uploads prior to submission. Attempt history and reviewer notes are preserved across resubmissions.

### 1.3 Order Broadcast & Claiming Module Audit
- **Concurrency & Claiming Integrity:** Atomic DB-level claim reservation using conditional `UPDATE` combined with active claim index logic. Prevents double-claiming under simultaneous requests.
- **Order Lifecycle:** Enforces `BROADCASTED` → `CLAIMED` → `PACKING` → `PACKED` → `READY_FOR_DELIVERY` → `OUT_FOR_DELIVERY` → `DELIVERED`.
- **Proof of Delivery (POD):** Mandates POD photo upload / customer confirmation when `orders.pod_required` setting is enabled.

### 1.4 Leaves Module Audit
- **Balance & Overlapping Controls:** Validates available entitlement balance and rejects overlapping date range applications (`LEAVE_OVERLAP`).
- **Backdate Policy:** Prevents backdated leave applications unless explicitly enabled by business configuration.

### 1.5 Financial Ledger & Payroll Module Audit
- **Append-Only Ledger:** `employee_ledger_entries` prevents direct hard deletion. Corrections require explicit reversal entries (`reverses_entry_id`) with immutable audit trails.
- **Payroll Lifecycle:** State progression `DRAFT` → `COMPUTED` → `FINALIZED` → `LOCKED` → `PAID`. Once a payroll run is locked, historical recalculation is strictly prohibited (`PeriodLocked`).
- **Rule Snapshotting:** `payroll_rule_snapshots` captures a JSONB snapshot and SHA-256 hash of all active rate/deduction business settings at computation time, ensuring historical payroll integrity.

### 1.6 Complaints Module Audit
- **Visibility & Status:** Implements `OPEN` → `IN_REVIEW` → `ACTION_REQUIRED` → `RESOLVED` / `CLOSED` / `REJECTED`. Enforces role-based visibility (`EMPLOYEE_PRIVATE` vs `ADMIN_ONLY`).

### 1.7 Reports Module Audit
- **Data Consistency:** Aggregated reports (R-01 through R-18) compute metrics directly from source tables (attendance records, salary records, order history) to avoid discrepancy.

---

## 2. Identified Findings & Classifications

| ID | Module | Scenario / Description | Severity | Recommended Action |
|---|---|---|---|---|
| DA-01 | Settings / Auth | `employee_payload` field key alignment for timezone/currency | **RESOLVED (MEDIUM)** | Mapped `business_timezone` and `currency` alongside dot-notation keys. |
| DA-02 | Payroll | `PayrollRuleSnapshot` scope check constraint mismatch | **RESOLVED (HIGH)** | Updated `ensure_rule_snapshot` scope from `'RUN'` to `'GLOBAL'`. |
| DA-03 | Business Config | 25 `CLIENT_DECISION_REQUIRED` items in `docs/04_BUSINESS_RULES.md` | **CLIENT_DECISION_REQUIRED** | Maintain database-backed defaults until client confirms final choices. |

---

## 3. Conclusion

The core business workflows comply with the source-of-truth requirements in `/docs`. All critical domain constraints (financial append-only ledger, atomic order claiming, attendance state machine) are authoritatively enforced on the backend.
