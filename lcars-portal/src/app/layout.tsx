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
    // 'black-translucent' (first pass) makes iOS standalone-mode content
    // flow underneath the status bar — that's what pushed
    // WorkbenchShell's top-right workbench-switcher dropdown into/behind
    // the status bar area, unreachable, on the real device. 'default'
    // keeps the status bar opaque and content below it, no manual
    // safe-area-inset-top math needed.
    statusBarStyle: 'default',
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
  // Endeavour 27: was #F7F4EE (the old Archive theme's bg) — the app's
  // default surface is now the dark Command/Focus navy.
  themeColor: '#0B1E2E',
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
};

// Reads the saved motion preference and sets it on <html> synchronously,
// BEFORE hydration/first paint, so a Captain with Motion: Reduced never
// sees one frame of animation. Deliberately a tiny inline script, not a
// dependency — the actual requirement is one localStorage read and one
// attribute set.
//
// Endeavour 27 (USS-TJR-MSN-0394): the 5-theme half of this script
// (data-theme, tjr-hq-theme) is retired along with lib/theme.ts and
// ThemeSelector.tsx — the dark Command/Focus vs. light Read surface is now
// a static per-route classification (WorkbenchShell's `mode` prop ->
// [data-wb-mode] in globals.css), known at render time, so it needs no
// anti-flash script of its own the way a client-toggled preference did.
const MOTION_INIT_SCRIPT = `
(function () {
  try {
    var m = localStorage.getItem('tjr-hq-motion');
    if (m === 'reduced') {
      document.documentElement.setAttribute('data-motion', 'reduced');
    }
  } catch (e) {}
})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={sourceSerif.variable}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: MOTION_INIT_SCRIPT }} />
      </head>
      <body>
        {children}
      </body>
    </html>
  );
}
