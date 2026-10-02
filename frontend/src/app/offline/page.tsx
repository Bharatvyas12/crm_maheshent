export const metadata = { title: 'Offline - Workforce CRM' };

export default function OfflinePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-3 px-6 text-center">
      <h1 className="text-xl font-semibold">You are offline</h1>
      <p className="max-w-sm text-sm text-content-muted">
        Attendance, order claiming, submissions and financial actions cannot be queued while offline. Reconnect and try
        again - your retry keeps the same idempotency key so a request that already succeeded is not duplicated.
      </p>
    </main>
  );
}