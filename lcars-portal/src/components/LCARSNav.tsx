'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import { NAV_SECTIONS } from '@/lib/nav';

/**
 * LCARSNav — left command rail. Highlights the active route. Renders
 * grouped sections; System section is collapsible.
 *
 * Real-Captain-walkthrough revision (2026-07-10): restyled on the real
 * public-site brand tokens, matching HomeScreen.tsx and LCARSHeader.tsx.
 * Department-colour coding (DEPARTMENTS map) dropped along with it - the
 * new brand has one accent, not five decorative department colours, and
 * NAV_SECTIONS currently has exactly one section (Home/Decide/Ask) so the
 * distinction was already doing almost no real work.
 */
export function LCARSNav() {
  const pathname = usePathname();

  // Track which sections are collapsed; initialise from section config
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>(
    () => Object.fromEntries(NAV_SECTIONS.map((s) => [s.label, s.collapsed ?? false]))
  );

  const toggleSection = (label: string) => {
    setCollapsedSections((prev) => ({ ...prev, [label]: !prev[label] }));
  };

  const isActive = (href: string) => pathname === href;

  return (
    <nav
      aria-label="Primary"
      className="hidden shrink-0 xl:block xl:w-64"
    >
      <ul className="flex flex-col gap-0">
        {NAV_SECTIONS.map((section, sectionIdx) => {
          const collapsed = collapsedSections[section.label];
          return (
            <li key={section.label}>
              <button
                onClick={() => toggleSection(section.label)}
                className={[
                  'flex w-full items-center justify-between px-1 mb-1 cursor-pointer select-none',
                  sectionIdx === 0 ? 'mt-0' : 'mt-3',
                ].join(' ')}
              >
                <span className="text-[9px] uppercase tracking-[0.3em] text-[#61718c]">
                  {section.label}
                </span>
                <span className="text-[9px] text-[#61718c]">{collapsed ? '▸' : '▾'}</span>
              </button>
              {!collapsed && (
                <ul className="flex flex-col gap-1.5">
                  {section.items.map((item) => {
                    const active = isActive(item.href);
                    return (
                      <li key={item.href} className="grow lg:grow-0">
                        <Link
                          href={item.href}
                          aria-current={active ? 'page' : undefined}
                          className={[
                            'group flex items-center gap-3 rounded-2xl border px-3 py-2 transition-colors',
                            active
                              ? 'border-[#243b7a] bg-[#243b7a]/8 text-[#18223a]'
                              : 'border-[#d9e1f0] bg-white/92 text-[#4d5d77] hover:border-[#243b7a]/40'
                          ].join(' ')}
                        >
                          <span
                            className={[
                              'flex h-8 w-8 shrink-0 items-center justify-center rounded-xl font-mono text-xs font-bold',
                              active ? 'bg-[#243b7a] text-white' : 'bg-[#eef1f8] text-[#61718c]'
                            ].join(' ')}
                          >
                            {item.glyph}
                          </span>
                          <span className="flex flex-col">
                            <span className="text-sm font-semibold text-[#18223a]">
                              {item.label}
                            </span>
                            <span className="hidden text-[11px] text-[#61718c] lg:block">
                              {item.description}
                            </span>
                          </span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
