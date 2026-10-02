'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import { useSession } from '@/features/auth/session';
import { useUnreadCount } from '@/features/notifications/hooks';
import { visibleAdminNav, type AdminNavGroup, type NavItem } from '@/lib/nav';
import { cn } from '@/lib/utils';
import { Icon } from '@/components/ui/Icons';
import { Dialog } from '@/components/ui/Dialog';
import { Button } from '@/components/ui/Button';
import { OfflineBanner } from './OfflineBanner';

function isActive(pathname: string, href: string): boolean {
  if (href === '/admin') return pathname === '/admin';
  return pathname === href || pathname.startsWith(`${href}/`);
}

function GroupNav({
  groups,
  pathname,
  onNavigate,
  unread
}: {
  groups: AdminNavGroup[];
  pathname: string;
  onNavigate?: () => void;
  unread?: number;
}) {
  return (
    <nav aria-label="Admin sections" className="space-y-4">
      {groups.map((group) => (
        <div key={group.label}>
          <p className="px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-content-muted">{group.label}</p>
          <ul className="space-y-0.5">
            {group.items.map((item: NavItem) => {
              const active = isActive(pathname, item.href);
              const badge = item.badgeKey === 'unread' ? unread : undefined;
              return (
                <li key={item.href}>
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
                    {badge && badge > 0 ? (
                      <span className="ml-auto rounded-full bg-primary px-2 py-0.5 text-xs text-primary-fg">{badge}</span>
                    ) : null}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

export function AdminShell({ children }: { children: React.ReactNode }) {
  const { permissions, user, employee, signOut } = useSession();
  const { data: unread } = useUnreadCount();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  const groups = visibleAdminNav(permissions);

  return (
    <div className="flex min-h-screen bg-surface-muted">
      <aside className="hidden w-64 shrink-0 border-r border-surface-border bg-surface lg:flex lg:flex-col">
        <div className="border-b border-surface-border px-4 py-4">
          <p className="text-sm font-semibold text-content">Workforce CRM</p>
          <p className="truncate text-xs text-content-muted">{user?.username ?? ''}</p>
        </div>
        <div className="flex-1 overflow-y-auto px-2 py-4">
          <GroupNav groups={groups} pathname={pathname} unread={unread} />
        </div>
        <div className="border-t border-surface-border p-3">
          <Button variant="secondary" size="md" className="w-full" onClick={() => void signOut()}>
            Sign out
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <OfflineBanner />
        <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-surface-border bg-surface px-4 py-3 lg:hidden">
          <button
            type="button"
            onClick={() => setMenuOpen(true)}
            aria-label="Open admin navigation"
            className="flex h-11 w-11 items-center justify-center rounded-md text-content-muted hover:bg-surface-muted"
          >
            <Icon name="list" />
          </button>
          <p className="truncate text-sm font-semibold">Workforce CRM</p>
          <Link
            href="/admin/notifications"
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
        </header>

        <main id="main-content" className="mx-auto w-full max-w-7xl flex-1 px-4 py-5 lg:px-8">
          {children}
        </main>

        <footer className="px-4 pb-6 text-xs text-content-muted lg:px-8">
          {employee?.full_name ? `${employee.full_name} - ${employee.employee_code}` : user?.username ?? ''}
        </footer>
      </div>

      <Dialog open={menuOpen} onClose={() => setMenuOpen(false)} title="Admin navigation" size="sm">
        <GroupNav groups={groups} pathname={pathname} onNavigate={() => setMenuOpen(false)} unread={unread} />
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