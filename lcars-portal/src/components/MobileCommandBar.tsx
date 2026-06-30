'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAlertCount } from '@/lib/useAlerts';
import type { NavHref } from '@/lib/nav';

/**
 * MobileCommandBar — the five-surface MVP navigation (MSN-IOS-001 WP7).
 *
 * Fixed, thumb-friendly bottom tab bar for the five Captain-facing MVP surfaces.
 * Mobile-only (`lg:hidden`) so the existing desktop portal navigation is
 * untouched — no broad redesign, no broken web access. Always mounted, so it is
 * also the single global owner that drives Push-Alert notifications.
 */

interface Tab {
  href: NavHref;
  label: string;
  glyph: string;
  /** Static Tailwind colour class (must be literal for the JIT scan). */
  active: string;
}

const TABS: Tab[] = [
  { href: '/captains-chair', label: 'Chair', glyph: '★', active: 'text-command' },
  { href: '/capture', label: 'Capture', glyph: '＋', active: 'text-engineering' },
  { href: '/xo', label: 'XO', glyph: '✦', active: 'text-science' },
  { href: '/engineering-queue', label: 'Queue', glyph: '⚙', active: 'text-engineering' },
  { href: '/alerts', label: 'Alerts', glyph: '◆', active: 'text-operations' },
];

export function MobileCommandBar() {
  const pathname = usePathname();
  const alertCount = useAlertCount();

  return (
    <nav
      aria-label="Command MVP"
      className="fixed inset-x-0 bottom-0 z-50 border-t border-edge bg-space/95 backdrop-blur lg:hidden"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      <ul className="mx-auto flex max-w-[640px]">
        {TABS.map((tab) => {
          const isActive =
            pathname === tab.href ||
            (tab.href === '/captains-chair' && pathname === '/');
          const isAlerts = tab.href === '/alerts';
          return (
            <li key={tab.href} className="flex-1">
              <Link
                href={tab.href}
                aria-current={isActive ? 'page' : undefined}
                className={[
                  'relative flex min-h-[56px] flex-col items-center justify-center gap-0.5 py-2',
                  isActive ? tab.active : 'text-lcars-muted',
                ].join(' ')}
              >
                <span className="relative text-xl leading-none" aria-hidden>
                  {tab.glyph}
                  {isAlerts && alertCount > 0 && (
                    <span className="absolute -right-3 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-operations px-1 text-[10px] font-bold text-space">
                      {alertCount > 9 ? '9+' : alertCount}
                    </span>
                  )}
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
