'use client';

// Adaptive Themes + Home/Workbench Redesign mission (2026-09-05), §4/§14.
// Captain's call, asked directly given the size difference vs. a Home-only
// sidebar: this is GLOBAL chrome, rendered by WorkbenchShell around every
// *-workbench page — "the same operating system in five different
// environments." Visible xl: and up, same breakpoint MobileCommandBar
// disappears at (that component remains the below-xl fallback nav,
// unchanged) — no gap reopened between them.
//
// Calendar/Help have no dedicated standalone page in this app today
// (calendar lives as a card on /hub; Help doesn't exist yet anywhere) —
// rather than link to a 404 or invent a page outside this mission's scope,
// those two render as disabled with an inline "soon" tag. Home and
// Calendar both resolve to /hub by design (glance dashboard IS where
// today's calendar lives) — a harmless double-highlight, not a bug.
//
// Settings Page Redesign mission (2026-09-06): Settings now has a real
// route (/settings) — see app/settings/ — so its entry is enabled.
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Home,
  LayoutGrid,
  CalendarDays,
  Rocket,
  TriangleAlert,
  BookMarked,
  Settings,
  HelpCircle,
  type LucideIcon,
} from 'lucide-react';

interface SidebarLink {
  href: string;
  label: string;
  icon: LucideIcon;
  disabled?: boolean;
}

const PRIMARY: SidebarLink[] = [
  { href: '/hub', label: 'Home', icon: Home },
  { href: '/workbenches', label: 'Workbenches', icon: LayoutGrid },
  { href: '/hub', label: 'Calendar', icon: CalendarDays },
  { href: '/missions', label: 'Missions', icon: Rocket },
  { href: '/alerts', label: 'Alerts', icon: TriangleAlert },
  { href: '/knowledge-library', label: 'Library', icon: BookMarked },
];

const SECONDARY: SidebarLink[] = [
  { href: '/settings', label: 'Settings', icon: Settings },
  { href: '#', label: 'Help', icon: HelpCircle, disabled: true },
];

function SidebarRow({ link, active }: { link: SidebarLink; active: boolean }) {
  const Icon = link.icon;
  const classes = [
    'flex items-center gap-3 rounded-md px-3 py-2 text-[13px] transition-colors',
    link.disabled
      ? 'cursor-not-allowed text-wb-ink2/50'
      : active
        ? 'bg-wb-sage-deep/10 font-medium text-wb-sage-deep'
        : 'text-wb-ink2 hover:bg-wb-surface-raised hover:text-wb-ink',
  ].join(' ');

  if (link.disabled) {
    return (
      <span className={classes} aria-disabled="true">
        <Icon className="h-4 w-4 shrink-0" aria-hidden />
        {link.label}
        <span className="ml-auto text-[10px] uppercase tracking-[0.1em] text-wb-ink2/50">Soon</span>
      </span>
    );
  }

  return (
    <Link
      href={link.href}
      aria-current={active ? 'page' : undefined}
      className={`${classes} focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep`}
    >
      <Icon className="h-4 w-4 shrink-0" aria-hidden />
      {link.label}
    </Link>
  );
}

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside
      aria-label="Primary"
      className="sticky top-0 hidden h-[100dvh] w-56 shrink-0 flex-col justify-between border-r border-wb-line bg-wb-surface px-3 py-6 xl:flex"
    >
      <nav className="flex flex-col gap-1" aria-label="Sections">
        {PRIMARY.map((link) => (
          <SidebarRow
            key={link.label}
            link={link}
            active={pathname === link.href || (link.href !== '/hub' && pathname?.startsWith(link.href + '/'))}
          />
        ))}
      </nav>
      <nav className="flex flex-col gap-1" aria-label="Secondary">
        {SECONDARY.map((link) => (
          <SidebarRow
            key={link.label}
            link={link}
            active={!link.disabled && (pathname === link.href || pathname?.startsWith(link.href + '/'))}
          />
        ))}
      </nav>
    </aside>
  );
}
