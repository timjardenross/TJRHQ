import type { Metadata, Viewport } from 'next';
import { Source_Serif_4 } from 'next/font/google';
import './globals.css';
import { SITE_URL } from '@/lib/site';

// This is the internal ops portal (USS TJR) — deliberately its own brand,
// not the public marketing site's (@/lib/public-site is for the still-live
// /login and other publicly-indexable pages only). Previously this file
// imported PUBLIC_SITE_NAME et al., so every authenticated page (including
// /home) showed "TJR Mind & Body" in the tab title and favicon.
const OPS_PORTAL_NAME = 'TJR HQ';
const OPS_PORTAL_DESCRIPTION = 'USS TJR — Command Centre for missions, intelligence, and recovery operations.';

const sourceSerif = Source_Serif_4({
  subsets: ['latin'],
  weight: ['600', '700'],
  variable: '--font-serif',
  display: 'swap',
});

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: OPS_PORTAL_NAME,
    template: `%s | ${OPS_PORTAL_NAME}`,
  },
  applicationName: OPS_PORTAL_NAME,
  description: OPS_PORTAL_DESCRIPTION,
  authors: [{ name: 'Tim Jarden-Ross' }],
  creator: 'Tim Jarden-Ross',
  publisher: OPS_PORTAL_NAME,
  category: 'Productivity',
  robots: {
    index: false,
    follow: false,
  },
  // 2026-09-05: iPad-kiosk retrofit — manifest.webmanifest was only linked
  // from the (app) route group's layout, so "Add to Home Screen" on
  // captains-chair-workbench (outside that group, the real live dashboard
  // this session built the calendar/reminders/spoken-alerts cards onto)
  // never picked it up at all — no standalone/fullscreen mode, just a
  // regular Safari tab shortcut. appleWebApp is what iOS Safari actually
  // reads for "Add to Home Screen" fullscreen behavior.
  manifest: '/manifest.webmanifest',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'black-translucent',
    title: 'TJR HQ',
  },
  openGraph: {
    title: OPS_PORTAL_NAME,
    description: OPS_PORTAL_DESCRIPTION,
    url: SITE_URL,
    siteName: OPS_PORTAL_NAME,
    type: 'website',
  },
  twitter: {
    card: 'summary',
    title: OPS_PORTAL_NAME,
    description: OPS_PORTAL_DESCRIPTION,
  },
};

export const viewport: Viewport = {
  themeColor: '#F7F4EE',
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={sourceSerif.variable}>
      <body>
        {children}
      </body>
    </html>
  );
}
