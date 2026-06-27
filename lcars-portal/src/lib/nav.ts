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
    href: '/operating-model',
    label: 'Operating Model',
    glyph: 'OM',
    department: 'command',
    description: 'Personal operating model — roles, priorities, capacity (MSN-3B-002)'
  },
  {
    href: '/executive-staff',
    label: 'Executive Staff',
    glyph: 'ES',
    department: 'science',
    description: 'Unified executive staff console — XO, advisors, AI (MSN-3C-001)'
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
    href: '/xo',
    label: 'XO Chat',
    glyph: 'XO',
    department: 'science',
    description: 'Ask, route, clarify — intent into next action (MVP)'
  },
  {
    href: '/advisory',
    label: 'Advisors',
    glyph: 'AD',
    department: 'science',
    description: 'Ask advisors, challenge a decision, review lessons (MSN-0092)'
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
  {
    href: '/medical/pulse',
    label: 'Recovery Pulse',
    glyph: '11',
    department: 'medical',
    description: 'Log a recovery pulse — four per day'
  },
  {
    href: '/medical/check-in',
    label: 'Health Check-In',
    glyph: '11b',
    department: 'medical',
    description: 'Log today\'s daily health check-in'
  },
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
    href: '/ai-console',
    label: 'AI Console',
    glyph: '13',
    department: 'science',
    description: 'Direct access to Ollama Cloud GLM 5.2'
  }
];

/** Union of all valid nav hrefs — type sub-nav components against this to catch stale paths at build time. */
export type NavHref = (typeof NAV_ITEMS)[number]['href'];
