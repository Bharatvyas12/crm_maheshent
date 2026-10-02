import { Badge, type BadgeTone } from './Badge';
import { humanize } from '@/lib/format';

/**
 * Status presentation (docs/07_UI_SPEC.md section 5.6): always human-readable text plus a colour
 * accent. Colour is never the only signal.
 *
 * Tones are keyed by documented enums from docs/04_BUSINESS_RULES.md / docs/03_API_CONTRACT.md.
 * Unknown values are shown verbatim rather than hidden (docs/07 section 9).
 */
const TONES: Record<string, BadgeTone> = {
  // Attendance day classification
  FULL_DAY: 'success',
  HALF_DAY: 'info',
  PARTIAL_DAY: 'warning',
  NONE: 'neutral',
  // Attendance status
  NOT_MARKED: 'neutral',
  PRESENT: 'success',
  INCOMPLETE: 'danger',
  ABSENT: 'danger',
  ON_LEAVE: 'neutral',
  HOLIDAY: 'neutral',
  WEEKLY_OFF: 'neutral',
  // Task / assignment
  OPEN: 'info',
  IN_PROGRESS: 'warning',
  COMPLETED: 'success',
  CANCELLED: 'neutral',
  ASSIGNED: 'info',
  STARTED: 'warning',
  SUBMITTED: 'info',
  RESUBMISSION_REQUESTED: 'warning',
  APPROVED: 'success',
  REJECTED: 'danger',
  PENDING_DECISION: 'warning',
  // Orders
  DRAFT: 'neutral',
  BROADCASTED: 'info',
  CLAIMED: 'info',
  PACKING: 'warning',
  PACKED: 'warning',
  READY_FOR_DELIVERY: 'info',
  OUT_FOR_DELIVERY: 'info',
  DELIVERED: 'success',
  FAILED: 'danger',
  REASSIGNED: 'warning',
  // Leave / correction
  PENDING: 'warning',
  MODIFICATION_REQUESTED: 'warning',
  // Complaints
  IN_REVIEW: 'warning',
  ACTION_REQUIRED: 'warning',
  RESOLVED: 'success',
  CLOSED: 'neutral',
  // Payroll
  COMPUTED: 'info',
  FINALIZED: 'success',
  LOCKED: 'warning',
  PAID: 'success',
  // Ledger
  ACTIVE: 'success',
  DISABLED: 'neutral',
  LOCKED_OUT: 'danger',
  EXITED: 'neutral',
  INACTIVE: 'neutral',
  // Priority
  LOW: 'neutral',
  NORMAL: 'neutral',
  HIGH: 'warning',
  URGENT: 'danger',
  // Notifications
  QUEUED: 'info',
  RUNNING: 'warning',
  COMPLETE: 'success',
  ERROR: 'danger'
};

export function statusTone(value: string | null | undefined): BadgeTone {
  if (!value) return 'neutral';
  return TONES[value] ?? 'neutral';
}

export function StatusPill({ value, className }: { value: string | null | undefined; className?: string }) {
  return (
    <Badge tone={statusTone(value)} className={className}>
      {humanize(value)}
    </Badge>
  );
}