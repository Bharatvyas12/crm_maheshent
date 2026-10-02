'use client';

import { useEffect, useState } from 'react';

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

/**
 * Install affordance shown only after the browser fires `beforeinstallprompt`, and only once the
 * user dismisses or accepts. It is never shown on first load.
 */
export function InstallPrompt() {
  const [event, setEvent] = useState<BeforeInstallPromptEvent | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    const handler = (e: Event) => {
      e.preventDefault();
      setEvent(e as BeforeInstallPromptEvent);
    };
    window.addEventListener('beforeinstallprompt', handler);
    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);

  if (!event || dismissed) return null;

  return (
    <div
      role="status"
      data-testid="install-prompt"
      className="fixed inset-x-2 bottom-2 z-40 mx-auto flex max-w-md items-center justify-between gap-3 rounded-card border border-surface-border bg-surface px-3 py-2 text-sm shadow-lg"
    >
      <span>Install Workforce CRM for faster access.</span>
      <span className="flex gap-2">
        <button
          type="button"
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-fg"
          onClick={async () => {
            await event.prompt();
            setDismissed(true);
          }}
        >
          Install
        </button>
        <button type="button" className="rounded-md border border-surface-border px-3 py-1.5 text-sm" onClick={() => setDismissed(true)}>
          Not now
        </button>
      </span>
    </div>
  );
}