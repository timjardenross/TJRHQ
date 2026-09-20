'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import { useAlertCount } from '@/lib/useAlerts';
import type { NavHref } from '@/lib/nav';
import { Modal } from './ui/Modal';

/**
 * MobileCommandBar — the Captain-facing MVP navigation (MSN-IOS-001 WP7).
 *
 * Fixed, thumb-friendly bottom tab bar. This is the ONLY nav rendered on
 * mobile/tablet (LCARSNav and LCARSBottomNav are `xl:`-gated, desktop-only)
 * — a page not listed here is unreachable below 1280px, full stop.
 *
 * Mission 7 §17/§45 fix (2026-09-19): tab 1 pointed at /workbenches with a
 * home glyph (⌂), while desktop Sidebar's own Home entry — added the same
 * day as this bar's last edit — points at /hub. Two different pages both
 * calling themselves "Home" depending on device width is exactly the kind
 * of topology the Captain shouldn't have to notice. /hub is the confirmed
 * front door (root '/' redirects there; see app/page.tsx) and the one
 * place the core Captain journey (Needs You -> act, "Where was I?", "Too
 * much", ...) actually lives, so it wins. The full directory doesn't lose
 * reachability: every WorkbenchShell page's top-left logo (visible below
 * `xl`) already links to /workbenches, including from /hub itself.
 * `xl:hidden` (2026-09-05, was `lg:hidden`): this component is also
 * unconditionally mounted inside WorkbenchShell (~20 non-(app) workbenches,
 * including captains-chair-workbench), which has no desktop nav equivalent
 * of its own — only a tiny "switch workbench" dropdown. At `lg:hidden`,
 * every WorkbenchShell page lost real navigation entirely between 1024px
 * and desktop — an iPad Air 4 in landscape (1180px CSS width) sat right in
 * that band. LCARSNav/LCARSBottomNav's own breakpoints were bumped to
 * `xl:` in the same pass so the (app)-group pages' desktop nav still hands
 * off cleanly (now at 1280 instead of 1024) rather than both nav systems
 * showing at once in the new gap between them.
 *
 * Endeavour 27 (USS-TJR-MSN-0394 §1.2/Stream B3, Captain-directed
 * redesign, 2026-09-20): replaced with the mockup's 4-item set — Hub /
 * Ready / Ask / More. "Capture" is dropped, not just renamed — it
 * duplicated the always-mounted QuickCapture floating button
 * (components/ui/QuickCapture.tsx: "Mounted once inside WorkbenchShell
 * (every workbench) and once on the hub, so a capture is always at most
 * one click away"), giving mobile two paths to the same captureItem()
 * pipeline. "Ready" points at /physical-readiness (renamed tab label to
 * match the mockup; same destination as the old "Readiness" tab). "Ask"
 * routes to /advisory-workbench?advisor=number_one — the same deep link
 * Hub's own "Open a full Number One session" link uses (app/hub/page.tsx)
 * to reach ConsultView's persisted, multi-turn Number One thread; the
 * ambient NumberOne.tsx floating widget (bottom-left, also unconditionally
 * mounted) already covers the quick ephemeral asks, so this tab is the
 * "different job" Hub's own comment describes, not a new destination.
 * "More" opens a small local sheet (Modal, same primitive QuickCapture/
 * NumberOne already use) rather than linking straight to /workbenches:
 * Physical Readiness was a deliberately-kept primary-nav item before this
 * redesign (see the old TABS comment below) and needed to stay one tap
 * away from the sheet, not buried in the ~20-item full directory the
 * WorkbenchShell header logo already links to below `xl`. The sheet
 * surfaces Physical Readiness directly plus a link to the full Workbenches
 * directory for everything else. This destination choice (a local sheet,
 * not a new route) was not dictated by the mission doc — flagged for
 * Captain confirmation in §6 Reporting.
 *
 * Colours converted from hardcoded hex (`bg-white/95`, `text-[#243b7a]`/
 * `text-[#61718c]`) to the `wb-*` tokens every other workbench uses
 * (globals.css) in the same pass, per §1.2's explicit direction.
 *
 * Real-Captain-walkthrough revision (2026-07-10): restyled on the real
 * public-site brand tokens - one accent colour for the active tab, not
 * five decorative department colours.
 */

interface Tab {
  href: NavHref;
  label: string;
  glyph: string;
}

// Pre-Endeavour-27 history (kept for context, superseded above):
// 2026-07-18: /home, /decide, /ask were decommissioned in favor of
// /workbenches as the new home (lib/nav.ts) but this bar was never
// updated, which broke the build (stale hrefs failed the NavHref type
// check) and, worse, left mobile with zero path back to the new home -
// this is the ONLY nav on mobile (see doc comment above). Capture and
// Physical Readiness are kept - both are real task tools (docs/
// INVENTORY.md: MIGRATE/TASK-TOOL), not dashboards, and mobile is their
// primary device with no other nav path once NAV_SECTIONS stopped
// listing them.
//
// Mission 7: slot 1 repointed /workbenches -> /hub (see doc comment
// above) — same reasoning that made root '/' redirect to /hub over
// /workbenches, now applied consistently on mobile too.
const TABS: Tab[] = [
  { href: '/hub', label: 'Hub', glyph: '⌂' },
  { href: '/physical-readiness', label: 'Ready', glyph: '✚' },
];

// "Ask" carries a query string (?advisor=number_one), so it isn't one of
// NavHref's plain-route literals (lib/nav.ts) — typed and rendered
// separately from TABS rather than loosening NavHref for one entry.
const ASK_HREF = '/advisory-workbench?advisor=number_one';

// "More" quick links — surfaced directly in the sheet (one tap once open),
// not buried in the full ~20-item /workbenches directory. Physical
// Readiness first: it was a deliberately-kept primary-nav item before this
// redesign (see history comment above) and must not strand.
const MORE_LINKS: { href: NavHref; label: string; glyph: string; description: string }[] = [
  { href: '/physical-readiness', label: 'Physical Readiness', glyph: '✚', description: 'Training, recovery, capacity' },
  { href: '/workbenches', label: 'All Workbenches', glyph: '◊', description: 'The full directory' },
];

export function MobileCommandBar() {
  const pathname = usePathname();
  const [moreOpen, setMoreOpen] = useState(false);
  // Kept despite the Alerts tab being removed below: this hook's
  // `enableNotifications: true` option is what actually fires native
  // browser push notifications for critical/high alerts - this component
  // is documented as its "single global owner" (see file doc comment).
  // Dropping the call would silently break real notifications, not just
  // hide a badge. The count itself is no longer displayed anywhere.
  useAlertCount();

  const isAskActive = pathname.startsWith('/advisory-workbench');
  const isMoreActive = MORE_LINKS.some((l) => pathname === l.href || pathname.startsWith(l.href + '/'));

  return (
    <>
      <nav
        aria-label="Command MVP"
        className="fixed inset-x-0 bottom-0 z-50 border-t border-wb-line bg-wb-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur xl:hidden"
      >
        <ul className="mx-auto flex max-w-[640px]">
          {TABS.map((tab) => {
            const isActive = pathname === tab.href || pathname.startsWith(tab.href + '/');
            return (
              <li key={tab.href} className="flex-1">
                <Link
                  href={tab.href}
                  aria-current={isActive ? 'page' : undefined}
                  className={[
                    'relative flex min-h-[56px] flex-col items-center justify-center gap-0.5 py-2',
                    'focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-wb-sage-deep',
                    isActive ? 'text-wb-sage-deep' : 'text-wb-ink2',
                  ].join(' ')}
                  // Negative offset (vs. the app's usual positive
                  // focus-visible:outline-offset-2): this tab sits flush
                  // against the fixed bottom bar's own edge, so a positive
                  // offset would clip outside the bar/viewport. Same
                  // reasoning as settings/page.tsx's row items.
                >
                  <span className="relative text-xl leading-none" aria-hidden>
                    {tab.glyph}
                  </span>
                  <span className="text-[10px] font-bold uppercase tracking-[0.12em]">
                    {tab.label}
                  </span>
                  {isActive && (
                    <span className="absolute inset-x-3 top-0 h-0.5 rounded-full bg-current" aria-hidden />
                  )}
                </Link>
              </li>
            );
          })}
          <li className="flex-1">
            <Link
              href={ASK_HREF}
              aria-current={isAskActive ? 'page' : undefined}
              className={[
                'relative flex min-h-[56px] w-full flex-col items-center justify-center gap-0.5 py-2',
                'focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-wb-sage-deep',
                isAskActive ? 'text-wb-sage-deep' : 'text-wb-ink2',
              ].join(' ')}
            >
              <span className="relative text-xl leading-none" aria-hidden>
                ✦
              </span>
              <span className="text-[10px] font-bold uppercase tracking-[0.12em]">Ask</span>
              {isAskActive && (
                <span className="absolute inset-x-3 top-0 h-0.5 rounded-full bg-current" aria-hidden />
              )}
            </Link>
          </li>
          <li className="flex-1">
            <button
              type="button"
              onClick={() => setMoreOpen(true)}
              aria-haspopup="dialog"
              aria-expanded={moreOpen}
              className={[
                'relative flex min-h-[56px] w-full flex-col items-center justify-center gap-0.5 py-2',
                'focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-wb-sage-deep',
                isMoreActive || moreOpen ? 'text-wb-sage-deep' : 'text-wb-ink2',
              ].join(' ')}
            >
              <span className="relative text-xl leading-none" aria-hidden>
                ⋯
              </span>
              <span className="text-[10px] font-bold uppercase tracking-[0.12em]">More</span>
              {isMoreActive && (
                <span className="absolute inset-x-3 top-0 h-0.5 rounded-full bg-current" aria-hidden />
              )}
            </button>
          </li>
        </ul>
      </nav>

      <Modal open={moreOpen} onClose={() => setMoreOpen(false)} title="More">
        <ul className="flex flex-col gap-1">
          {MORE_LINKS.map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                onClick={() => setMoreOpen(false)}
                className="flex items-center gap-3 rounded-md border border-wb-line bg-wb-surface p-3 text-wb-ink transition-colors hover:border-wb-sage-deep/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
              >
                <span className="text-xl leading-none" aria-hidden>
                  {link.glyph}
                </span>
                <span className="flex flex-col">
                  <span className="text-sm font-semibold">{link.label}</span>
                  <span className="text-xs text-wb-ink2">{link.description}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </Modal>
    </>
  );
}
