/**
 * Deterministic formatters (docs/07_UI_SPEC.md section 13: formatters accept an injected "now").
 *
 * Money is a decimal STRING from the API (docs/01_ARCHITECTURE.md section 13.1); it is never
 * converted to a float for arithmetic in the client. Formatting only.
 */

const DEFAULT_TIMEZONE = 'UTC';

function safeTimezone(timezone?: string | null): string {
  return timezone && timezone.length > 0 ? timezone : DEFAULT_TIMEZONE;
}

/** Format a decimal-string money value. Returns a plain string, never a number. */
export function formatMoney(value: string | number | null | undefined, currency = 'INR', timezone?: string): string {
  void timezone;
  if (value === null || value === undefined || value === '') return '-';
  const normalized = typeof value === 'number' ? value.toFixed(2) : String(value);
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(Number(normalized));
  } catch {
    return `${normalized} ${currency}`;
  }
}

/** Format a `YYYY-MM-DD` business date without timezone drift. */
export function formatBusinessDate(date: string | null | undefined): string {
  if (!date) return '-';
  const parts = date.slice(0, 10).split('-');
  if (parts.length !== 3) return date;
  const [year, month, day] = parts.map((part) => Number(part));
  if (!year || !month || !day) return date;
  // Construct in UTC so the rendered calendar date matches the business date exactly.
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    timeZone: 'UTC'
  }).format(new Date(Date.UTC(year, month - 1, day)));
}

export function formatDateRange(start: string | null | undefined, end: string | null | undefined): string {
  if (!start && !end) return '-';
  if (start === end) return formatBusinessDate(start);
  return `${formatBusinessDate(start)} - ${formatBusinessDate(end)}`;
}

/** Format a UTC timestamp in the business timezone. */
export function formatDateTime(timestamp: string | null | undefined, timezone?: string | null): string {
  if (!timestamp) return '-';
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return timestamp;
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: safeTimezone(timezone)
  }).format(date);
}

export function formatTime(timestamp: string | null | undefined, timezone?: string | null): string {
  if (!timestamp) return '-';
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return timestamp;
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: safeTimezone(timezone)
  }).format(date);
}

/** Duration rendered from integer seconds (never computed business totals in the client). */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '-';
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours <= 0 && minutes <= 0) return `${total}s`;
  if (hours <= 0) return `${minutes}m`;
  return `${hours}h ${minutes}m`;
}

/** Live elapsed timer between a server timestamp and now (break timer, claim countdown). */
export function formatElapsed(fromIso: string | null | undefined, now: Date = new Date()): string {
  if (!fromIso) return '00:00';
  const from = new Date(fromIso).getTime();
  if (Number.isNaN(from)) return '00:00';
  const seconds = Math.max(0, Math.floor((now.getTime() - from) / 1000));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const pad = (n: number) => String(n).padStart(2, '0');
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

/** Countdown to a future timestamp; returns null when already elapsed. */
export function formatCountdown(targetIso: string | null | undefined, now: Date = new Date()): string | null {
  if (!targetIso) return null;
  const target = new Date(targetIso).getTime();
  if (Number.isNaN(target)) return null;
  const seconds = Math.floor((target - now.getTime()) / 1000);
  if (seconds <= 0) return null;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${String(s).padStart(2, '0')}s`;
}

/** Relative time for notification/audit lists. */
export function formatRelative(timestamp: string | null | undefined, now: Date = new Date(), timezone?: string | null): string {
  if (!timestamp) return '-';
  const then = new Date(timestamp).getTime();
  if (Number.isNaN(then)) return timestamp;
  const diffMs = now.getTime() - then;
  const minutes = Math.round(diffMs / 60000);
  if (Math.abs(minutes) < 1) return 'just now';
  if (Math.abs(minutes) < 60) return minutes > 0 ? `${minutes}m ago` : `in ${-minutes}m`;
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return hours > 0 ? `${hours}h ago` : `in ${-hours}h`;
  const days = Math.round(hours / 24);
  if (Math.abs(days) < 7) return days > 0 ? `${days}d ago` : `in ${-days}d`;
  return formatDateTime(timestamp, timezone);
}

export function nowIso(): string {
  return new Date().toISOString();
}

/** Humanise an UPPER_SNAKE_CASE enum or code for display. */
export function humanize(value: string | null | undefined): string {
  if (!value) return '-';
  return value
    .toLowerCase()
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}