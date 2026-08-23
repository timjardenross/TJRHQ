'use client';

// Canonical standalone brand shell for every *-workbench route (no LCARS
// app chrome - these routes live outside the (app) group by design).
//
// Consolidated 2026-07-18 (WORKBENCH-REVIEW.md H9/H12): 6 workbenches each
// forked this component, byte-identical except for homeHref/ariaLabel/
// tagline/default eyebrow - confirmed by diffing every pair before merging.
// 3 more workbenches (mission, comms, self-improvement-findings) reached
// into intelligence-workbench's own folder to reuse its copy directly,
// which meant they silently inherited intelligence-workbench's OWN
// homeHref ("/intelligence-workbench") and tagline ("Operational Resilience
// Intelligence · Phase B") - a real, live branding/navigation bug this
// consolidation also fixed.
//
// 2026-08 UX review follow-up: the logo previously linked to `homeHref`,
// a per-page prop every caller set to ITS OWN route - so "click the logo
// to go home" was a no-op refresh on every workbench, not an escape hatch.
// /workbenches is now the one canonical home (root '/' redirects there;
// /home is retired - see workbenches/page.tsx and home/page.tsx's own
// comments), so the logo always points there and homeHref/homeAriaLabel
// are gone from this component's contract entirely, not just unused.
//
// Also added: a persistent workbench switcher (`LIVE_WORKBENCHES`, shared
// with the hub so the two lists can't drift) so moving between workbenches
// no longer requires a round trip through the hub page every time, and a
// dedicated `tabs` slot so a page's DomainToggle gets a full-width row
// instead of being squeezed into the header's status-text corner.
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { ReactNode } from 'react';
import { LIVE_WORKBENCHES } from '@/lib/workbenches';
import { MobileCommandBar } from '@/components/MobileCommandBar';
import { QuickCapture } from './QuickCapture';

const GLOBAL_HOME = '/workbenches';

function WorkbenchSwitcher() {
  const router = useRouter();
  const pathname = usePathname();
  const current = LIVE_WORKBENCHES.find((w) => pathname?.startsWith(w.href))?.href ?? '';

  return (
    <select
      aria-label="Switch workbench"
      value={current}
      onChange={(e) => { if (e.target.value) router.push(e.target.value); }}
      className="rounded-md border border-wb-line bg-wb-surface px-2 py-1 text-[12px] text-wb-ink2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
    >
      {!current && <option value="" disabled>Switch workbench…</option>}
      {LIVE_WORKBENCHES.map((w) => (
        <option key={w.href} value={w.href}>{w.title}</option>
      ))}
    </select>
  );
}

export function WorkbenchShell({
  title,
  eyebrow = 'Operational Resilience',
  tagline,
  right,
  tabs,
  back,
  wide = false,
  children,
}: {
  title: string;
  eyebrow?: string;
  /** Footer tagline, e.g. "USS TJR · Capture · Review-first — nothing auto-routes without your say". */
  tagline: string;
  right?: ReactNode;
  /** Full-width row below the header, for a page's DomainToggle — keeps the
   * header's own `right` slot free for lightweight status text only. */
  tabs?: ReactNode;
  back?: { href: string; label: string };
  /** Opt into max-w-7xl instead of the default max-w-4xl — for multi-column
   * board/kanban layouts (e.g. Content Workbench) that feel cramped at the
   * standard reading-width shell every other workbench uses. Off by default
   * so this stays a per-page choice, not a blanket layout change. */
  wide?: boolean;
  children: ReactNode;
}) {
  const shellWidth = wide ? 'max-w-7xl' : 'max-w-4xl';
  return (
    <div className="min-h-[100dvh] bg-wb-bg font-sans text-wb-ink antialiased">
      <a
        href="#wb-main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-wb-ink focus:px-3 focus:py-2 focus:text-[13px] focus:text-white"
      >
        Skip to content
      </a>
      <header className="border-b border-wb-line bg-wb-bg/80 backdrop-blur">
        <div className={`mx-auto flex ${shellWidth} items-center gap-3 px-6 py-4`}>
          <Link
            href={GLOBAL_HOME}
            className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-wb-sage-deep text-[14px] font-semibold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-ink"
            aria-label="Workbenches home"
          >
            TJR
          </Link>
          <div className="leading-tight">
            <div className="font-serif text-[17px]">{title}</div>
            <div className="text-[11px] uppercase tracking-[0.14em] text-wb-ink2">{eyebrow}</div>
          </div>
          <span className="ml-auto flex items-center gap-3 text-[12px] text-wb-ink2">
            {right}
            <WorkbenchSwitcher />
          </span>
        </div>
        {tabs && (
          <div className={`mx-auto ${shellWidth} px-6 pb-4`}>
            {tabs}
          </div>
        )}
      </header>
      <main id="wb-main" className={`mx-auto ${shellWidth} px-6 py-8`}>
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
          {tagline}
        </p>
      </main>
      <QuickCapture />
      <MobileCommandBar />
    </div>
  );
}
