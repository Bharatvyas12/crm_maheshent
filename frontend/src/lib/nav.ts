import type { PermissionCode } from './permissions';
import { hasAllPermissions, hasAnyPermission } from './permissions';

/**
 * Navigation is derived from `GET /auth/me` permissions (docs/07_UI_SPEC.md section 2 and 4).
 * A route the user lacks permission for is not rendered in navigation; the server would reject
 * it anyway. Navigation is UX only - never a security control.
 */
export interface NavItem {
  href: string;
  label: string;
  /** Item is shown when the user holds ANY of these permissions. */
  requiresAny?: PermissionCode[];
  /** Item is shown only when the user holds ALL of these permissions. */
  requiresAll?: PermissionCode[];
  /** Icon key resolved by the shell component. */
  icon: NavIcon;
  badgeKey?: 'unread' | 'corrections' | 'review' | 'reviewQueue';
}

export type NavIcon =
  | 'home'
  | 'clock'
  | 'coffee'
  | 'check-square'
  | 'package'
  | 'calendar'
  | 'message'
  | 'wallet'
  | 'bell'
  | 'user'
  | 'users'
  | 'shield'
  | 'map-pin'
  | 'gift'
  | 'trending'
  | 'settings'
  | 'list'
  | 'file-text';

export const EMPLOYEE_NAV: NavItem[] = [
  { href: '/app', label: 'Dashboard', icon: 'home', requiresAny: ['attendance.read.self'] },
  { href: '/app/attendance', label: 'Attendance', icon: 'clock', requiresAny: ['attendance.read.self'] },
  { href: '/app/tasks', label: 'Tasks', icon: 'check-square', requiresAny: ['task.read.self'] },
  { href: '/app/orders', label: 'Orders', icon: 'package', requiresAny: ['order.read.available', 'order.read.self'] },
  { href: '/app/leaves', label: 'Leave', icon: 'calendar', requiresAny: ['leave.apply.self', 'leave.read.self'] },
  { href: '/app/complaints', label: 'Complaints', icon: 'message', requiresAny: ['complaint.create.self', 'complaint.read.self'] },
  { href: '/app/ledger', label: 'Ledger', icon: 'wallet', requiresAny: ['ledger.read.self', 'advance.read.self', 'salary.read.self'] },
  { href: '/app/notifications', label: 'Notifications', icon: 'bell', requiresAny: ['notification.read.self'], badgeKey: 'unread' },
  { href: '/app/profile', label: 'Profile', icon: 'user', requiresAny: ['employee.read.self'] }
];

/** Bottom-tab subset for the mobile employee shell (thumb reachable). */
export const EMPLOYEE_TABS: NavItem[] = [
  { href: '/app', label: 'Home', icon: 'home', requiresAny: ['attendance.read.self'] },
  { href: '/app/attendance', label: 'Attendance', icon: 'clock', requiresAny: ['attendance.read.self'] },
  { href: '/app/tasks', label: 'Tasks', icon: 'check-square', requiresAny: ['task.read.self'] },
  { href: '/app/orders', label: 'Orders', icon: 'package', requiresAny: ['order.read.available', 'order.read.self'] },
  { href: '/app/notifications', label: 'Alerts', icon: 'bell', requiresAny: ['notification.read.self'], badgeKey: 'unread' }
];

export interface AdminNavGroup {
  label: string;
  items: NavItem[];
}

export const ADMIN_NAV: AdminNavGroup[] = [
  {
    label: 'Overview',
    items: [{ href: '/admin', label: 'Dashboard', icon: 'home' }]
  },
  {
    label: 'People',
    items: [
      { href: '/admin/employees', label: 'Employees', icon: 'users', requiresAny: ['employee.read.all'] },
      { href: '/admin/roles', label: 'Roles & permissions', icon: 'shield', requiresAny: ['role.read'] }
    ]
  },
  {
    label: 'Attendance',
    items: [
      { href: '/admin/attendance', label: 'Register', icon: 'clock', requiresAny: ['attendance.read.all'] },
      { href: '/admin/attendance/corrections', label: 'Corrections', icon: 'list', requiresAny: ['attendance.correct.approve'], badgeKey: 'corrections' },
      { href: '/admin/attendance/qr', label: 'Shop QR', icon: 'map-pin', requiresAny: ['attendance.qr.generate'] },
      { href: '/admin/holidays', label: 'Holidays', icon: 'calendar', requiresAny: ['attendance.config.manage'] }
    ]
  },
  {
    label: 'Work',
    items: [
      { href: '/admin/tasks', label: 'Tasks', icon: 'check-square', requiresAny: ['task.read.all'] },
      { href: '/admin/tasks/review', label: 'Review queue', icon: 'file-text', requiresAny: ['task.review'], badgeKey: 'review' },
      { href: '/admin/orders', label: 'Orders', icon: 'package', requiresAny: ['order.read.all'] }
    ]
  },
  {
    label: 'Time off',
    items: [
      { href: '/admin/leaves', label: 'Leave queue', icon: 'calendar', requiresAny: ['leave.read.all'] },
      { href: '/admin/leave-balances', label: 'Balances', icon: 'list', requiresAny: ['leave.read.all'] }
    ]
  },
  {
    label: 'Support',
    items: [
      { href: '/admin/complaints', label: 'Complaints', icon: 'message', requiresAny: ['complaint.read.all'] },
      { href: '/admin/notifications', label: 'Notifications', icon: 'bell', requiresAny: ['notification.manage'] }
    ]
  },
  {
    label: 'Finance',
    items: [
      { href: '/admin/ledger', label: 'Ledger', icon: 'wallet', requiresAny: ['ledger.read.all'] },
      { href: '/admin/advances', label: 'Advances', icon: 'trending', requiresAny: ['advance.read.all'] },
      { href: '/admin/payroll', label: 'Payroll', icon: 'gift', requiresAny: ['salary.read.all'] }
    ]
  },
  {
    label: 'Insights',
    items: [
      { href: '/admin/reports', label: 'Reports', icon: 'file-text', requiresAny: ['report.attendance', 'report.tasks', 'report.orders', 'report.leaves', 'report.ledger', 'report.salary', 'report.complaints'] },
      { href: '/admin/audit', label: 'Audit log', icon: 'list', requiresAny: ['audit.read'] }
    ]
  },
  {
    label: 'Configuration',
    items: [{ href: '/admin/settings', label: 'Settings', icon: 'settings', requiresAny: ['settings.read'] }]
  }
];

export function isNavItemVisible(item: NavItem, permissions: readonly string[]): boolean {
  if (item.requiresAll && item.requiresAll.length > 0 && !hasAllPermissions(permissions, item.requiresAll)) {
    return false;
  }
  if (item.requiresAny && item.requiresAny.length > 0 && !hasAnyPermission(permissions, item.requiresAny)) {
    return false;
  }
  return true;
}

export function visibleEmployeeNav(permissions: readonly string[]): NavItem[] {
  return EMPLOYEE_NAV.filter((item) => isNavItemVisible(item, permissions));
}

export function visibleEmployeeTabs(permissions: readonly string[]): NavItem[] {
  return EMPLOYEE_TABS.filter((item) => isNavItemVisible(item, permissions));
}

export function visibleAdminNav(permissions: readonly string[]): AdminNavGroup[] {
  return ADMIN_NAV.map((group) => ({
    label: group.label,
    items: group.items.filter((item) => isNavItemVisible(item, permissions))
  })).filter((group) => group.items.length > 0);
}