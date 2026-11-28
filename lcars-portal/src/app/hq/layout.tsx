import type { Metadata, Viewport } from 'next';
import { notFound } from 'next/navigation';
import { isHqEnabled } from '@/lib/hq/flag';
import { HqShell } from './_components/HqShell';
import './hq.css';

// HQ Workbench: a separate, parallel presentation layer over existing
// capabilities. Own shell and navigation, isolated from every other
// workbench. Gated by HQ_WORKBENCH_ENABLED (server-side, default off):
// when the flag is off this whole route group returns the standard 404.
// force-dynamic so the flag is read per request, never baked in at build.
export const dynamic = 'force-dynamic';

export const metadata: Metadata = {
  title: 'HQ',
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  themeColor: '#f2f5f6',
};

export default function HqLayout({ children }: { children: React.ReactNode }) {
  if (!isHqEnabled()) notFound();
  return <HqShell>{children}</HqShell>;
}
