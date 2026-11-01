import type { Metadata, Viewport } from 'next';
import { LegacyFrame } from './_components/LegacyFrame';
import { ServiceWorkerRegister } from '@/components/ServiceWorkerRegister';

export const metadata: Metadata = {
  title: 'TJR HQ',
  description:
    "Private TJR HQ command centre — missions, intelligence, and recovery operations.",
  robots: {
    index: false,
    follow: false,
  },
  manifest: '/manifest.webmanifest',
  applicationName: 'TJR HQ',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'black-translucent',
    title: 'Endeavour',
  },
};

export const viewport: Viewport = {
  themeColor: '#F5F7FA',
};

// Stage C: the older command-centre routes (/missions, /medical, /alerts ...) keep their URLs
// but now sit in the same shell as every workbench (Sidebar, header, mobile bar, theme).
// Their page content is unchanged; it is restyled page by page afterwards.
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <ServiceWorkerRegister />
      <LegacyFrame>{children}</LegacyFrame>
    </>
  );
}
