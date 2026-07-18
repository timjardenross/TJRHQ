'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { NavHref } from '@/lib/nav';

interface BottomTab {
  href: NavHref;
  label: string;
  glyph: string;
}

// This bar only renders inside the legacy (app) layout, giving the Captain
// a quick way back to current surfaces while on a legacy page.
//
// 2026-07-18: /home, /decide, /ask were decommissioned in favor of
// /workbenches as the new home (lib/nav.ts) but this bar still pointed at
// them, which broke the build (stale hrefs failed the NavHref type check).
// Workbenches replaces them as the way back to the new home; Capture stays
// because it's a real task tool with no other quick-access path once the
// sidebar (NAV_SECTIONS) stopped listing it.
const BOTTOM_TABS: BottomTab[] = [
  { href: '/workbenches', label: 'Workbenches', glyph: '⌂' },
  { href: '/capture-workbench', label: 'Capture', glyph: '+' },
];

export function LCARSBottomNav() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Quick access"
      className="mt-4 hidden overflow-hidden rounded-2xl border border-[#d9e1f0] bg-white/92 lg:flex"
    >
      {BOTTOM_TABS.map((tab) => {
        const active = pathname === tab.href;
        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={active ? 'page' : undefined}
            className={[
              'flex flex-1 flex-col items-center justify-center gap-1 py-2.5 px-1 transition-colors',
              active ? 'bg-[#243b7a] text-white' : 'text-[#4d5d77] hover:bg-[#f5f7fb]'
            ].join(' ')}
          >
            <span className="text-base leading-none" aria-hidden>
              {tab.glyph}
            </span>
            <span className="text-[9px] font-bold uppercase tracking-[0.15em]">
              {tab.label}
            </span>
          </Link>
        );
      })}
    </nav>
  );
}
