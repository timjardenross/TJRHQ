'use client';

// Standalone brand shell for the Intelligence Workbench (no LCARS app chrome).
import Link from 'next/link';
import { ReactNode } from 'react';

export function Shell({
  title,
  eyebrow = 'Operational Resilience',
  right,
  back,
  children,
}: {
  title: string;
  eyebrow?: string;
  right?: ReactNode;
  back?: { href: string; label: string };
  children: ReactNode;
}) {
  return (
    <div className="min-h-[100dvh] bg-wb-bg font-sans text-wb-ink antialiased">
      <a
        href="#wb-main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-wb-ink focus:px-3 focus:py-2 focus:text-[13px] focus:text-white"
      >
        Skip to content
      </a>
      <header className="border-b border-wb-line bg-wb-bg/80 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-6 py-4">
          <Link
            href="/intelligence-workbench"
            className="grid h-8 w-8 place-items-center rounded-full bg-wb-sage-deep text-[14px] font-semibold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-ink"
            aria-label="Workbench home"
          >
            TJR
          </Link>
          <div className="leading-tight">
            <div className="font-serif text-[17px]">{title}</div>
            <div className="text-[11px] uppercase tracking-[0.14em] text-wb-ink2">{eyebrow}</div>
          </div>
          <span className="ml-auto text-[12px] text-wb-ink2">{right}</span>
        </div>
      </header>
      <main id="wb-main" className="mx-auto max-w-4xl px-6 py-8">
        {back && (
          <Link
            href={back.href}
            className="mb-4 inline-block text-[13px] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep"
          >
            ← {back.label}
          </Link>
        )}
        {children}
        <p className="mt-8 text-center text-[11px] text-wb-ink2">
          USS TJR · Operational Resilience Intelligence · Phase B
        </p>
      </main>
    </div>
  );
}

export function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <section className="mb-6 rounded-lg border border-wb-line bg-wb-surface p-6 shadow-sm">
      {title && <h2 className="mb-3 border-b border-wb-line pb-3 font-serif text-lg">{title}</h2>}
      {children}
    </section>
  );
}

export function riskClass(r: string | null | undefined) {
  const v = (r ?? '').toUpperCase();
  // *-on text hues are AA-safe (>=4.5:1) on the light tint backgrounds.
  if (v === 'RED' || v === 'HIGH') return 'bg-wb-crit/15 text-wb-crit-on';
  if (v === 'AMBER' || v === 'MEDIUM') return 'bg-wb-warn/15 text-wb-warn-on';
  if (v === 'GREEN' || v === 'LOW') return 'bg-wb-ok/15 text-wb-ok-on';
  return 'bg-wb-line text-wb-ink2';
}

export function RiskPill({ value }: { value: string | null | undefined }) {
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${riskClass(value)}`}>
      {value ?? '—'}
    </span>
  );
}
