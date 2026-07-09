'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { NavHref } from '@/lib/nav';

interface BottomTab {
  href: NavHref;
  label: string;
  /** Tailwind bg class — must be a static string for Tailwind to include it. */
  bg: string;
  /** Icon glyph (Unicode or text abbreviation). */
  glyph: string;
}

// Starship rewrite (docs/REMOVAL-PLAN.md): this bar only renders inside the
// legacy (app) layout - Home/Decide/Ask live outside it and are never
// wrapped by this component - so its job now is purely "give the Captain a
// quick way back to the three MVP surfaces while on a legacy page", plus
// Capture, kept because it's a real task tool with no other quick-access
// path once the sidebar (NAV_SECTIONS) stopped listing it.
const BOTTOM_TABS: BottomTab[] = [
  { href: '/home', label: 'Home', bg: 'bg-command', glyph: '⌂' },
  { href: '/decide',  label: 'Decide', bg: 'bg-status',      glyph: '✓' },
  { href: '/ask',     label: 'Ask',    bg: 'bg-science',     glyph: '?' },
  { href: '/capture', label: 'Capture', bg: 'bg-engineering', glyph: '+' },
];

export function LCARSBottomNav() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Quick access"
      className="mt-4 hidden overflow-hidden rounded-lcars border border-edge lg:flex"
    >
      {BOTTOM_TABS.map((tab) => {
        const active = pathname === tab.href;
        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={active ? 'page' : undefined}
            className={[
              'flex flex-1 flex-col items-center justify-center gap-1 py-2.5 px-1 transition-opacity',
              tab.bg,
              active ? 'opacity-100 ring-2 ring-inset ring-white/30' : 'opacity-75 hover:opacity-100'
            ].join(' ')}
          >
            <span className="text-base leading-none text-space" aria-hidden>
              {tab.glyph}
            </span>
            <span className="text-[9px] font-bold uppercase tracking-[0.15em] text-space">
              {tab.label}
            </span>
          </Link>
        );
      })}
    </nav>
  );
}
