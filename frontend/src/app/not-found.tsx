import Link from 'next/link';

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="max-w-sm text-sm text-content-muted">
        The page you requested does not exist, or you do not have access to it.
      </p>
      <Link className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-fg" href="/">
        Go to your dashboard
      </Link>
    </main>
  );
}