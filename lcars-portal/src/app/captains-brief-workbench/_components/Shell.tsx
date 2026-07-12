'use client';

// Standalone brand shell for the Captain's Brief Workbench — same wb- design
// system and layout as the Advisory / Human Systems / Intelligence Workbench
// Shells, branded for the Captain's Brief. Deliberately no LCARS app chrome
// (this route lives outside the (app) group), matching the workbench precedent.
import Link from 'next/link';
import { ReactNode } from 'react';

export { Card } from '@/components/ui';

export function Shell({
  title,
  eyebrow = 'Captain’s Brief',
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
            href="/captains-brief-workbench"
            className="grid h-8 w-8 place-items-center rounded-full bg-wb-sage-deep text-[14px] font-semibold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-ink"
            aria-label="Captain’s Brief Workbench home"
          >
            TJR
          </Link>
          <div className="leading-tight">
            <div className="font-serif text-[17px]">{title}</div>
            <div className="text-[11px] uppercase tracking-[0.14em] text-wb-ink2">{eyebrow}</div>
          </div>
          <div className="ml-auto">{right}</div>
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
          USS TJR · Captain’s Brief · assembled on request — reports the signals received, not an all-clear
        </p>
      </main>
    </div>
  );
}
