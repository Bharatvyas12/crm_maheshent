/**
 * Core API types. Field names/semantics follow docs/03_API_CONTRACT.md section 3
 * and docs/01_ARCHITECTURE.md section 13 (snake_case, RFC 3339 UTC, decimal-string money,
 * integer-second durations with a convenience decimal-hour string).
 */

export type Uuid = string;
/** Business date, `YYYY-MM-DD`, interpreted in the business timezone. */
export type BusinessDate = string;
/** RFC 3339 timestamp in UTC. */
export type Timestamp = string;
/** Money serialized as a decimal string with two decimals, e.g. "1500.00". */
export type Money = string;

export interface Paginated<T> {
  items: T[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

/**
 * A non-paginated collection. docs/01_ARCHITECTURE.md section 13.2 requires every collection
 * response to be an object carrying an `items` array, so reference-data lookups (break types,
 * leave types, complaint categories, permission catalog, ...) use this shape rather than a bare
 * array. `total` is present on some lookups (for example the permission and report catalogs).
 */
export interface ListResponse<T> {
  items: T[];
  total?: number;
}

export interface CursorPage<T> {
  items: T[];
  next_cursor: string | null;
}

/** RFC 9457 problem details body (docs/01_ARCHITECTURE.md section 13.3). */
export interface ProblemDetails {
  type?: string;
  title?: string;
  status?: number;
  code?: string;
  detail?: string;
  instance?: string;
  request_id?: string;
  rule_code?: string;
  errors?: Array<{ field: string; code: string; message: string }>;
  /** Present on CLAIM_ALREADY_TAKEN so the UI can show who/when (docs/03 section 9.2). */
  current_status?: string;
  claimed_at?: Timestamp;
  claimed_by?: { employee_id?: Uuid; full_name?: string } | null;
  retry_after_seconds?: number;
}

// ---------------------------------------------------------------------------
// Identity
// ---------------------------------------------------------------------------

export type UserStatus = 'ACTIVE' | 'DISABLED' | 'LOCKED';

export interface RoleRef {
  id: Uuid;
  code: string;
  name: string;
}

export interface User {
  id: Uuid;
  username: string;
  email: string | null;
  status: UserStatus;
  last_login_at: Timestamp | null;
  must_change_password: boolean;
  roles: RoleRef[];
  created_at: Timestamp;
}

export type EmploymentStatus = 'ACTIVE' | 'INACTIVE' | 'EXITED';
export type EmploymentType = 'FULL_TIME' | 'PART_TIME' | 'CONTRACT' | 'INTERN';

export interface EmployeeSensitive {
  bank_account_name: string | null;
  bank_account_number_masked: string | null;
  bank_ifsc: string | null;
}

export interface Employee {
  id: Uuid;
  user_id: Uuid;
  employee_code: string;
  full_name: string;
  phone: string | null;
  email: string | null;
  date_of_joining: BusinessDate;
  date_of_exit: BusinessDate | null;
  employment_status: EmploymentStatus;
  employment_type: EmploymentType;
  department: string | null;
  designation: string | null;
  manager_employee_id: Uuid | null;
  emergency_contact_name: string | null;
  emergency_contact_phone: string | null;
  address_line: string | null;
  created_at: Timestamp;
  updated_at: Timestamp;
  /** Present only with `employee.read.sensitive`. */
  sensitive?: EmployeeSensitive;
}

/** Payload returned by /auth/login, /auth/me and /me bootstrap. */
export interface SessionPayload {
  user: User;
  employee: Employee | null;
  roles: string[];
  permissions: string[];
  settings: SessionSettings;
}

/** Employee-relevant, non-sensitive settings slice (docs/03 section 2 notes). */
export interface SessionSettings {
  business_timezone: string;
  currency: string;
  break_types_enabled?: boolean;
  attendance_verification_mode?: AttendanceVerificationMode;
  attendance_checkout_verification_mode?: AttendanceVerificationMode;
  attendance_thresholds?: Record<string, unknown>;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Attendance
// ---------------------------------------------------------------------------

export type AttendanceStatus =
  | 'NOT_MARKED'
  | 'PRESENT'
  | 'INCOMPLETE'
  | 'ABSENT'
  | 'ON_LEAVE'
  | 'HOLIDAY'
  | 'WEEKLY_OFF';

export type DayClassification = 'FULL_DAY' | 'HALF_DAY' | 'PARTIAL_DAY' | 'NONE';

export type AttendanceAction =
  | 'CHECK_IN'
  | 'CHECK_OUT'
  | 'START_BREAK'
  | 'END_BREAK'
  | 'REQUEST_CORRECTION';

export type AttendanceVerificationMode = 'GPS' | 'QR' | 'GPS_AND_QR' | 'GPS_OR_QR' | 'NONE';

export interface AttendanceRecord {
  id: Uuid;
  employee_id: Uuid;
  employee?: Pick<Employee, 'id' | 'employee_code' | 'full_name'> | null;
  business_date: BusinessDate;
  status: AttendanceStatus;
  day_classification: DayClassification;
  first_check_in_at: Timestamp | null;
  last_check_out_at: Timestamp | null;
  worked_seconds: number;
  worked_hours: string;
  break_seconds: number;
  unpaid_break_seconds: number;
  overtime_seconds: number;
  overtime_hours?: string;
  late_minutes: number;
  early_checkout_minutes: number;
  is_open: boolean;
  is_corrected: boolean;
  computed_at: Timestamp | null;
  version: number;
  next_allowed_action?: AttendanceAction | null;
  allowed_transitions?: AttendanceAction[];
  /** Verification requirements resolved server-side, never guessed by the client. */
  required_evidence?: AttendanceEvidenceRequirement;
  open_break?: BreakSession | null;
  anomalies?: string[];
}

export interface AttendanceEvidenceRequirement {
  mode: AttendanceVerificationMode;
  location_required: boolean;
  qr_required: boolean;
}

export interface AttendanceEvent {
  id: Uuid;
  attendance_record_id: Uuid;
  event_type: string;
  occurred_at: Timestamp;
  source: string;
  session_id: Uuid | null;
  break_session_id: Uuid | null;
  correction_id: Uuid | null;
  is_manual: boolean;
  note: string | null;
}

export interface AttendanceVerification {
  id: Uuid;
  attendance_record_id: Uuid;
  event_id: Uuid | null;
  method: string;
  result: string;
  distance_meters: number | null;
  accuracy_meters: number | null;
  geofence_radius_meters: number | null;
  qr_result: string | null;
  failure_code: string | null;
  failure_reason: string | null;
  captured_at: Timestamp;
}

/** The server's evaluation summary returned with check-in/check-out. */
export interface VerificationResult {
  method: string;
  result: string;
  distance_meters: number | null;
  accuracy_meters: number | null;
  geofence_radius_meters: number | null;
  qr_result: string | null;
  failure_code: string | null;
  failure_reason: string | null;
}

export interface BreakType {
  id: Uuid;
  code: string;
  name: string;
  is_paid: boolean;
  max_minutes: number | null;
  requires_approval: boolean;
  counts_toward_max_per_day: boolean;
  is_active: boolean;
}

export interface BreakSession {
  id: Uuid;
  attendance_record_id: Uuid;
  break_type_id: Uuid;
  break_type?: BreakType;
  started_at: Timestamp;
  ended_at: Timestamp | null;
  duration_seconds: number | null;
  is_paid: boolean;
  close_reason: string | null;
}

export interface Holiday {
  id: Uuid;
  holiday_date: BusinessDate;
  name: string;
  is_paid: boolean;
  is_working_day: boolean;
}

export type CorrectionStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED';
export type CorrectionType =
  | 'CHECK_IN_TIME'
  | 'CHECK_OUT_TIME'
  | 'BREAK_TIME'
  | 'MISSING_CHECK_IN'
  | 'MISSING_CHECK_OUT'
  | 'FULL_DAY';

export interface AttendanceCorrection {
  id: Uuid;
  attendance_record_id: Uuid;
  employee_id: Uuid;
  employee?: Pick<Employee, 'id' | 'employee_code' | 'full_name'> | null;
  correction_type: CorrectionType;
  requested_check_in_at: Timestamp | null;
  requested_check_out_at: Timestamp | null;
  requested_break_start_at: Timestamp | null;
  requested_break_end_at: Timestamp | null;
  reason: string;
  attachment_file_id: Uuid | null;
  status: CorrectionStatus;
  decided_by_user_id: Uuid | null;
  decided_at: Timestamp | null;
  decision_notes: string | null;
  created_at: Timestamp;
  record?: AttendanceRecord | null;
}

export interface QrToken {
  id: Uuid;
  qr_payload: string;
  nonce: string;
  expires_at: Timestamp;
  rotation_seconds: number;
  purpose?: string;
}

// ---------------------------------------------------------------------------
// Tasks
// ---------------------------------------------------------------------------

export type TaskStatus = 'OPEN' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED';
export type TaskPriority = 'LOW' | 'NORMAL' | 'HIGH' | 'URGENT';
export type AssignmentStatus =
  | 'ASSIGNED'
  | 'STARTED'
  | 'COMPLETED'
  | 'SUBMITTED'
  | 'RESUBMISSION_REQUESTED'
  | 'APPROVED'
  | 'REJECTED'
  | 'CANCELLED';

export interface TaskAttachment {
  id: Uuid;
  file_id: Uuid;
  attachment_type: string;
  file?: FileMeta | null;
}

export interface Task {
  id: Uuid;
  title: string;
  description: string | null;
  priority: TaskPriority;
  status: TaskStatus;
  due_at: Timestamp | null;
  requires_evidence: boolean;
  requires_attachment: boolean;
  created_by_user_id: Uuid;
  created_at: Timestamp;
  attachments?: TaskAttachment[];
  assignments?: TaskAssignment[];
  assignment_count?: number;
}

export interface TaskAssignment {
  id: Uuid;
  task_id: Uuid;
  task?: Task | null;
  employee_id: Uuid;
  employee?: Pick<Employee, 'id' | 'employee_code' | 'full_name'> | null;
  status: AssignmentStatus;
  assigned_at: Timestamp;
  started_at: Timestamp | null;
  completed_at: Timestamp | null;
  submitted_at: Timestamp | null;
  reviewed_at: Timestamp | null;
  reviewer_id: Uuid | null;
  review_decision: string | null;
  review_notes: string | null;
  attempt_count: number;
  due_at: Timestamp | null;
  version: number;
  allowed_transitions: string[];
  submissions?: TaskSubmission[];
  comments?: TaskComment[];
}

export interface TaskSubmission {
  id: Uuid;
  assignment_id: Uuid;
  attempt_no: number;
  description: string | null;
  status: string;
  submitted_at: Timestamp;
  reviewed_at: Timestamp | null;
  reviewer_id: Uuid | null;
  review_notes: string | null;
  attachments?: Array<{ id: Uuid; file_id: Uuid; file?: FileMeta | null }>;
}

export interface TaskComment {
  id: Uuid;
  task_id: Uuid;
  assignment_id: Uuid | null;
  author_user_id: Uuid;
  author?: { id: Uuid; username: string } | null;
  body: string;
  is_internal: boolean;
  created_at: Timestamp;
}

// ---------------------------------------------------------------------------
// Orders
// ---------------------------------------------------------------------------

export type OrderStatus =
  | 'DRAFT'
  | 'BROADCASTED'
  | 'CLAIMED'
  | 'PACKING'
  | 'PACKED'
  | 'READY_FOR_DELIVERY'
  | 'OUT_FOR_DELIVERY'
  | 'DELIVERED'
  | 'CANCELLED'
  | 'FAILED'
  | 'REASSIGNED';

export interface OrderBroadcast {
  id: Uuid;
  order_id: Uuid;
  round_no: number;
  audience_scope: string;
  audience_payload?: Record<string, unknown> | null;
  broadcast_at: Timestamp;
  expires_at: Timestamp | null;
  is_active: boolean;
}

export interface OrderClaim {
  id: Uuid;
  order_id: Uuid;
  employee_id: Uuid;
  employee?: Pick<Employee, 'id' | 'employee_code' | 'full_name'> | null;
  claimed_at: Timestamp;
  claim_expires_at: Timestamp | null;
  released_at: Timestamp | null;
  release_reason: string | null;
  status: 'ACTIVE' | 'COMPLETED' | 'RELEASED' | 'EXPIRED';
}

export interface Order {
  id: Uuid;
  order_code: string;
  customer_name: string;
  customer_phone: string | null;
  delivery_address: string | null;
  delivery_notes: string | null;
  item_summary: string | null;
  item_count: number | null;
  order_amount: Money;
  currency: string;
  payment_mode: string | null;
  notes: string | null;
  status: OrderStatus;
  current_assignee_id: Uuid | null;
  current_assignee?: Pick<Employee, 'id' | 'employee_code' | 'full_name'> | null;
  broadcast_at: Timestamp | null;
  claimed_at: Timestamp | null;
  claim_expires_at: Timestamp | null;
  delivered_at: Timestamp | null;
  cancelled_at: Timestamp | null;
  created_at: Timestamp;
  version: number;
  allowed_transitions: string[];
  attachments?: OrderAttachment[];
  history?: OrderHistoryEntry[];
  active_claim?: OrderClaim | null;
}

export interface OrderAttachment {
  id: Uuid;
  order_id: Uuid;
  file_id: Uuid;
  purpose: string;
  note: string | null;
  latitude: number | null;
  longitude: number | null;
  accuracy_meters: number | null;
  customer_confirmed: boolean | null;
  customer_confirmation_method: string | null;
  created_at: Timestamp;
  file?: FileMeta | null;
}

export interface OrderHistoryEntry {
  id: Uuid;
  order_id: Uuid;
  from_status: OrderStatus | null;
  to_status: OrderStatus;
  actor_user_id: Uuid | null;
  employee_id: Uuid | null;
  reason: string | null;
  note: string | null;
  created_at: Timestamp;
}

// ---------------------------------------------------------------------------
// Leave
// ---------------------------------------------------------------------------

export interface LeaveType {
  id: Uuid;
  code: string;
  name: string;
  is_paid: boolean;
  requires_approval: boolean;
  requires_attachment_after_days: number | null;
  max_consecutive_days: number | null;
  allow_half_day: boolean;
  annual_entitlement_days: string | null;
  accrual_mode: string | null;
  is_active: boolean;
}

export type LeaveStatus =
  | 'PENDING'
  | 'APPROVED'
  | 'REJECTED'
  | 'MODIFICATION_REQUESTED'
  | 'CANCELLED';

export interface Leave {
  id: Uuid;
  employee_id: Uuid;
  employee?: Pick<Employee, 'id' | 'employee_code' | 'full_name'> | null;
  leave_type_id: Uuid;
  leave_type?: LeaveType | null;
  start_date: BusinessDate;
  end_date: BusinessDate;
  is_half_day: boolean;
  half_day_period: string | null;
  total_days: string;
  reason: string;
  attachment_file_id: Uuid | null;
  status: LeaveStatus;
  decided_by_user_id: Uuid | null;
  decided_at: Timestamp | null;
  decision_notes: string | null;
  created_at: Timestamp;
  allowed_transitions: string[];
  balance_effect?: Record<string, unknown> | null;
}

export interface LeaveBalance {
  id: Uuid;
  employee_id: Uuid;
  leave_type_id: Uuid;
  leave_type?: LeaveType | null;
  period_year: number;
  entitled_days: string;
  accrued_days: string;
  used_days: string;
  pending_days: string;
  carried_forward_days: string;
  adjustment_days: string;
  available_days: string;
}

export interface LeaveBalanceMovement {
  id: Uuid;
  leave_balance_id: Uuid;
  movement_type: string;
  days: string;
  reason: string | null;
  reference_type: string | null;
  reference_id: Uuid | null;
  created_at: Timestamp;
}

// ---------------------------------------------------------------------------
// Ledger / advances / payroll
// ---------------------------------------------------------------------------

export type LedgerDirection = 'CREDIT' | 'DEBIT';

export interface LedgerEntry {
  id: Uuid;
  employee_id: Uuid;
  employee?: Pick<Employee, 'id' | 'employee_code' | 'full_name'> | null;
  entry_type: string;
  direction: LedgerDirection;
  amount: Money;
  currency: string;
  business_date: BusinessDate;
  period_year: number | null;
  period_month: number | null;
  reason: string;
  reference_type: string | null;
  reference_id: Uuid | null;
  reversal_of_id: Uuid | null;
  is_reversed: boolean;
  created_by_user_id: Uuid | null;
  created_at: Timestamp;
}

export interface LedgerSummary {
  credit_total: Money;
  debit_total: Money;
  net: Money;
  as_of?: Timestamp;
}

export interface Advance {
  id: Uuid;
  employee_id: Uuid;
  employee?: Pick<Employee, 'id' | 'employee_code' | 'full_name'> | null;
  amount: Money;
  currency: string;
  issued_on: BusinessDate;
  reason: string;
  repayment_mode: string;
  installment_count: number | null;
  installment_amount: Money | null;
  outstanding_amount: Money;
  status: string;
  approved_by_user_id: Uuid | null;
  approved_at: Timestamp | null;
  created_at: Timestamp;
  installments?: AdvanceInstallment[];
}

export interface AdvanceInstallment {
  id: Uuid;
  advance_id: Uuid;
  installment_no: number;
  due_on: BusinessDate;
  amount: Money;
  paid_amount: Money;
  status: string;
}

export interface SalaryRecord {
  id: Uuid;
  payroll_run_id: Uuid;
  employee_id: Uuid;
  employee?: Pick<Employee, 'id' | 'employee_code' | 'full_name'> | null;
  period_year: number;
  period_month: number;
  currency: string;
  compensation_type: string;
  base_rate: Money;
  payable_days: string;
  gross_amount: Money;
  overtime_amount: Money;
  bonus_amount: Money;
  leave_deduction: Money;
  late_deduction: Money;
  advance_deduction: Money;
  other_deduction: Money;
  total_deductions: Money;
  net_amount: Money;
  status: string;
  rule_snapshot_hash: string;
  computed_at: Timestamp | null;
  finalized_at: Timestamp | null;
  paid_at: Timestamp | null;
  version: number;
}

export interface PayrollRun {
  id: Uuid;
  period_year: number;
  period_month: number;
  status: string;
  notes: string | null;
  summary?: Record<string, unknown> | null;
  record_counts?: Record<string, number> | null;
  created_at: Timestamp;
  finalized_at: Timestamp | null;
  locked_at: Timestamp | null;
  paid_at: Timestamp | null;
  records?: SalaryRecord[];
}

// ---------------------------------------------------------------------------
// Complaints
// ---------------------------------------------------------------------------

export interface ComplaintCategory {
  id: Uuid;
  code: string;
  name: string;
  default_priority: string | null;
  default_visibility: string | null;
  is_active: boolean;
}

export type ComplaintStatus =
  | 'OPEN'
  | 'IN_REVIEW'
  | 'ACTION_REQUIRED'
  | 'RESOLVED'
  | 'CLOSED'
  | 'REJECTED';

export interface Complaint {
  id: Uuid;
  complaint_code: string;
  category_id: Uuid;
  category?: ComplaintCategory | null;
  title: string;
  description: string;
  priority: string | null;
  visibility: string;
  status: ComplaintStatus;
  raised_by_employee_id: Uuid | null;
  subject_employee_id: Uuid | null;
  subject_employee?: Pick<Employee, 'id' | 'employee_code' | 'full_name'> | null;
  assigned_to_user_id: Uuid | null;
  resolution_summary: string | null;
  rejection_reason: string | null;
  created_at: Timestamp;
  updated_at: Timestamp;
  closed_at: Timestamp | null;
  allowed_transitions: string[];
  comments?: ComplaintComment[];
  attachments?: Array<{ id: Uuid; file_id: Uuid; note: string | null; file?: FileMeta | null }>;
}

export interface ComplaintComment {
  id: Uuid;
  complaint_id: Uuid;
  author_user_id: Uuid;
  author?: { id: Uuid; username: string } | null;
  body: string;
  is_internal: boolean;
  created_at: Timestamp;
}

// ---------------------------------------------------------------------------
// Notifications / files / settings / audit / reports
// ---------------------------------------------------------------------------

export interface NotificationItem {
  id: Uuid;
  event_type: string;
  title: string;
  body: string;
  priority: string | null;
  is_read: boolean;
  read_at: Timestamp | null;
  deep_link: string | null;
  created_at: Timestamp;
}

export interface NotificationPreference {
  event_type: string;
  channel: string;
  is_enabled: boolean;
  is_default: boolean;
  can_disable: boolean;
}

export interface FileMeta {
  id: Uuid;
  original_name: string;
  content_type: string;
  size_bytes: number;
  checksum: string;
  scan_status: string;
  created_at: Timestamp;
}

export type SettingValueType =
  | 'STRING'
  | 'NUMBER'
  | 'INTEGER'
  | 'BOOLEAN'
  | 'TIME'
  | 'TIMEZONE'
  | 'JSON_LIST'
  | 'ENUM'
  | 'DURATION';

export interface SettingSchemaItem {
  key: string;
  value_type: SettingValueType;
  description: string;
  default: unknown;
  min: number | null;
  max: number | null;
  allowed_values: unknown[] | null;
  unit: string | null;
  is_provisional: boolean;
  provisional_reference?: string | null;
  consumer_module: string;
  group: string;
  /** Whether a change affects already-computed attendance/payroll (docs/07 section 7.4). */
  affects_history?: boolean;
}

export interface SettingItem {
  key: string;
  value: unknown;
  value_type: SettingValueType;
  version: number;
  updated_by_user_id: Uuid | null;
  updated_at: Timestamp;
  is_provisional: boolean;
  group: string;
  description: string;
}

export interface SettingHistoryItem {
  id: Uuid;
  key: string;
  old_value: unknown;
  new_value: unknown;
  actor_user_id: Uuid | null;
  reason: string;
  created_at: Timestamp;
}

export interface AuditLog {
  id: Uuid;
  category: string;
  action: string;
  entity_type: string | null;
  entity_id: Uuid | null;
  actor_user_id: Uuid | null;
  actor?: { id: Uuid; username: string } | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  reason: string | null;
  request_id: string | null;
  ip_address: string | null;
  created_at: Timestamp;
}

export interface ExportJob {
  id: Uuid;
  report_type: string;
  format: string;
  status: string;
  parameters: Record<string, unknown> | null;
  file_id: Uuid | null;
  download_url: string | null;
  error_message: string | null;
  created_at: Timestamp;
  completed_at: Timestamp | null;
}

export interface ReportCatalogItem {
  report_type: string;
  name: string;
  description: string | null;
  required_permission: string;
  formats: string[];
  filters: Array<{
    name: string;
    type: string;
    required: boolean;
    label: string;
    allowed_values?: unknown[] | null;
  }>;
}

export interface DashboardSummary {
  [key: string]: unknown;
}

export interface PermissionCatalogItem {
  code: string;
  description: string;
  module: string;
  is_sensitive: boolean;
}

export interface Role {
  id: Uuid;
  code: string;
  name: string;
  description: string | null;
  is_system: boolean;
  is_assignable: boolean;
  permission_count?: number;
  user_count?: number;
  permissions?: PermissionCatalogItem[];
}
/**
 * Declaration merge: the failure form of an attendance verification is returned alongside the
 * problem-details body (docs/03_API_CONTRACT.md section 4.2), not inside the success resource.
 */
export interface ProblemDetails {
  verification?: VerificationResult;
}