'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAlertCount } from '@/lib/useAlerts';
import type { NavHref } from '@/lib/nav';

/**
 * MobileCommandBar — the Captain-facing MVP navigation (MSN-IOS-001 WP7).
 *
 * Fixed, thumb-friendly bottom tab bar. This is the ONLY nav rendered on
 * mobile (LCARSNav and LCARSBottomNav are `lg:`-gated, desktop-only) — a
 * page not listed here is unreachable from a phone, full stop.
 * Mobile-only (`lg:hidden`) so the existing desktop portal navigation is
 * untouched — no broad redesign, no broken web access. Always mounted, so it is
 * also the single global owner that drives Push-Alert notifications.
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

// Starship rewrite (docs/REMOVAL-PLAN.md): Home/Decide/Ask are now the
// primary surfaces and take the first three slots - this is the ONLY nav
// on mobile (see doc comment above), so without this change mobile had
// zero path to any of them. Capture and Physical Readiness are kept -
// both are real task tools (docs/INVENTORY.md: MIGRATE/TASK-TOOL), not
// dashboards, and mobile is their primary device with no other nav path
// once NAV_SECTIONS stopped listing them. Chair/Advisory/Queue/Alerts
// dropped - all four are superseded (see docs/REMOVAL-PLAN.md Category A)
// and remain reachable by direct URL for now, not deleted.
const TABS: Tab[] = [
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
      className="fixed inset-x-0 bottom-0 z-50 border-t border-[#d9e1f0] bg-white/95 backdrop-blur lg:hidden"
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
