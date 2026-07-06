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
] as const;

/** Union of all valid nav hrefs — type sub-nav components against this to catch stale paths at build time. */
export type NavHref = (typeof VALID_NAV_HREFS)[number];

export interface NavSection {
  label: string;
  items: NavItem[];
  collapsed?: boolean; // System section starts collapsed
}

export const NAV_SECTIONS: NavSection[] = [
  {
    label: 'Chief of Staff',
    items: [
      { href: '/captains-chair',   label: "Captain's Chair",   glyph: '01', department: 'command',     description: 'What changed, what matters, what needs attention' },
      { href: '/advisory-council', label: 'Advisory Council',  glyph: 'AC', department: 'command',     description: 'Consult, board, brief, picture, intelligence — unified' },
      { href: '/captains-brief',   label: "Captain's Brief",   glyph: 'CB', department: 'command',     description: 'Cross-domain intelligence brief — priorities, confidence, warnings' },
      { href: '/capture',          label: 'Capture',           glyph: 'QC', department: 'engineering', description: 'Quick intake — note, mission, health, idea' },
      // MSN-0328 (WP-B): promoted from unreachable — same intake pipeline as Capture.
      { href: '/captains-notebook', label: "Captain's Notebook", glyph: '16', department: 'command',   description: 'Intelligence intake — capture, triage, route' },
    ],
  },
  {
    label: 'Health & Capacity',
    items: [
      { href: '/medical',        label: 'Health Centre',   glyph: '05',  department: 'medical',     description: 'Recovery indexes, pulse, check-in, trends' },
      // MSN-0328 (WP-B): promoted from unreachable — real pages, no nav path to any of them before this.
      { href: '/human-systems',    label: 'Human Systems',    glyph: 'HS', department: 'medical', description: 'Capacity gates, escalation state, recovery debt' },
      { href: '/recovery-brief',   label: 'Recovery Brief',   glyph: 'RB', department: 'medical', description: 'Recovery posture and debt — leverage recommendation' },
      { href: '/stage-progression', label: 'Stage Progression', glyph: 'SP', department: 'medical', description: 'Recovery stage tracking (ROS-001)' },
    ],
  },
  {
    label: 'Intelligence',
    items: [
      { href: '/intelligence',      label: 'Intelligence',      glyph: 'IC',  department: 'science',     description: 'Advisory signals, awareness, operational picture' },
      { href: '/knowledge',         label: 'Knowledge',         glyph: 'KH',  department: 'science',     description: 'Decisions, lessons, architecture, articles' },
      { href: '/knowledge-library', label: 'Knowledge Library', glyph: 'KL',  department: 'science',     description: 'VM-processed documents; approve into Command Memory' },
      { href: '/comms',             label: 'Communications',    glyph: 'CP',  department: 'command',     description: 'Content pipeline — from signal to published thought-leadership' },
    ],
  },
  {
    label: 'Actions',
    items: [
      { href: '/missions',       label: 'Missions',        glyph: '02',  department: 'command',     description: 'Mission registry and status board' },
      { href: '/timeline',       label: 'Timeline',        glyph: '⏱',  department: 'science',     description: 'Unified operational timeline' },
      { href: '/captains-log',   label: "Captain's Log",   glyph: '12',  department: 'command',     description: 'End-of-day structured log entry' },
      // MSN-0328 (WP-B): promoted from unreachable — both are direct Captain decision surfaces.
      { href: '/alerts',           label: 'Push Alerts',       glyph: '!!', department: 'operations',  description: 'Gated, meaningful escalations only' },
      { href: '/engineering-queue', label: 'Engineering Queue', glyph: 'EQ', department: 'engineering', description: 'Triage, review, approve and unblock' },
    ],
  },
  {
    label: 'System',
    collapsed: true,
    items: [
      { href: '/operations',        label: 'Operations',         glyph: '08',  department: 'operations',  description: 'Service and integration status' },
      { href: '/delivery',          label: 'Delivery',           glyph: 'DL',  department: 'engineering', description: 'Engineering & Delivery Officer — pipeline throughput, where work is stuck' },
      // MSN-0328 (WP-B): promoted from unreachable — sits alongside Delivery, same domain.
      { href: '/engineering',       label: 'Engineering',        glyph: 'EN',  department: 'engineering', description: 'Engineering domain overview' },
      { href: '/automation-centre', label: 'Automation Centre',  glyph: 'AT',  department: 'operations',  description: 'Scheduled automations, notification routing, alert thresholds' },
      { href: '/model-crew',        label: 'Model Crew',         glyph: 'MC',  department: 'science',     description: 'Live LLM router — loaded models, latency, escalations' },
      { href: '/search',            label: 'Search',             glyph: '🔍', department: 'science',     description: 'Universal search' },
      { href: '/preferences',       label: 'Preferences',        glyph: '⚙',  department: 'engineering', description: 'Settings and defaults' },
    ],
  },
];
