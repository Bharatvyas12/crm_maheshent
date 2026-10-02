export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-muted px-4 py-10">
      <main id="main-content" className="w-full max-w-md">
        {children}
      </main>
    </div>
  );
}