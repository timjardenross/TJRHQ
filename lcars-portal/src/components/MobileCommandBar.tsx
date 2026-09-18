'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAlertCount } from '@/lib/useAlerts';
import type { NavHref } from '@/lib/nav';

/**
 * MobileCommandBar — the Captain-facing MVP navigation (MSN-IOS-001 WP7).
 *
 * Fixed, thumb-friendly bottom tab bar, `xl:hidden`. Scope narrowed
 * 2026-09-12 (WORKBENCH-MOBILE-COMPAT): no longer mounted in WorkbenchShell
 * or /workbenches — on phones it sat, fixed and full-width at z-50, on top
 * of QuickCapture's floating "+" button (both bottom-right/bottom-of-screen)
 * and clipped the bottom of every *-workbench page's content, which had no
 * padding reserved for it. Those routes already have a mobile way home
 * (header logo + Settings icon, both xl:hidden) and a way to any other
 * workbench (WorkbenchSwitcher dropdown, always visible), so the bar was a
 * second nav layer causing real harm rather than a needed one. It remains
 * the primary mobile/tablet nav for the legacy (app) route group (LCARSNav
 * and LCARSBottomNav are `xl:`-gated, desktop-only there) and for the
 * zero-nav /investigate page. See GlobalAlertNotifier for the bar's other
 * job (firing real push notifications for critical/high alerts), split out
 * so removing this component from a route doesn't silently stop that too.
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
  // browser push notifications for critical/high alerts. GlobalAlertNotifier
  // now does the same for the routes this component was removed from (see
  // file doc comment) - dropping this call here would silently break real
  // notifications on the routes still using this bar, not just hide a
  // badge. The count itself is no longer displayed anywhere.
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
