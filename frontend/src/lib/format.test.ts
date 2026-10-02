import { describe, expect, it } from 'vitest';
import { formatCountdown, formatDuration, formatElapsed, formatRelative, humanize } from './format';

describe('formatters are deterministic with an injected now', () => {
  it('formatDuration renders integer seconds without client arithmetic on business totals', () => {
    expect(formatDuration(0)).toBe('0s');
    expect(formatDuration(null)).toBe('-');
    expect(formatDuration(90)).toBe('1m');
    expect(formatDuration(3600)).toBe('1h 0m');
    expect(formatDuration(34200)).toBe('9h 30m');
  });

  it('formatElapsed counts up from a server timestamp', () => {
    const now = new Date('2026-09-25T10:00:00Z');
    expect(formatElapsed('2026-09-25T09:59:30Z', now)).toBe('00:30');
    expect(formatElapsed('2026-09-25T08:59:00Z', now)).toBe('1:01:00');
    expect(formatElapsed(null, now)).toBe('00:00');
  });

  it('formatCountdown returns null once the window elapsed', () => {
    const now = new Date('2026-09-25T10:00:00Z');
    expect(formatCountdown('2026-09-25T10:30:00Z', now)).toBe('30m 00s');
    expect(formatCountdown('2026-09-25T09:59:59Z', now)).toBeNull();
    expect(formatCountdown(null, now)).toBeNull();
  });

  it('formatRelative is stable for a fixed now', () => {
    const now = new Date('2026-09-25T10:00:00Z');
    expect(formatRelative('2026-09-25T09:59:40Z', now)).toBe('just now');
    expect(formatRelative('2026-09-25T09:30:00Z', now)).toBe('30m ago');
    expect(formatRelative('2026-09-25T07:00:00Z', now)).toBe('3h ago');
    expect(formatRelative('2026-09-23T10:00:00Z', now)).toBe('2d ago');
  });

  it('humanize never leaves a raw enum on screen', () => {
    expect(humanize('OUT_FOR_DELIVERY')).toBe('Out For Delivery');
    expect(humanize('PENDING_APPROVAL')).toBe('Pending Approval');
    expect(humanize(null)).toBe('-');
  });
});