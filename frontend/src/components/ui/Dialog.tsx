'use client';

import { useCallback, useEffect, useRef, type ReactNode } from 'react';
import { Button } from './Button';

const FOCUSABLE = 'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Accessible modal dialog. Traps focus, restores it on close and closes on Escape
 * (docs/07_UI_SPEC.md section 12).
 */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = 'md',
  testId
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children?: ReactNode;
  footer?: ReactNode;
  size?: 'sm' | 'md' | 'lg';
  testId?: string;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (!open) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key === 'Tab' && panelRef.current) {
        const nodes = Array.from(panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((node) => node.offsetParent !== null);
        if (nodes.length === 0) return;
        const first = nodes[0];
        const last = nodes[nodes.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    },
    [open]
  );

  useEffect(() => {
    if (!open) return;
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    document.addEventListener('keydown', handleKeyDown);
    const timer = window.setTimeout(() => {
      if (!panelRef.current) return;
      if (panelRef.current.contains(document.activeElement)) return;
      const input = panelRef.current.querySelector<HTMLElement>('input:not([disabled]), textarea:not([disabled]), select:not([disabled])');
      const target = input || panelRef.current.querySelector<HTMLElement>(FOCUSABLE);
      target?.focus();
    }, 50);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      window.clearTimeout(timer);
      previouslyFocused.current?.focus();
    };
  }, [open, handleKeyDown]);

  if (!open) return null;

  const widths = { sm: 'max-w-sm', md: 'max-w-lg', lg: 'max-w-3xl' } as const;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-3 sm:p-4 overflow-y-auto">
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        aria-describedby={description ? 'dialog-description' : undefined}
        data-testid={testId}
        className={`relative w-full ${widths[size]} my-auto max-h-[85vh] flex flex-col min-h-0 animate-slide-up rounded-card bg-surface p-5 shadow-2xl overflow-hidden border border-border/40`}
      >
        <div className="flex items-start justify-between gap-4 pb-3 flex-shrink-0 border-b border-border/40">
          <div>
            <h2 id="dialog-title" className="text-lg font-semibold text-content">
              {title}
            </h2>
            {description ? (
              <p id="dialog-description" className="mt-1 text-sm text-content-muted">
                {description}
              </p>
            ) : null}
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close dialog">
            Close
          </Button>
        </div>
        {children ? <div className="flex-1 min-h-0 overflow-y-auto py-4 pr-2">{children}</div> : null}
        {footer ? <div className="pt-3 border-t border-border/40 flex flex-wrap justify-end gap-2 flex-shrink-0">{footer}</div> : null}
      </div>
    </div>
  );
}