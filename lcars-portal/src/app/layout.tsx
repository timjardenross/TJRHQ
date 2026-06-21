import type { Metadata, Viewport } from 'next';
import './globals.css';
import { LCARSHeader } from '@/components/LCARSHeader';
import { LCARSNav } from '@/components/LCARSNav';
import { LCARSBottomNav } from '@/components/LCARSBottomNav';
import { MobileCommandBar } from '@/components/MobileCommandBar';
import { ServiceWorkerRegister } from '@/components/ServiceWorkerRegister';
import { SignOutButton } from '@/components/SignOutButton';
import { SHIP } from '@/lib/mockData';

export const metadata: Metadata = {
  title: 'USS TJR — Command Centre',
  description:
    'Starship Endeavour mobile Command Centre — Captain’s Chair, Quick Capture, XO Chat, Engineering Queue, and Push Alerts.',
  manifest: '/manifest.webmanifest',
  applicationName: 'USS TJR Command Centre',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'black-translucent',
    title: 'Endeavour'
  },
  icons: {
    icon: [
      { url: '/icon-192.png', sizes: '192x192', type: 'image/png' },
      { url: '/icon-512.png', sizes: '512x512', type: 'image/png' }
    ],
    apple: [{ url: '/apple-touch-icon.png', sizes: '180x180', type: 'image/png' }]
  }
};

export const viewport: Viewport = {
  themeColor: '#05070e',
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover'
};

export default function RootLayout({
  children
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <ServiceWorkerRegister />
        <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col px-3 py-3 pb-24 md:px-5 md:py-5 lg:pb-5">
          <LCARSHeader
            ship={SHIP.name}
            registry={SHIP.registry}
            stardate={SHIP.stardate}
            pageTitle="USS TJR — Starship Endeavour"
          />
          <div className="mt-4 flex flex-1 flex-col gap-4 lg:flex-row">
            <LCARSNav />
            <main className="flex-1">{children}</main>
          </div>
          <LCARSBottomNav />
          <MobileCommandBar />
          <footer className="mt-4 flex flex-col items-start justify-between gap-2 border-t border-edge pt-4 text-xs text-lcars-muted md:flex-row md:items-center">
            <span>
              {SHIP.name} · {SHIP.registry}
            </span>
            <div className="flex items-center gap-4">
              <span className="uppercase tracking-[0.2em]">
                LCARS Portal · ROS-001 v1.1
              </span>
              <SignOutButton />
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
