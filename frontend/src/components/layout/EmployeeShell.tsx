'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import { useSession } from '@/features/auth/session';
import { useUnreadCount } from '@/features/notifications/hooks';
import { visibleEmployeeNav, visibleEmployeeTabs, type NavItem } from '@/lib/nav';
import { cn } from '@/lib/utils';
import { Icon } from '@/components/ui/Icons';
import { Dialog } from '@/components/ui/Dialog';
import { Button } from '@/components/ui/Button';
import { OfflineBanner } from './OfflineBanner';

function isActive(pathname: string, href: string): boolean {
  if (href === '/app') return pathname === '/app';
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavLink({ item, active, onNavigate, badge }: { item: NavItem; active: boolean; onNavigate?: () => void; badge?: number }) {
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'flex min-h-touch items-center gap-2 rounded-md px-3 text-sm font-medium',
        active ? 'bg-primary-soft text-primary' : 'text-content-muted hover:bg-surface-muted'
      )}
    >
      <Icon name={item.icon} />
      <span className="truncate">{item.label}</span>
      {badge && badge > 0 ? <span className="ml-auto rounded-full bg-primary px-2 py-0.5 text-xs text-primary-fg">{badge}</span> : null}
    </Link>
  );
}

export function EmployeeShell({ children }: { children: React.ReactNode }) {
  const { permissions, employee, user, signOut } = useSession();
  const { data: unread } = useUnreadCount();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  const nav = visibleEmployeeNav(permissions);
  const tabs = visibleEmployeeTabs(permissions);

  return (
    <div className="flex min-h-screen flex-col bg-surface-muted">
      <OfflineBanner />
      <header className="sticky top-0 z-30 border-b border-surface-border bg-surface">
        <div className="mx-auto flex w-full max-w-3xl items-center justify-between gap-3 px-4 py-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-content">{employee?.full_name ?? user?.username ?? 'Employee'}</p>
            <p className="truncate text-xs text-content-muted">{employee?.employee_code ?? ''}</p>
          </div>
          <div className="flex items-center gap-1">
            <Link
              href="/app/notifications"
              aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'}
              className="relative flex h-11 w-11 items-center justify-center rounded-md text-content-muted hover:bg-surface-muted"
            >
              <Icon name="bell" />
              {unread && unread > 0 ? (
                <span className="absolute right-1 top-1 min-w-5 rounded-full bg-danger px-1 text-center text-[10px] font-bold text-white">
                  {unread > 99 ? '99+' : unread}
                </span>
              ) : null}
            </Link>
            <button
              type="button"
              onClick={() => setMenuOpen(true)}
              aria-label="Open all sections"
              className="flex h-11 w-11 items-center justify-center rounded-md text-content-muted hover:bg-surface-muted"
            >
              <Icon name="list" />
            </button>
          </div>
        </div>
      </header>

      <main id="main-content" className="mx-auto w-full max-w-3xl flex-1 px-4 py-4 pb-safe">
        {children}
      </main>

      <nav
        aria-label="Primary"
        className="fixed inset-x-0 bottom-0 z-30 border-t border-surface-border bg-surface pb-[env(safe-area-inset-bottom)]"
      >
        <ul className="mx-auto flex w-full max-w-3xl items-stretch justify-between">
          {tabs.map((tab) => {
            const active = isActive(pathname, tab.href);
            const badge = tab.badgeKey === 'unread' ? unread : undefined;
            return (
              <li key={tab.href} className="flex-1">
                <Link
                  href={tab.href}
                  aria-current={active ? 'page' : undefined}
                  className={cn(
                    'relative flex min-h-action flex-col items-center justify-center gap-0.5 text-[11px] font-medium',
                    active ? 'text-primary' : 'text-content-muted'
                  )}
                >
                  <Icon name={tab.icon} className="h-5 w-5" />
                  {tab.label}
                  {badge && badge > 0 ? (
                    <span className="absolute right-3 top-1 min-w-4 rounded-full bg-danger px-1 text-center text-[10px] font-bold text-white">
                      {badge > 99 ? '99+' : badge}
                    </span>
                  ) : null}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <Dialog open={menuOpen} onClose={() => setMenuOpen(false)} title="All sections" size="sm">
        <nav aria-label="All sections">
          <ul className="space-y-1">
            {nav.map((item) => (
              <li key={item.href}>
                <NavLink
                  item={item}
                  active={isActive(pathname, item.href)}
                  onNavigate={() => setMenuOpen(false)}
                  badge={item.badgeKey === 'unread' ? unread : undefined}
                />
              </li>
            ))}
          </ul>
        </nav>
        <div className="mt-4 border-t border-surface-border pt-4">
          <Button
            variant="secondary"
            size="lg"
            className="w-full"
            onClick={() => {
              setMenuOpen(false);
              void signOut();
            }}
          >
            Sign out
          </Button>
        </div>
      </Dialog>
    </div>
  );
}