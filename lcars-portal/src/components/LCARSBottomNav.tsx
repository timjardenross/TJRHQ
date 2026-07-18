'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { NavHref } from '@/lib/nav';

interface BottomTab {
  href: NavHref;
  label: string;
  glyph: string;
}

// Starship rewrite (docs/REMOVAL-PLAN.md): this bar only renders inside the
// legacy (app) layout - Home/Decide/Ask live outside it and are never
// wrapped by this component - so its job now is purely "give the Captain a
// quick way back to the three MVP surfaces while on a legacy page", plus
// Capture, kept because it's a real task tool with no other quick-access
// path once the sidebar (NAV_SECTIONS) stopped listing it.
//
// Real-Captain-walkthrough revision (2026-07-10): restyled on the real
// public-site brand tokens - one accent colour, not four decorative
// department-coloured tiles.
const BOTTOM_TABS: BottomTab[] = [
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
