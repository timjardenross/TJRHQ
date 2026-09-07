'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAlertCount } from '@/lib/useAlerts';
import type { NavHref } from '@/lib/nav';

/**
 * MobileCommandBar — the Captain-facing MVP navigation (MSN-IOS-001 WP7).
 *
 * Fixed, thumb-friendly bottom tab bar. This is the ONLY nav rendered on
 * mobile/tablet (LCARSNav and LCARSBottomNav are `xl:`-gated, desktop-only)
 * — a page not listed here is unreachable below 1280px, full stop.
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
 * Real-Captain-walkthrough revision (2026-07-10): restyled on the real
 * public-site brand tokens - one accent colour for the active tab, not
 * five decorative department colours.
 */

interface Tab {
  href: NavHref;
  label: string;
  glyph: string;
}

// 2026-07-18: /home, /decide, /ask were decommissioned in favor of
// /workbenches as the new home (lib/nav.ts) but this bar was never
// updated, which broke the build (stale hrefs failed the NavHref type
// check) and, worse, left mobile with zero path back to the new home -
// this is the ONLY nav on mobile (see doc comment above). Workbenches
// takes the first slot for that reason. Capture and Physical Readiness
// are kept - both are real task tools (docs/INVENTORY.md:
// MIGRATE/TASK-TOOL), not dashboards, and mobile is their primary device
// with no other nav path once NAV_SECTIONS stopped listing them.
const TABS: Tab[] = [
  { href: '/workbenches', label: 'Workbenches', glyph: '⌂' },
  { href: '/capture-workbench', label: 'Capture', glyph: '＋' },
  { href: '/physical-readiness', label: 'Readiness', glyph: '✚' },
];

export function MobileCommandBar() {
  const pathname = usePathname();
  // Kept despite the Alerts tab being removed below: this hook's
  // `enableNotifications: true` option is what actually fires native
  // browser push notifications for critical/high alerts - this component
  // is documented as its "single global owner" (see file doc comment).
  // Dropping the call would silently break real notifications, not just
  // hide a badge. The count itself is no longer displayed anywhere.
  useAlertCount();

  return (
    <nav
      aria-label="Command MVP"
      className="fixed inset-x-0 bottom-0 z-50 border-t border-[#d9e1f0] bg-white/95 backdrop-blur xl:hidden"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
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
                  isActive ? 'text-[#243b7a]' : 'text-[#61718c]',
                ].join(' ')}
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
      </ul>
    </nav>
  );
}
