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
    href: '/chief-of-staff',
    label: 'Chief of Staff',
    glyph: 'CoS',
    department: 'command',
    description: 'Chat, brief, advisors, intelligence — unified'
  },
  {
    href: '/operating-model',
    label: 'Operating Model',
    glyph: 'OM',
    department: 'command',
    description: 'Personal operating model — roles, priorities, capacity (MSN-3B-002)'
  },
  {
    href: '/automation-centre',
    label: 'Automation Centre',
    glyph: 'AC',
    department: 'operations',
    description: 'Scheduled jobs, notification routing, delivery history (MSN-3C-002)'
  },
  {
    href: '/knowledge',
    label: 'Knowledge Hub',
    glyph: 'KH',
    department: 'science',
    description: 'Decisions, lessons, intelligence, architecture records (MSN-3D-002)'
  },
  {
    href: '/preferences',
    label: 'Preferences',
    glyph: '⚙',
    department: 'engineering',
    description: 'Operating mode, favourites, notifications, advisor defaults (MSN-3D-001)'
  },
  {
    href: '/search',
    label: 'Search',
    glyph: '🔍',
    department: 'science',
    description: 'Universal search — missions, log, captures, events (MSN-3A-001)'
  },
  {
    href: '/timeline',
    label: 'Timeline',
    glyph: '⏱',
    department: 'science',
    description: 'Unified operational timeline — all sources (MSN-3A-002)'
  },
  {
    href: '/capture',
    label: 'Quick Capture',
    glyph: 'QC',
    department: 'engineering',
    description: 'Capture a note, mission, health log or idea (MVP)'
  },
  {
    href: '/intelligence',
    label: 'Intelligence',
    glyph: 'IC',
    department: 'science',
    description: 'Advisor dashboard, performance, timeline, operational picture (MSN-0097)'
  },
  {
    href: '/engineering-queue',
    label: 'Engineering Queue',
    glyph: 'EQ',
    department: 'engineering',
    description: 'Triage, review, approve and unblock (MVP)'
  },
  {
    href: '/alerts',
    label: 'Push Alerts',
    glyph: '!!',
    department: 'operations',
    description: 'Gated, meaningful escalations only (MVP)'
  },
  {
    href: '/missions',
    label: 'Missions',
    glyph: '02',
    department: 'command',
    description: 'Mission registry and status'
  },
  {
    href: '/engineering',
    label: 'Engineering',
    glyph: '03',
    department: 'engineering',
    description: 'Systems, runtime and build health'
  },
  {
    href: '/delivery',
    label: 'Delivery',
    glyph: '15',
    department: 'engineering',
    description: 'Delivery pipeline, bottlenecks and metrics (EDO)'
  },
  {
    href: '/number-one',
    label: 'Number One',
    glyph: '04',
    department: 'operations',
    description: 'Crew assignments and execution'
  },
  {
    href: '/medical',
    label: 'Medical Bay',
    glyph: '05',
    department: 'medical',
    description: 'Recovery indexes and life participation'
  },
  {
    href: '/recovery-brief',
    label: 'Recovery Brief',
    glyph: '06',
    department: 'medical',
    description: 'Daily recovery-first morning brief'
  },
  {
    href: '/stage-progression',
    label: 'Stage Progression',
    glyph: '07',
    department: 'medical',
    description: 'Stage record — Knowledge Officer'
  },
  {
    href: '/human-systems',
    label: 'Human Systems',
    glyph: '14',
    department: 'medical',
    description: 'Capacity, energy domains and resilience (HSF-001)'
  },
  {
    href: '/operations',
    label: 'Operations',
    glyph: '08',
    department: 'operations',
    description: 'Service and integration status'
  },
  {
    href: '/knowledge-base',
    label: 'Knowledge Base',
    glyph: '09',
    department: 'science',
    description: 'Knowledge, ADRs and playbooks'
  },
  {
    href: '/xo-brief',
    label: 'Intelligence Brief',
    glyph: '10',
    department: 'science',
    description: 'Work intelligence brief — OR pipeline'
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
      { href: '/captains-chair', label: 'Situation Room',  glyph: '01',  department: 'command',     description: 'What changed, what matters, what needs attention' },
      { href: '/chief-of-staff', label: 'Chief of Staff',  glyph: 'CoS', department: 'command',     description: 'Chat, brief, advisors, intelligence — unified' },
    ],
  },
  {
    label: 'Health & Capacity',
    items: [
      { href: '/medical',        label: 'Health Centre',   glyph: '05',  department: 'medical',     description: 'Recovery indexes, pulse, check-in, trends' },
      { href: '/recovery-brief', label: 'Recovery Brief',  glyph: '06',  department: 'medical',     description: 'Morning recovery-first brief' },
    ],
  },
  {
    label: 'Intelligence',
    items: [
      { href: '/intelligence',   label: 'Intelligence',    glyph: 'IC',  department: 'science',     description: 'Advisory signals, awareness, operational picture' },
      { href: '/knowledge',      label: 'Knowledge',       glyph: 'KH',  department: 'science',     description: 'Decisions, lessons, architecture, articles' },
    ],
  },
  {
    label: 'Actions',
    items: [
      { href: '/missions',       label: 'Missions',        glyph: '02',  department: 'command',     description: 'Mission registry and status board' },
      { href: '/timeline',       label: 'Timeline',        glyph: '⏱',  department: 'science',     description: 'Unified operational timeline' },
      { href: '/capture',        label: 'Capture',         glyph: 'QC',  department: 'engineering', description: 'Quick intake — note, mission, health, idea' },
      { href: '/captains-log',   label: "Captain's Log",   glyph: '12',  department: 'command',     description: 'End-of-day structured log entry' },
    ],
  },
  {
    label: 'System',
    collapsed: true,
    items: [
      { href: '/engineering',    label: 'Engineering',     glyph: '03',  department: 'engineering', description: 'Systems, queue, delivery' },
      { href: '/operations',     label: 'Operations',      glyph: '08',  department: 'operations',  description: 'Service and integration status' },
      { href: '/search',         label: 'Search',          glyph: '🔍', department: 'science',     description: 'Universal search' },
      { href: '/preferences',    label: 'Preferences',     glyph: '⚙',  department: 'engineering', description: 'Settings and defaults' },
    ],
  },
];
