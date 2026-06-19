import type { Metadata } from 'next';
import './globals.css';
import { LCARSHeader } from '@/components/LCARSHeader';
import { LCARSNav } from '@/components/LCARSNav';
import { SHIP } from '@/lib/mockData';

export const metadata: Metadata = {
  title: 'USS TJR — LCARS Portal',
  description:
    'Starship Endeavour LCARS command portal (Phase 1) — reusable LCARS-style dashboard for USS TJR.'
};

export default function RootLayout({
  children
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col px-3 py-3 md:px-5 md:py-5">
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
          <footer className="mt-6 flex flex-col items-start justify-between gap-2 border-t border-edge pt-4 text-xs text-lcars-muted md:flex-row md:items-center">
            <span>
              {SHIP.name} · {SHIP.registry}
            </span>
            <span className="uppercase tracking-[0.2em]">
              LCARS Portal · Phase 1 · Placeholder Data
            </span>
          </footer>
        </div>
      </body>
    </html>
  );
}
