import type { Metadata, Viewport } from 'next';
import './globals.css';
import { ServiceWorkerRegister } from '@/components/ServiceWorkerRegister';
import { SITE_URL } from '@/lib/site';

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: 'USS TJR — Command Centre',
  description:
    "Starship Endeavour mobile Command Centre — Captain's Chair, Quick Capture, XO Chat, Engineering Queue, and Push Alerts.",
  robots: {
    index: false,
    follow: false
  },
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

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <ServiceWorkerRegister />
        {children}
      </body>
    </html>
  );
}
