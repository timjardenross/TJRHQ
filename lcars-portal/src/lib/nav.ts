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
  // MSN: Advisory Council reskinned onto the wb- design system at
  // /advisory-workbench (kept first-class per Captain decision 2026-07-12).
  // /advisory-council stays valid — it now redirects to the workbench.
  '/captains-chair', '/advisory-council', '/advisory-workbench', '/knowledge', '/knowledge-library',
  // Capture reskinned onto the wb- design system at /capture-workbench (kept
  // first-class per Captain decision 2026-07-12). /capture stays valid — it
  // now redirects to the workbench.
  '/search', '/timeline', '/capture', '/capture-workbench',
  '/engineering-queue', '/intelligence', '/comms', '/alerts', '/missions',
  '/medical', '/operations', '/captains-log', '/captains-notebook',
  '/captains-brief', '/captains-brief-workbench', '/delivery', '/automation-centre', '/model-crew',
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
  // Canonical Architecture Decisions §1 (docs/EOS-CANONICAL-ARCHITECTURE-
  // DECISIONS.md): /home is now the real Home - HomeScreen.tsx/
  // executiveContext.ts mounted there, zero persistent nav, matching
  // /decide and /ask. /captains-chair remains fully valid and reachable
  // as a supporting experience, just no longer the Home target.
  '/decide', '/ask', '/home',
  // EOS Phase 2 Priority 1: reached only via Home's quiet "Recommended"
  // link, same treatment as Decide/Ask - deliberately not promoted in
  // NAV_SECTIONS below (no persistent sidebar, per docs/EOS-CANONICAL-
  // ARCHITECTURE-DECISIONS.md §5).
  '/recommended', '/investigate',
  // EOS Phase 2 Priority 5: same treatment - reached via Home's quiet
  // "Draft" link.
  '/comms-studio',
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
      { href: '/home', label: 'Home', glyph: '⌂', department: 'command', description: 'The verified-quiet briefing' },
      { href: '/decide', label: 'Decide', glyph: '✓', department: 'command', description: 'One place for judgement, one item at a time' },
      { href: '/ask',    label: 'Ask',    glyph: '?', department: 'command', description: 'Ask Starship what it knows' },
    ],
  },
];
