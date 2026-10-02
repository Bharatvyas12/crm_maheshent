import { describe, expect, it } from 'vitest';
import {
  EMPLOYEE_PERMISSIONS,
  PERMISSION_CODES,
  PERMISSION_MODULES,
  SENSITIVE_PERMISSIONS,
  hasAllPermissions,
  hasAnyPermission,
  hasPermission
} from './permissions';

describe('permission catalog', () => {
  it('contains exactly 96 unique permission codes (docs/05_PERMISSIONS.md)', () => {
    expect(PERMISSION_CODES).toHaveLength(96);
    expect(new Set(PERMISSION_CODES).size).toBe(96);
  });

  it('seeds the EMPLOYEE role with exactly 28 permissions', () => {
    expect(EMPLOYEE_PERMISSIONS).toHaveLength(28);
    expect(new Set(EMPLOYEE_PERMISSIONS).size).toBe(28);
  });

  it('only references codes that exist in the catalog', () => {
    const catalog = new Set<string>(PERMISSION_CODES);
    for (const code of EMPLOYEE_PERMISSIONS) expect(catalog.has(code)).toBe(true);
    for (const module of PERMISSION_MODULES) {
      for (const code of module.codes) expect(catalog.has(code)).toBe(true);
    }
  });

  it('groups every catalog code under exactly one module', () => {
    const grouped = PERMISSION_MODULES.flatMap((module) => module.codes);
    expect(new Set(grouped).size).toBe(grouped.length);
    expect(new Set(grouped)).toEqual(new Set(PERMISSION_CODES));
  });

  it('seeds EMPLOYEE with ledger.read.self but not salary.read.self (decision 25)', () => {
    expect(EMPLOYEE_PERMISSIONS).toContain('ledger.read.self');
    expect(EMPLOYEE_PERMISSIONS).not.toContain('salary.read.self');
  });

  it('never grants a seeded employee an all-scope, approval or management permission', () => {
    const forbidden = /(\.read\.all$|\.approve$|\.manage$|\.adjust$|\.cancel\.any$|\.manage\.roles$|\.update\.status\.any$)/;
    for (const code of EMPLOYEE_PERMISSIONS) {
      expect(forbidden.test(code), `${code} must not be seeded to EMPLOYEE`).toBe(false);
    }
  });

  it('marks the financial management scopes as sensitive so the UI can de-emphasise them', () => {
    for (const code of ['salary.read.all', 'ledger.entry.create', 'payroll.pay', 'audit.read'] as const) {
      expect(SENSITIVE_PERMISSIONS.has(code)).toBe(true);
    }
  });
});

describe('permission helpers', () => {
  it('hasPermission is exact', () => {
    expect(hasPermission(['order.claim'], 'order.claim')).toBe(true);
    expect(hasPermission(['order.claim'], 'order.reassign')).toBe(false);
    expect(hasPermission(undefined, 'order.claim')).toBe(false);
  });

  it('hasAnyPermission is a union', () => {
    expect(hasAnyPermission(['task.read.self'], ['task.read.all', 'task.read.self'])).toBe(true);
    expect(hasAnyPermission(['task.read.self'], ['task.read.all'])).toBe(false);
  });

  it('hasAllPermissions requires every code', () => {
    expect(hasAllPermissions(['a', 'b'], ['a', 'b'])).toBe(true);
    expect(hasAllPermissions(['a'], ['a', 'b'])).toBe(false);
  });

  it('an ADMIN holding the full catalog satisfies every employee permission', () => {
    expect(hasAllPermissions(PERMISSION_CODES, EMPLOYEE_PERMISSIONS)).toBe(true);
  });
});