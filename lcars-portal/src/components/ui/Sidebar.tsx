'use client';

// Adaptive Themes + Home/Workbench Redesign mission (2026-09-05), §4/§14.
// Captain's call, asked directly given the size difference vs. a Home-only
// sidebar: this is GLOBAL chrome, rendered by WorkbenchShell around every
// *-workbench page — "the same operating system in five different
// environments." Visible xl: and up, same breakpoint MobileCommandBar
// disappears at (that component remains the below-xl fallback nav,
// unchanged) — no gap reopened between them.
//
// Help has no dedicated standalone page in this app today — rather than
// link to a 404 or invent a page outside this mission's scope, it renders
// disabled with an inline "soon" tag.
//
// Calendar entry removed (Sidebar review, 2026-09-08): it only ever
// resolved to /hub, duplicating Home — a confusing double-highlight, not a
// second destination. Calendar still lives as a card on /hub.
//
// Missions/Alerts/Library now link straight at their real pages
// (/mission-workbench, /captains-chair-workbench/alerts,
// /knowledge-workbench) instead of the /missions, /alerts,
// /knowledge-library redirect stubs — those stubs live under the legacy
// (app) LCARS layout, so following them briefly rendered the old
// LCARS-branded chrome before bouncing to the real destination. Missions
// and Alerts are also lower priority than Workbenches/Library now — they're
// narrower, single-purpose surfaces, not places captains land often.
//
// Settings Page Redesign mission (2026-09-06): Settings now has a real
// route (/settings) — see app/settings/ — so its entry is enabled.
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Home,
  LayoutGrid,
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
  { href: '/knowledge-workbench', label: 'Library', icon: BookMarked },
  { href: '/mission-workbench', label: 'Missions', icon: Rocket },
  { href: '/captains-chair-workbench/alerts', label: 'Alerts', icon: TriangleAlert },
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
            active={pathname === link.href || pathname?.startsWith(link.href + '/')}
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
