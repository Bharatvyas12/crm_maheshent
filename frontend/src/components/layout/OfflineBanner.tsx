'use client';

import { useEffect, useState } from 'react';

/**
 * Global connectivity banner (docs/07_UI_SPEC.md section 5.5). Read-only screens may keep
 * serving cached data; mutations fail fast with a clear message and are never queued silently.
 */
export function OfflineBanner() {
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    const update = () => setOffline(!navigator.onLine);
    update();
    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    return () => {
      window.removeEventListener('online', update);
      window.removeEventListener('offline', update);
    };
  }, []);

  if (!offline) return null;

  return (
    <div role="status" data-testid="offline-banner" className="sticky top-0 z-40 w-full bg-warning-soft px-4 py-2 text-center text-sm font-medium text-warning">
      You are offline. Showing last loaded data; actions that change records are unavailable until you reconnect.
    </div>
  );
}