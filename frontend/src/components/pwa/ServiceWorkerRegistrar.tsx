'use client';

import { useEffect, useState } from 'react';

/**
 * Registers the app-shell service worker and offers an explicit update prompt
 * (docs/07_UI_SPEC.md section 2 - PWA: app shell, static assets, offline page).
 */
export function ServiceWorkerRegistrar() {
  const [waitingWorker, setWaitingWorker] = useState<ServiceWorker | null>(null);

  useEffect(() => {
    if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;
    let cancelled = false;

    navigator.serviceWorker
      .register('/sw.js')
      .then((registration) => {
        if (cancelled) return;
        if (registration.waiting) setWaitingWorker(registration.waiting);
        registration.addEventListener('updatefound', () => {
          const installing = registration.installing;
          if (!installing) return;
          installing.addEventListener('statechange', () => {
            if (installing.state === 'installed' && navigator.serviceWorker.controller) {
              setWaitingWorker(installing);
            }
          });
        });
      })
      .catch(() => {
        // Registration failure must never break the app; the app works online without it.
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (!waitingWorker) return null;

  return (
    <div
      role="status"
      data-testid="sw-update-prompt"
      className="fixed inset-x-2 bottom-2 z-50 mx-auto flex max-w-md items-center justify-between gap-3 rounded-card border border-surface-border bg-surface px-3 py-2 text-sm shadow-lg"
    >
      <span>A new version is available.</span>
      <button
        type="button"
        className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-fg"
        onClick={() => {
          waitingWorker.postMessage({ type: 'SKIP_WAITING' });
          window.location.reload();
        }}
      >
        Reload
      </button>
    </div>
  );
}