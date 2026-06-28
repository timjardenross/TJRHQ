'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import { NAV_SECTIONS } from '@/lib/nav';
import { DEPARTMENTS } from '@/lib/departments';

/**
 * LCARSNav — left command rail. Highlights the active route and colour-codes
 * each entry by department. Renders grouped sections; System section is collapsible.
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
      className="hidden shrink-0 lg:block lg:w-64"
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
                <span className="text-[9px] uppercase tracking-[0.3em] text-lcars-muted">
                  {section.label}
                </span>
                <span className="text-[9px] text-lcars-muted">{collapsed ? '▸' : '▾'}</span>
              </button>
              {!collapsed && (
                <ul className="flex flex-col gap-1.5">
                  {section.items.map((item) => {
                    const dept = DEPARTMENTS[item.department];
                    const active = isActive(item.href);
                    return (
                      <li key={item.href} className="grow lg:grow-0">
                        <Link
                          href={item.href}
                          aria-current={active ? 'page' : undefined}
                          className={[
                            'group flex items-center gap-3 rounded-lcars border px-3 py-2 transition-colors',
                            active
                              ? `${dept.bgSoft} ${dept.border} ${dept.text}`
                              : 'border-edge bg-panel/50 text-lcars-text hover:border-lcars-muted'
                          ].join(' ')}
                        >
                          <span
                            className={[
                              'flex h-8 w-8 shrink-0 items-center justify-center rounded-md font-mono text-xs font-bold',
                              active ? dept.bg + ' text-space' : 'bg-edge/60 text-lcars-muted'
                            ].join(' ')}
                          >
                            {item.glyph}
                          </span>
                          <span className="flex flex-col">
                            <span className="text-sm font-semibold uppercase tracking-wider">
                              {item.label}
                            </span>
                            <span className="hidden text-[11px] text-lcars-muted lg:block">
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
