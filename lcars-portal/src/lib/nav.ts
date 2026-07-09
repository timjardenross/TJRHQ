import type { DepartmentKey } from './types';

export interface NavItem {
  href: string;
  label: string;
  glyph: string;
  department: DepartmentKey;
  description: string;
}

// MSN-0328 (WP-D): this used to be a full NavItem[] (label/glyph/department/
// description per entry) that looked like the primary nav source but wasn't
// — LCARSNav.tsx has always rendered NAV_SECTIONS below, never this. The
// dead metadata is retired; the one real thing depending on this list —
// NavHref, a build-time type check used by MobileCommandBar and
// LCARSBottomNav — is kept, now sourced from a plain href list instead of
// a duplicate, driftable copy of nav item data.
const VALID_NAV_HREFS = [
  '/captains-chair', '/advisory-council', '/knowledge', '/knowledge-library',
  '/preferences', '/search', '/timeline', '/capture',
  '/engineering-queue', '/intelligence', '/comms', '/alerts', '/missions',
  '/medical', '/operations', '/captains-log', '/captains-notebook',
  '/captains-brief', '/delivery', '/automation-centre', '/model-crew',
  '/physical-readiness',
  // MSN-0344: found missing here despite being live in NAV_SECTIONS since
  // MSN-0328 (WP-B) — this list had silently drifted from the real nav.
  '/human-systems', '/recovery-brief', '/stage-progression', '/engineering',
  // MSN-0344: relocated from orphan into the Platform section (see below).
  '/operating-model',
  // MSN-0345: the Decisions area now has a real page.
  '/decisions',
  // Starship rewrite (docs/REMOVAL-PLAN.md): the three MVP surfaces, now
  // the only entries actually promoted in NAV_SECTIONS below. Every href
  // above this line stays valid (all those pages still exist and are
  // still directly reachable) but is no longer nav-promoted - see the
  // removal plan for the full per-route legacy access policy.
  '/', '/decide', '/ask',
] as const;

/** Union of all valid nav hrefs — type sub-nav components against this to catch stale paths at build time. */
export type NavHref = (typeof VALID_NAV_HREFS)[number];

export interface NavSection {
  label: string;
  items: NavItem[];
  collapsed?: boolean; // System section starts collapsed
}

// Starship rewrite (docs/REMOVAL-PLAN.md, first nav demotion commit): Home,
// Decide, and Ask are now the product's only primary surfaces. Every route
// that used to live in this file's ~35-item, 8-section nav still exists and
// is still directly reachable by URL - see docs/REMOVAL-PLAN.md for the
// full per-route category (immediate nav removal / retire with notice /
// task tool kept off nav / delete pending verification / backend-only) and
// docs/INVENTORY.md for the original per-route rationale. Nothing is
// deleted by this change - only what's promoted in the sidebar.
export const NAV_SECTIONS: NavSection[] = [
  {
    label: 'Starship',
    items: [
      { href: '/',       label: 'Home',   glyph: '⌂', department: 'command', description: 'The verified-quiet briefing' },
      { href: '/decide', label: 'Decide', glyph: '✓', department: 'command', description: 'One place for judgement, one item at a time' },
      { href: '/ask',    label: 'Ask',    glyph: '?', department: 'command', description: 'Ask Starship what it knows' },
    ],
  },
];
