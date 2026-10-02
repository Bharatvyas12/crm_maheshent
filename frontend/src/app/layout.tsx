import type { Metadata, Viewport } from 'next';
import './globals.css';
import { Providers } from './providers';
import { ServiceWorkerRegistrar } from '@/components/pwa/ServiceWorkerRegistrar';
import { InstallPrompt } from '@/components/pwa/InstallPrompt';

export const metadata: Metadata = {
  title: 'Workforce CRM',
  description: 'Employee operations, attendance, tasks, orders and payroll.',
  applicationName: 'Workforce CRM',
  manifest: '/manifest.webmanifest',
  appleWebApp: { capable: true, statusBarStyle: 'default', title: 'Workforce CRM' },
  icons: {
    icon: '/icons/icon.svg',
    apple: '/icons/icon.svg'
  }
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  themeColor: '#1d4ed8'
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-[70] focus:rounded focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-fg"
        >
          Skip to main content
        </a>
        <Providers>
          {children}
          <ServiceWorkerRegistrar />
          <InstallPrompt />
        </Providers>
      </body>
    </html>
  );
}