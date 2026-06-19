'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { NAV_ITEMS } from '@/lib/nav';
import { DEPARTMENTS } from '@/lib/departments';

/**
 * LCARSNav — left command rail. Highlights the active route and colour-codes
 * each entry by department. Treats "/" as the Captain's Chair.
 */
export function LCARSNav() {
  const pathname = usePathname();

  const isActive = (href: string) => pathname === href;

  return (
    <nav
      aria-label="Primary"
      className="shrink-0 lg:w-64"
    >
      <ul className="flex flex-row flex-wrap gap-2 lg:flex-col lg:gap-1.5">
        {NAV_ITEMS.map((item) => {
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
    </nav>
  );
}
