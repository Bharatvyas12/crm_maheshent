/**
 * Permission catalog mirror of docs/05_PERMISSIONS.md section 3 (96 codes).
 *
 * The catalog exists so navigation and affordances can be derived from
 * `GET /auth/me` permissions. It is a UX convenience ONLY: the backend
 * re-checks every protected operation (docs/05 section 1, AGENTS.md section 3).
 */

export const PERMISSION_CODES = [
  // 3.1 Authentication and session
  'auth.session.read.self',
  'auth.session.revoke.self',
  'auth.password.change.self',
  'employee.manage.credentials',
  // 3.2 Employee and user management
  'profile.update.self',
  'employee.read.self',
  'employee.read.all',
  'employee.read.sensitive',
  'employee.create',
  'employee.update',
  'employee.update.sensitive',
  'employee.deactivate',
  'employee.manage.roles',
  // 3.3 Roles and permissions
  'role.read',
  'role.manage',
  'permission.read',
  // 3.4 Business settings
  'settings.read',
  'settings.update',
  'settings.read.history',
  // 3.5 Attendance, breaks and verification
  'attendance.checkin.self',
  'attendance.checkout.self',
  'attendance.break.self',
  'attendance.read.self',
  'attendance.read.all',
  'attendance.manage',
  'attendance.config.manage',
  'attendance.qr.generate',
  'attendance.correct.request.self',
  'attendance.correct.approve',
  // 3.6 Tasks
  'task.create',
  'task.read.self',
  'task.read.all',
  'task.update',
  'task.assign',
  'task.cancel',
  'task.submit.self',
  'task.comment',
  'task.review',
  // 3.7 Orders
  'order.create',
  'order.read.available',
  'order.read.self',
  'order.read.all',
  'order.update',
  'order.broadcast',
  'order.claim',
  'order.update.status.self',
  'order.update.status.any',
  'order.proof.upload',
  'order.reassign',
  'order.cancel',
  // 3.8 Leave
  'leave.apply.self',
  'leave.read.self',
  'leave.read.all',
  'leave.cancel.self',
  'leave.cancel.any',
  'leave.approve',
  'leave.type.manage',
  'leave.balance.manage',
  // 3.9 Ledger, advances, salary and payroll
  'ledger.read.self',
  'ledger.read.all',
  'ledger.entry.create',
  'ledger.entry.adjust',
  'advance.read.self',
  'advance.read.all',
  'advance.create',
  'advance.approve',
  'salary.read.self',
  'salary.read.all',
  'salary.compute',
  'salary.finalize',
  'payroll.lock',
  'payroll.unlock',
  'payroll.pay',
  // 3.10 Complaints
  'complaint.create.self',
  'complaint.read.self',
  'complaint.read.all',
  'complaint.read.internal',
  'complaint.comment',
  'complaint.manage',
  'complaint.resolve',
  'complaint.close',
  // 3.11 Notifications, files, reports and audit
  'notification.read.self',
  'notification.manage',
  'file.upload',
  'file.read.all',
  'file.delete',
  'report.attendance',
  'report.tasks',
  'report.orders',
  'report.leaves',
  'report.ledger',
  'report.salary',
  'report.complaints',
  'report.export',
  'audit.read',
  'audit.export'
] as const;

export type PermissionCode = (typeof PERMISSION_CODES)[number];

/** Grouping mirror of the module headings in docs/05_PERMISSIONS.md section 3. */
export const PERMISSION_MODULES: Array<{ module: string; codes: PermissionCode[] }> = [
  {
    module: 'Authentication and session',
    codes: ['auth.session.read.self', 'auth.session.revoke.self', 'auth.password.change.self', 'employee.manage.credentials']
  },
  {
    module: 'Employee and user management',
    codes: [
      'profile.update.self',
      'employee.read.self',
      'employee.read.all',
      'employee.read.sensitive',
      'employee.create',
      'employee.update',
      'employee.update.sensitive',
      'employee.deactivate',
      'employee.manage.roles'
    ]
  },
  { module: 'Roles and permissions', codes: ['role.read', 'role.manage', 'permission.read'] },
  { module: 'Business settings', codes: ['settings.read', 'settings.update', 'settings.read.history'] },
  {
    module: 'Attendance, breaks and verification',
    codes: [
      'attendance.checkin.self',
      'attendance.checkout.self',
      'attendance.break.self',
      'attendance.read.self',
      'attendance.read.all',
      'attendance.manage',
      'attendance.config.manage',
      'attendance.qr.generate',
      'attendance.correct.request.self',
      'attendance.correct.approve'
    ]
  },
  {
    module: 'Tasks',
    codes: [
      'task.create',
      'task.read.self',
      'task.read.all',
      'task.update',
      'task.assign',
      'task.cancel',
      'task.submit.self',
      'task.comment',
      'task.review'
    ]
  },
  {
    module: 'Orders',
    codes: [
      'order.create',
      'order.read.available',
      'order.read.self',
      'order.read.all',
      'order.update',
      'order.broadcast',
      'order.claim',
      'order.update.status.self',
      'order.update.status.any',
      'order.proof.upload',
      'order.reassign',
      'order.cancel'
    ]
  },
  {
    module: 'Leave',
    codes: [
      'leave.apply.self',
      'leave.read.self',
      'leave.read.all',
      'leave.cancel.self',
      'leave.cancel.any',
      'leave.approve',
      'leave.type.manage',
      'leave.balance.manage'
    ]
  },
  {
    module: 'Ledger, advances, salary and payroll',
    codes: [
      'ledger.read.self',
      'ledger.read.all',
      'ledger.entry.create',
      'ledger.entry.adjust',
      'advance.read.self',
      'advance.read.all',
      'advance.create',
      'advance.approve',
      'salary.read.self',
      'salary.read.all',
      'salary.compute',
      'salary.finalize',
      'payroll.lock',
      'payroll.unlock',
      'payroll.pay'
    ]
  },
  {
    module: 'Complaints',
    codes: [
      'complaint.create.self',
      'complaint.read.self',
      'complaint.read.all',
      'complaint.read.internal',
      'complaint.comment',
      'complaint.manage',
      'complaint.resolve',
      'complaint.close'
    ]
  },
  {
    module: 'Notifications, files, reports and audit',
    codes: [
      'notification.read.self',
      'notification.manage',
      'file.upload',
      'file.read.all',
      'file.delete',
      'report.attendance',
      'report.tasks',
      'report.orders',
      'report.leaves',
      'report.ledger',
      'report.salary',
      'report.complaints',
      'report.export',
      'audit.read',
      'audit.export'
    ]
  }
];

/** Permissions flagged `is_sensitive` in docs/05_PERMISSIONS.md section 3. */
export const SENSITIVE_PERMISSIONS: ReadonlySet<string> = new Set([
  'employee.manage.credentials',
  'employee.read.sensitive',
  'employee.create',
  'employee.update',
  'employee.update.sensitive',
  'employee.deactivate',
  'employee.manage.roles',
  'role.manage',
  'settings.update',
  'settings.read.history',
  'attendance.read.all',
  'attendance.manage',
  'attendance.config.manage',
  'attendance.qr.generate',
  'attendance.correct.approve',
  'task.review',
  'order.read.all',
  'order.update.status.any',
  'order.reassign',
  'order.cancel',
  'leave.read.all',
  'leave.cancel.any',
  'leave.approve',
  'leave.type.manage',
  'leave.balance.manage',
  'ledger.read.self',
  'ledger.read.all',
  'ledger.entry.create',
  'ledger.entry.adjust',
  'advance.read.self',
  'advance.read.all',
  'advance.create',
  'advance.approve',
  'salary.read.self',
  'salary.read.all',
  'salary.compute',
  'salary.finalize',
  'payroll.lock',
  'payroll.unlock',
  'payroll.pay',
  'complaint.read.all',
  'complaint.read.internal',
  'complaint.manage',
  'complaint.resolve',
  'complaint.close',
  'file.read.all',
  'file.delete',
  'report.attendance',
  'report.leaves',
  'report.ledger',
  'report.salary',
  'report.complaints',
  'report.export',
  'audit.read',
  'audit.export'
]);

/** The `.self` set granted to EMPLOYEE (docs/05_PERMISSIONS.md section 4.2). */
export const EMPLOYEE_PERMISSIONS: readonly PermissionCode[] = [
  'auth.session.read.self',
  'auth.session.revoke.self',
  'auth.password.change.self',
  'profile.update.self',
  'employee.read.self',
  'attendance.checkin.self',
  'attendance.checkout.self',
  'attendance.break.self',
  'attendance.read.self',
  'attendance.correct.request.self',
  'task.read.self',
  'task.submit.self',
  'task.comment',
  'order.read.available',
  'order.read.self',
  'order.claim',
  'order.update.status.self',
  'order.proof.upload',
  'leave.apply.self',
  'leave.read.self',
  'leave.cancel.self',
  'ledger.read.self',
  'advance.read.self',
  'complaint.create.self',
  'complaint.read.self',
  'complaint.comment',
  'notification.read.self',
  'file.upload'
];

export function hasPermission(permissions: readonly string[] | undefined, code: string): boolean {
  if (!permissions) return false;
  return permissions.includes(code);
}

export function hasAnyPermission(permissions: readonly string[] | undefined, codes: readonly string[]): boolean {
  if (!permissions || codes.length === 0) return false;
  return codes.some((code) => permissions.includes(code));
}

export function hasAllPermissions(permissions: readonly string[] | undefined, codes: readonly string[]): boolean {
  if (!permissions) return false;
  return codes.every((code) => permissions.includes(code));
}