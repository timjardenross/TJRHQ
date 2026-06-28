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

const BOTTOM_TABS: BottomTab[] = [
  { href: '/captains-chair', label: 'Situation',  bg: 'bg-command',     glyph: '⌂' },
  { href: '/advisory-council', label: 'Advisory',  bg: 'bg-science',     glyph: '✦' },
  { href: '/medical',        label: 'Health',     bg: 'bg-medical',     glyph: '✚' },
  { href: '/capture',        label: 'Capture',    bg: 'bg-engineering', glyph: '+' },
  { href: '/missions',       label: 'Missions',   bg: 'bg-lcars-lilac', glyph: '★' },
];

export function LCARSBottomNav() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Quick access"
      className="mt-4 hidden overflow-hidden rounded-lcars border border-edge lg:flex"
    >
      {BOTTOM_TABS.map((tab) => {
        const active = pathname === tab.href || (tab.href === '/captains-chair' && pathname === '/');
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
