'use client';

// Adaptive Themes + Home/Workbench Redesign mission (2026-09-05), §4/§14.
// GLOBAL chrome, rendered by WorkbenchShell around every *-workbench page.
// Visible xl: and up, same breakpoint MobileCommandBar disappears at (that
// component remains the below-xl fallback nav) — no gap reopened between
// them.
//
// Endeavour 27 (USS-TJR-MSN-0394), Stream A: this used to be a hand-picked
// 5-item list (Home/Workbenches/Library/Missions/Alerts) — real IA debt
// the mission doc flagged, since the mockups showed a 9-item curated set
// instead. Captain's decision on being asked directly: neither curated
// list — the sidebar should include every live workbench, not a hand-
// picked subset of either size. Renders the same LIVE_WORKBENCHES/
// WORKBENCH_GROUP_META source of truth `/workbenches` already uses (see
// that page's own header comment on why two independently-maintained
// lists drift), grouped the same way, so this can never show a different
// set of workbenches than the full directory does.
//
// Help has no dedicated standalone page in this app today — rather than
// link to a 404 or invent a page outside this mission's scope, it renders
// disabled with an inline "soon" tag.
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Settings, HelpCircle, type LucideIcon } from 'lucide-react';
import { LIVE_WORKBENCHES, WORKBENCH_GROUP_META, type WorkbenchGroup } from '@/lib/workbenches';

const GROUP_ORDER = Object.keys(WORKBENCH_GROUP_META) as WorkbenchGroup[];

interface SidebarLink {
  href: string;
  label: string;
  icon: LucideIcon;
  disabled?: boolean;
}

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
        ? 'bg-wb-sage-deep/15 font-medium text-wb-sage'
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
  const isActive = (href: string) => pathname === href || pathname?.startsWith(href + '/');

  return (
    <aside
      aria-label="Primary"
      className="sticky top-0 hidden h-[100dvh] w-64 shrink-0 flex-col justify-between overflow-y-auto border-r border-wb-line bg-wb-surface px-3 py-6 xl:flex"
    >
      <div className="flex flex-col gap-5">
        <Link href="/hub" className="flex items-center gap-2 px-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep" aria-label="TJR HQ home">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-wb-sage-deep text-[13px] font-semibold text-white">TJR</span>
          <span className="leading-tight">
            <span className="block text-[13px] font-semibold text-wb-ink">TJR HQ</span>
            <span className="block text-[10px] uppercase tracking-[0.14em] text-wb-ink2">Endeavour 27</span>
          </span>
        </Link>
        {GROUP_ORDER.map((group) => {
          const entries = LIVE_WORKBENCHES.filter((e) => e.group === group);
          if (entries.length === 0) return null;
          const meta = WORKBENCH_GROUP_META[group];
          return (
            <nav key={group} className="flex flex-col gap-1" aria-label={meta.label}>
              <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-wb-ink2/70">
                {meta.label}
              </p>
              {entries.map((entry) => (
                <SidebarRow
                  key={entry.href}
                  link={{ href: entry.href, label: entry.title, icon: entry.icon }}
                  active={isActive(entry.href)}
                />
              ))}
            </nav>
          );
        })}
      </div>
      <nav className="flex flex-col gap-1 border-t border-wb-line pt-3" aria-label="Secondary">
        {SECONDARY.map((link) => (
          <SidebarRow
            key={link.label}
            link={link}
            active={!link.disabled && isActive(link.href)}
          />
        ))}
        {/* Mission §1.1: mockups show this motto in every sidebar footer —
            real copy from the source brief, not fabricated here, but not
            yet Captain-confirmed as final (see mission doc §1.1). */}
        <p className="mt-4 px-3 text-[9px] uppercase leading-relaxed tracking-[0.18em] text-wb-ink2/50">
          Discipline<br />Clarity<br />Progress<br />Freedom
        </p>
      </nav>
    </aside>
  );
}
