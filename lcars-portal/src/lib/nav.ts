import type { DepartmentKey } from './types';

export interface NavItem {
  href: string;
  label: string;
  glyph: string;
  department: DepartmentKey;
  description: string;
}

/** Primary navigation — order defines the LCARS rail order. */
export const NAV_ITEMS: NavItem[] = [
  {
    href: '/captains-chair',
    label: "Captain's Chair",
    glyph: '01',
    department: 'command',
    description: 'Command overview and daily posture'
  },
  {
    href: '/advisory-council',
    label: 'Advisory Council',
    glyph: 'AC',
    department: 'command',
    description: 'Consult, board, brief, picture, intelligence — unified'
  },
  {
    href: '/knowledge',
    label: 'Knowledge Hub',
    glyph: 'KH',
    department: 'science',
    description: 'Decisions, lessons, intelligence, architecture records'
  },
  {
    href: '/knowledge-library',
    label: 'Knowledge Library',
    glyph: 'KL',
    department: 'science',
    description: 'Browse VM-processed documents; approve into Command Memory'
  },
  {
    href: '/preferences',
    label: 'Preferences',
    glyph: '⚙',
    department: 'engineering',
    description: 'Operating mode, favourites, notifications, advisor defaults'
  },
  {
    href: '/search',
    label: 'Search',
    glyph: '🔍',
    department: 'science',
    description: 'Universal search — missions, log, captures, events'
  },
  {
    href: '/timeline',
    label: 'Timeline',
    glyph: '⏱',
    department: 'science',
    description: 'Unified operational timeline — all sources'
  },
  {
    href: '/capture',
    label: 'Quick Capture',
    glyph: 'QC',
    department: 'engineering',
    description: 'Capture a note, mission, health log or idea'
  },
  {
    href: '/xo',
    label: 'XO Chat',
    glyph: 'XO',
    department: 'science',
    description: 'Ask, route, clarify — intent into next action (MVP)'
  },
  {
    href: '/engineering-queue',
    label: 'Engineering Queue',
    glyph: 'EQ',
    department: 'engineering',
    description: 'Triage, review, approve and unblock (MVP)'
  },
  {
    href: '/intelligence',
    label: 'Intelligence',
    glyph: 'IC',
    department: 'science',
    description: 'Advisory signals, awareness, operational picture'
  },
  {
    href: '/comms',
    label: 'Communications',
    glyph: 'CP',
    department: 'command',
    description: 'Content pipeline — from signal to published thought-leadership'
  },
  {
    href: '/alerts',
    label: 'Push Alerts',
    glyph: '!!',
    department: 'operations',
    description: 'Gated, meaningful escalations only'
  },
  {
    href: '/missions',
    label: 'Missions',
    glyph: '02',
    department: 'command',
    description: 'Mission registry and status'
  },
  {
    href: '/medical',
    label: 'Medical Bay',
    glyph: '05',
    department: 'medical',
    description: 'Recovery indexes and life participation'
  },
  {
    href: '/operations',
    label: 'Operations',
    glyph: '08',
    department: 'operations',
    description: 'Service and integration status'
  },
  // /medical/pulse and /medical/check-in are sub-pages of Medical Bay — accessible
  // via the Medical Bay page, not the primary nav rail.
  {
    href: '/captains-log',
    label: "Captain's Log",
    glyph: '12',
    department: 'command',
    description: 'End-of-day structured log entry'
  },
  {
    href: '/captains-notebook',
    label: "Captain's Notebook",
    glyph: '16',
    department: 'command',
    description: 'Intelligence intake — capture, triage, route'
  },
  {
    href: '/captains-brief',
    label: "Captain's Brief",
    glyph: 'CB',
    department: 'command',
    description: 'Cross-domain intelligence brief — priorities, confidence, warnings'
  }
];

/** Union of all valid nav hrefs — type sub-nav components against this to catch stale paths at build time. */
export type NavHref = (typeof NAV_ITEMS)[number]['href'];

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
    ],
  },
  {
    label: 'Health & Capacity',
    items: [
      { href: '/medical',        label: 'Health Centre',   glyph: '05',  department: 'medical',     description: 'Recovery indexes, pulse, check-in, trends' },
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
    ],
  },
  {
    label: 'System',
    collapsed: true,
    items: [
      { href: '/operations',        label: 'Operations',         glyph: '08',  department: 'operations',  description: 'Service and integration status' },
      { href: '/delivery',          label: 'Delivery',           glyph: 'DL',  department: 'engineering', description: 'Engineering & Delivery Officer — pipeline throughput, where work is stuck' },
      { href: '/automation-centre', label: 'Automation Centre',  glyph: 'AT',  department: 'operations',  description: 'Scheduled automations, notification routing, alert thresholds' },
      { href: '/model-crew',        label: 'Model Crew',         glyph: 'MC',  department: 'science',     description: 'Live LLM router — loaded models, latency, escalations' },
      { href: '/search',            label: 'Search',             glyph: '🔍', department: 'science',     description: 'Universal search' },
      { href: '/preferences',       label: 'Preferences',        glyph: '⚙',  department: 'engineering', description: 'Settings and defaults' },
    ],
  },
];
