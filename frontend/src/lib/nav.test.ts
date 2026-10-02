import { describe, expect, it } from 'vitest';
import { visibleAdminNav, visibleEmployeeTabs, visibleEmployeeNav } from './nav';
import { EMPLOYEE_PERMISSIONS, PERMISSION_CODES } from './permissions';
import { hasAnyPermission } from './permissions';

describe('navigation is derived from server permissions', () => {
  it('shows an employee exactly the documented employee areas', () => {
    const hrefs = visibleEmployeeNav(EMPLOYEE_PERMISSIONS).map((item) => item.href);
    expect(hrefs).toEqual([
      '/app',
      '/app/attendance',
      '/app/tasks',
      '/app/orders',
      '/app/leaves',
      '/app/complaints',
      '/app/ledger',
      '/app/notifications',
      '/app/profile'
    ]);
  });

  it('shows the mobile tab bar only the thumb-reachable sections', () => {
    expect(visibleEmployeeTabs(EMPLOYEE_PERMISSIONS).map((item) => item.href)).toEqual([
      '/app',
      '/app/attendance',
      '/app/tasks',
      '/app/orders',
      '/app/notifications'
    ]);
  });

  it('hides an employee area the caller cannot read', () => {
    const withoutLedger = EMPLOYEE_PERMISSIONS.filter((code) => code !== 'ledger.read.self' && code !== 'advance.read.self');
    const hrefs = visibleEmployeeNav(withoutLedger).map((item) => item.href);
    expect(hrefs).not.toContain('/app/ledger');
  });

  it('renders no navigation at all for an empty permission set', () => {
    expect(visibleEmployeeNav([])).toHaveLength(0);
  });

  it('gives an admin the full documented admin surface', () => {
    const groups = visibleAdminNav(PERMISSION_CODES);
    const hrefs = groups.flatMap((group) => group.items.map((item) => item.href));
    for (const expected of [
      '/admin',
      '/admin/employees',
      '/admin/roles',
      '/admin/attendance',
      '/admin/attendance/corrections',
      '/admin/attendance/qr',
      '/admin/holidays',
      '/admin/tasks',
      '/admin/tasks/review',
      '/admin/orders',
      '/admin/leaves',
      '/admin/leave-balances',
      '/admin/complaints',
      '/admin/notifications',
      '/admin/ledger',
      '/admin/advances',
      '/admin/payroll',
      '/admin/reports',
      '/admin/settings',
      '/admin/audit'
    ]) {
      expect(hrefs, `${expected} should be visible to an admin`).toContain(expected);
    }
  });

  it('drops empty groups and keeps the always-available dashboard group', () => {
    const groups = visibleAdminNav(['settings.read']);
    const hrefs = groups.flatMap((group) => group.items.map((item) => item.href));
    // The dashboard nav item is intentionally permission-free (every authenticated admin sees it).
    expect(hrefs).toEqual(['/admin', '/admin/settings']);
    expect(groups.map((group) => group.label)).toEqual(['Overview', 'Configuration']);
  });

  it('every admin nav item is gated by a permission that exists in the catalog', () => {
    const catalog = new Set<string>(PERMISSION_CODES);
    for (const group of visibleAdminNav(PERMISSION_CODES)) {
      for (const item of group.items) {
        const codes = [...(item.requiresAny ?? []), ...(item.requiresAll ?? [])];
        for (const code of codes) expect(catalog.has(code), `${item.href} -> ${code}`).toBe(true);
      }
    }
  });

  it('an admin sees every item because it holds at least one listed permission', () => {
    for (const group of visibleAdminNav(PERMISSION_CODES)) {
      for (const item of group.items) {
        const codes = [...(item.requiresAny ?? []), ...(item.requiresAll ?? [])];
        if (codes.length === 0) continue;
        expect(hasAnyPermission(PERMISSION_CODES, codes), item.href).toBe(true);
      }
    }
  });
});