import { AuthGuard } from '@/components/layout/AuthGuard';
import { EmployeeShell } from '@/components/layout/EmployeeShell';

export default function EmployeeLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <EmployeeShell>{children}</EmployeeShell>
    </AuthGuard>
  );
}