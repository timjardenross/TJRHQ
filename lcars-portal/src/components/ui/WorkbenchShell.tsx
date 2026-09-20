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
import { Settings } from 'lucide-react';
import { LIVE_WORKBENCHES, PRIMARY_ACTIONS } from '@/lib/workbenches';
import { MobileCommandBar } from '@/components/MobileCommandBar';
import { NumberOne } from './NumberOne';
import { QuickCapture } from './QuickCapture';
import { Sidebar } from './Sidebar';
import { AttentionControls } from '@/components/AttentionControls';
import { ActionHistoryPanel } from '@/components/FocusLane';

const GLOBAL_HOME = '/workbenches';

function WorkbenchSwitcher() {
  const router = useRouter();
  const pathname = usePathname();
  const current = LIVE_WORKBENCHES.find((w) => pathname?.startsWith(w.href))?.href ?? '';

  return (
    // Mission 7 item 1 (Phase 14 finding, Phase 15 fix): this <select> had
    // no width constraint, so its closed-state face sized to the longest
    // workbench title (up to 25 chars, "Technical OSINT Workbench") —
    // confirmed overflowing the viewport at 375px on 20 of 21 workbenches.
    // max-w + truncate caps the closed face only; the dropdown's own open
    // list still shows full titles untruncated (native <select> behaviour).
    <select
      aria-label="Switch workbench"
      value={current}
      onChange={(e) => { if (e.target.value) router.push(e.target.value); }}
      className="w-[92px] max-w-[92px] truncate rounded-md border border-wb-line bg-wb-surface px-2 py-1 text-[12px] text-wb-ink2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep sm:w-auto sm:max-w-[180px]"
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
  minimal = false,
  mode = 'focus',
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
  /** Mission 4 (Executive Function & Regulation): suppress Sidebar, the
   * workbench switcher, back-link and tagline while the Captain is inside
   * a single active-execution moment (Ready Room's ActiveTaskView) — one
   * fewer decision surface competing for attention mid-task. Opt-in, off
   * by default, so every other workbench is unaffected. Settings stay
   * reachable (never trap the Captain), QuickCapture/MobileCommandBar
   * stay mounted. */
  minimal?: boolean;
  /** Endeavour 27 (USS-TJR-MSN-0394): 'command' and 'focus' share the dark
   * Command/Focus surface (differ by density/layout, not colour — mission
   * §1.1), 'read' switches to the light reading surface via
   * [data-wb-mode='read'] in globals.css. Defaults to 'focus' — the
   * majority of existing action/execution workbenches — so unclassified
   * pages don't silently go light. Set explicitly per mission §1.8's
   * classification when migrating a page. */
  mode?: 'command' | 'focus' | 'read';
  children: ReactNode;
}) {
  const shellWidth = wide ? 'max-w-7xl' : 'max-w-4xl';
  const pathname = usePathname();
  const searchParams = new URLSearchParams(typeof window !== 'undefined' ? window.location.search : '');
  const from = searchParams.get('from');
  const item = searchParams.get('item');
  const originLabel = from === 'captains-chair' ? 'Captain’s Chair' : from === 'hub' ? 'LifeOS Hub' : from;
  const originHref = from === 'captains-chair' ? '/captains-chair-workbench' : from === 'hub' ? '/hub' : null;
  const primaryAction = LIVE_WORKBENCHES.find((w) => pathname?.startsWith(w.href)) ? PRIMARY_ACTIONS[LIVE_WORKBENCHES.find((w) => pathname?.startsWith(w.href))!.href] : null;
  return (
    <div className="min-h-[100dvh] bg-wb-bg font-sans text-wb-ink antialiased">
      <a
        href="#wb-main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-wb-ink focus:px-3 focus:py-2 focus:text-[13px] focus:text-white"
      >
        Skip to content
      </a>
      {/* Adaptive Themes mission (2026-09-05): Sidebar is global chrome on
          every *-workbench page, not just Home — Captain's explicit call.
          xl:flex on Sidebar itself, no extra breakpoint class needed here.
          Mission 4: hidden in `minimal` mode (see prop doc above).
          Endeavour 27 (USS-TJR-MSN-0394) Stream A/B: `data-wb-mode` scopes
          to this inner column only, not the outer wrapper -- mission §1.1
          is explicit that Read mode swaps the reading pane's surface
          lightness while "the header/sidebar chrome stays dark navy" (also
          confirmed directly against Image 1's own Briefs panel). Scoping it
          on the whole shell made Sidebar go light too on first
          implementation -- a real bug, caught via live verification, not
          left in. */}
      <div className="flex">
        {!minimal && <Sidebar />}
        {/* text-wb-ink re-declared here (not just relying on inheriting
            the outer wrapper's already-computed colour): `color` inherits
            the parent's COMPUTED value, not a live re-evaluation of
            var(--wb-ink) -- without a fresh declaration inside this scope,
            title text (and anything else with no colour class of its own)
            silently inherited the outer wrapper's dark-mode ink, invisible
            against this div's light Read-mode background. Same class of
            bug as the bg-wb-bg/80 fix above, caught the same way. */}
        <div data-wb-mode={mode} className={`min-w-0 flex-1 bg-wb-bg text-wb-ink wb-mode-${mode}`}>
          {/* Endeavour 27 Stream B, found via live verification: `bg-wb-bg/80`
              never actually rendered a translucent fill -- Tailwind's
              opacity modifier needs an RGB-channel CSS var (e.g.
              `--wb-bg-rgb: 11 30 46`), not a plain hex var like `--wb-bg`,
              so it silently resolved to fully transparent. Invisible before
              this mission (this header sits on the same solid colour as
              everything behind it in the old single-surface system), but a
              real bug once Read mode wants this header genuinely lighter
              than the dark chrome around it. `backdrop-blur` was already a
              no-op too -- header isn't `sticky`/`fixed`, nothing scrolls
              underneath it. Solid bg-wb-bg is the correct, simpler fix. */}
          <header className="border-b border-wb-line bg-wb-bg">
            <div className={`mx-auto flex ${shellWidth} flex-wrap items-center gap-3 px-6 py-4`}>
              <Link
                href={GLOBAL_HOME}
                className="endeavour-brand-mark h-9 w-9 shrink-0 text-[13px] font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-ink xl:hidden"
                aria-label="Workbenches home"
              >
                △
              </Link>
              <div className="leading-tight">
                <h1 className="font-serif text-[17px]">{title}</h1>
                <div className="text-[11px] uppercase tracking-[0.14em] text-wb-ink2">{eyebrow}</div>
              </div>
              {/* Mission 7 item 1 (Phase 15): flex-wrap here is the second
                  layer of the mobile-overflow fix — even with both <select>s
                  now width-capped, this gives the cluster somewhere to go
                  (wrap to its own line) rather than force horizontal
                  scroll, on whatever narrower screen turns up next. */}
              <span className="ml-auto flex flex-wrap items-center justify-end gap-2 text-[12px] text-wb-ink2">
                {right}
                {/* Settings Page Redesign mission §23: Sidebar (xl+) already
                    links to /settings, but Sidebar is hidden below xl and
                    MobileCommandBar's 3 MVP tabs don't cover it either —
                    without this, mobile/tablet had no path to Settings at
                    all short of typing the URL. xl:hidden mirrors the mobile
                    home logo above so it disappears exactly when Sidebar
                    takes over. */}
                <Link
                  href="/settings"
                  aria-label="Settings"
                  className="grid h-8 w-8 shrink-0 place-items-center rounded-md text-wb-ink2 hover:bg-wb-surface-raised hover:text-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep xl:hidden"
                >
                  <Settings className="h-4 w-4" aria-hidden />
                </Link>
                {!minimal && <WorkbenchSwitcher />}
              </span>
            </div>
            {tabs && !minimal && (
              <div className={`mx-auto ${shellWidth} px-6 pb-4`}>
                {tabs}
              </div>
            )}
          </header>
          <main id="wb-main" className={`mx-auto ${shellWidth} px-4 py-6 pb-28 sm:px-6 sm:py-8 sm:pb-28 xl:pb-8`}>
            {!minimal && primaryAction && <div className="mb-4"><Link href={primaryAction.href} className="inline-flex min-h-11 items-center rounded-md bg-wb-sage-deep px-4 py-2.5 text-[13px] font-semibold text-white transition hover:bg-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">{primaryAction.label} →</Link></div>}
            {!minimal && <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><AttentionControls label="Attention" /><ActionHistoryPanel /></div>}
            {originLabel && pathname !== originHref && (
              <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-wb-line bg-wb-surface px-3 py-2 text-[11px] text-wb-ink2" role="status">
                <span>Opened from {originLabel}{item ? ` · item ${item}` : ''}</span>
                {originHref && <Link href={originHref} className="font-semibold text-wb-sage underline underline-offset-2">Return to source →</Link>}
              </div>
            )}
            {back && !minimal && (
              <Link
                href={back.href}
                className="mb-4 inline-block text-[13px] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep"
              >
                ← {back.label}
              </Link>
            )}
            {children}
            {!minimal && (
              <p className="mt-8 text-center text-[11px] text-wb-ink2">
                {tagline}
              </p>
            )}
          </main>
        </div>
      </div>
      <QuickCapture />
      <NumberOne />
      <MobileCommandBar />
    </div>
  );
}
