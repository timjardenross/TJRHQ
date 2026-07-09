import type { Metadata, Viewport } from 'next';
import './globals.css';
import { SITE_URL } from '@/lib/site';
import { PUBLIC_SITE_DESCRIPTION, PUBLIC_SITE_NAME, PUBLIC_SOCIAL_IMAGE_PATH } from '@/lib/public-site';

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: PUBLIC_SITE_NAME,
    template: `%s | ${PUBLIC_SITE_NAME}`,
  },
  applicationName: PUBLIC_SITE_NAME,
  description: PUBLIC_SITE_DESCRIPTION,
  authors: [{ name: 'Tim Jarden-Ross' }],
  creator: 'Tim Jarden-Ross',
  publisher: PUBLIC_SITE_NAME,
  category: 'Health and wellness education',
  robots: {
    index: false,
    follow: false,
  },
  openGraph: {
    title: PUBLIC_SITE_NAME,
    description: PUBLIC_SITE_DESCRIPTION,
    url: SITE_URL,
    siteName: PUBLIC_SITE_NAME,
    type: 'website',
    images: [
      {
        url: PUBLIC_SOCIAL_IMAGE_PATH,
        width: 1200,
        height: 630,
        alt: 'TJR Mind & Body social sharing image',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: PUBLIC_SITE_NAME,
    description: PUBLIC_SITE_DESCRIPTION,
    images: [PUBLIC_SOCIAL_IMAGE_PATH],
  },
  icons: {
    icon: [
      { url: '/icon-192.png', sizes: '192x192', type: 'image/png' },
      { url: '/icon-512.png', sizes: '512x512', type: 'image/png' },
    ],
    shortcut: [{ url: '/icon-192.png', type: 'image/png' }],
    apple: [{ url: '/apple-touch-icon.png', sizes: '180x180', type: 'image/png' }],
  },
};

export const viewport: Viewport = {
  themeColor: '#f5f7fb',
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {children}
      </body>
    </html>
  );
}
