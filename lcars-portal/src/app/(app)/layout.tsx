import type { Metadata, Viewport } from 'next';
import { LCARSHeader } from '@/components/LCARSHeader';
import { LCARSNav } from '@/components/LCARSNav';
import { LCARSBottomNav } from '@/components/LCARSBottomNav';
import { MobileCommandBar } from '@/components/MobileCommandBar';
import { SignOutButton } from '@/components/SignOutButton';
import { ServiceWorkerRegister } from '@/components/ServiceWorkerRegister';
import { SHIP } from '@/lib/mockData';

export const metadata: Metadata = {
  title: 'USS TJR Command Centre',
  description:
    "Private LCARS command centre for USS TJR — Captain's Chair, missions, intelligence, and recovery operations.",
  robots: {
    index: false,
    follow: false,
  },
  manifest: '/manifest.webmanifest',
  applicationName: 'USS TJR Command Centre',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'black-translucent',
    title: 'Endeavour',
  },
};

export const viewport: Viewport = {
  themeColor: '#f5f7fb',
};

/** Compute a Trek-style stardate: YYYY.DDD where DDD is the 3-digit day-of-year. */
function computeStardate(): string {
  const now = new Date();
  const start = new Date(now.getFullYear(), 0, 0);
  const diff = now.getTime() - start.getTime();
  const oneDay = 1000 * 60 * 60 * 24;
  const dayOfYear = Math.floor(diff / oneDay);
  return `${now.getFullYear()}.${String(dayOfYear).padStart(3, '0')}`;
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-dvh bg-[#f5f7fb]">
      <div className="mx-auto flex min-h-dvh max-w-[1600px] flex-col px-3 py-3 pb-24 md:px-5 md:py-5 lg:pb-5">
        <ServiceWorkerRegister />
        <LCARSHeader
          ship={SHIP.name}
          registry={SHIP.registry}
          stardate={computeStardate()}
          pageTitle="USS TJR — Starship Endeavour"
        />
        <div className="mt-4 flex flex-1 flex-col gap-4 lg:flex-row">
          <LCARSNav />
          <main className="flex-1">{children}</main>
        </div>
        <LCARSBottomNav />
        <MobileCommandBar />
        <footer className="mt-4 flex flex-col items-start justify-between gap-2 border-t border-[#d9e1f0] pt-4 text-xs text-[#61718c] md:flex-row md:items-center">
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
    </div>
  );
}
