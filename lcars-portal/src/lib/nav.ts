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
] as const;

/** Union of all valid nav hrefs — type sub-nav components against this to catch stale paths at build time. */
export type NavHref = (typeof VALID_NAV_HREFS)[number];

export interface NavSection {
  label: string;
  items: NavItem[];
  collapsed?: boolean; // System section starts collapsed
}

// MSN-0344: regrouped from 5 sections (Chief of Staff/Health & Capacity/
// Intelligence/Actions/System) into the Captain Operating System's 7
// decision-first areas. No route added or removed by this change — every
// href below already existed in the prior grouping; this is IA only.
// "Decisions" (the 8th proposed area — a unified approve/reject inbox) is
// deliberately NOT a section here: no such page exists yet (today's approval
// surfaces stay where they are — Captain's Chair's CaptainApprovalQueue,
// Missions/[id]'s governed approve/reject, Engineering Queue's own queue).
// Adding a nav entry for a page that doesn't exist would be worse than the
// gap it's meant to close. See reports/USS-TJR-MSN-0344-*.md §1/§8 for the
// full rationale and the roadmap item to build it.
export const NAV_SECTIONS: NavSection[] = [
  {
    label: 'Today',
    items: [
      { href: '/captains-chair',   label: "Captain's Chair",   glyph: '01', department: 'command',     description: 'What changed, what matters, what needs attention' },
      { href: '/alerts',           label: 'Push Alerts',       glyph: '!!', department: 'operations',  description: 'Gated, meaningful escalations only' },
      { href: '/capture',          label: 'Capture',           glyph: 'QC', department: 'engineering', description: 'Quick intake — note, mission, health, idea' },
      { href: '/captains-notebook', label: "Captain's Notebook", glyph: '16', department: 'command',   description: 'Intelligence intake — capture, triage, route' },
      { href: '/captains-log',     label: "Captain's Log",     glyph: '12', department: 'command',     description: 'End-of-day structured log entry' },
    ],
  },
  {
    label: 'Decisions',
    items: [
      // MSN-0345: was a documented gap in MSN-0344's IA (no page existed) —
      // now built, merging mission + engineering approvals (and, once real,
      // OI recommendations) into one priority-ordered inbox. See lib/decisions.ts.
      { href: '/decisions',        label: 'Decisions',         glyph: 'DC', department: 'command',     description: 'One place for judgement — mission, engineering, intelligence' },
    ],
  },
  {
    label: 'Captain Brief',
    items: [
      { href: '/captains-brief',   label: "Captain's Brief",   glyph: 'CB', department: 'command',     description: 'Cross-domain intelligence brief — priorities, confidence, warnings' },
    ],
  },
  {
    label: 'Intelligence',
    items: [
      { href: '/intelligence',      label: 'Intelligence',      glyph: 'IC',  department: 'science',     description: 'Advisory signals, awareness, operational picture' },
      { href: '/advisory-council',  label: 'Advisory Council',  glyph: 'AC',  department: 'command',     description: 'Consult, board, brief, picture, intelligence — unified' },
      { href: '/timeline',          label: 'Timeline',          glyph: '⏱',  department: 'science',     description: 'Unified operational timeline' },
    ],
  },
  {
    label: 'Missions',
    items: [
      { href: '/missions',          label: 'Missions',          glyph: '02',  department: 'command',     description: 'Mission registry and status board' },
      { href: '/engineering-queue', label: 'Engineering Queue', glyph: 'EQ',  department: 'engineering', description: 'Triage, review, approve and unblock' },
    ],
  },
  {
    label: 'Health',
    items: [
      { href: '/medical',        label: 'Health Centre',   glyph: '05',  department: 'medical',     description: 'Recovery indexes, pulse, check-in, trends' },
      { href: '/physical-readiness', label: 'Physical Readiness', glyph: 'PR', department: 'medical', description: 'Adaptive gym session — readiness, generated workout, runner' },
      { href: '/human-systems',    label: 'Human Systems',    glyph: 'HS', department: 'medical', description: 'Capacity gates, escalation state, recovery debt' },
      { href: '/recovery-brief',   label: 'Recovery Brief',   glyph: 'RB', department: 'medical', description: 'Recovery posture and debt — leverage recommendation' },
      { href: '/stage-progression', label: 'Stage Progression (Retired)', glyph: 'SP', department: 'medical', description: 'Retired - previously showed placeholder data, not live' },
    ],
  },
  {
    label: 'Knowledge',
    items: [
      { href: '/knowledge',         label: 'Knowledge',         glyph: 'KH',  department: 'science',     description: 'Decisions, lessons, architecture, articles' },
      { href: '/knowledge-library', label: 'Knowledge Library', glyph: 'KL',  department: 'science',     description: 'VM-processed documents; approve into Command Memory' },
      { href: '/comms',             label: 'Communications',    glyph: 'CP',  department: 'command',     description: 'Content pipeline — from signal to published thought-leadership' },
    ],
  },
  {
    label: 'Platform',
    collapsed: true,
    items: [
      { href: '/operations',        label: 'Operations',         glyph: '08',  department: 'operations',  description: 'Service and integration status' },
      { href: '/delivery',          label: 'Delivery',           glyph: 'DL',  department: 'engineering', description: 'Engineering & Delivery Officer — pipeline throughput, where work is stuck' },
      { href: '/engineering',       label: 'Engineering',        glyph: 'EN',  department: 'engineering', description: 'Engineering domain overview' },
      { href: '/automation-centre', label: 'Automation Centre',  glyph: 'AT',  department: 'operations',  description: 'Scheduled automations, notification routing, alert thresholds' },
      { href: '/model-crew',        label: 'Model Crew',         glyph: 'MC',  department: 'science',     description: 'Live LLM router — loaded models, latency, escalations' },
      { href: '/search',            label: 'Search',             glyph: '🔍', department: 'science',     description: 'Universal search' },
      { href: '/preferences',       label: 'Preferences',        glyph: '⚙',  department: 'engineering', description: 'Settings and defaults' },
      // MSN-0344: relocated per MSN-0321 WP-B's own recommendation ("Keep,
      // relocate — static Captain-profile reference, not a dead page") —
      // was orphaned (zero inbound nav links) since at least MSN-0320.
      { href: '/operating-model',   label: 'Operating Model',    glyph: 'OM', department: 'command',     description: 'Captain profile — life domains, principles, daily schedule' },
    ],
  },
];
