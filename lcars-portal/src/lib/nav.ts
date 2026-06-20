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
    href: '/xo-brief',
    label: 'XO Brief',
    glyph: '05',
    department: 'science',
    description: 'Operational intelligence brief'
  },
  {
    href: '/medical',
    label: 'Medical Bay',
    glyph: '06',
    department: 'medical',
    description: 'Recovery indexes and life participation'
  },
  {
    href: '/recovery-brief',
    label: 'Recovery Brief',
    glyph: '07',
    department: 'medical',
    description: 'Daily recovery-first morning brief'
  },
  {
    href: '/stage-progression',
    label: 'Stage Progression',
    glyph: '08',
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
    glyph: '09',
    department: 'operations',
    description: 'Service and integration status'
  },
  {
    href: '/knowledge-base',
    label: 'Knowledge Base',
    glyph: '10',
    department: 'science',
    description: 'Knowledge, ADRs and playbooks'
  },
  {
    href: '/medical/check-in',
    label: 'Health Check-In',
    glyph: '11',
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
    href: '/ai-console',
    label: 'AI Console',
    glyph: '13',
    department: 'science',
    description: 'Direct access to Ollama Cloud GLM 5.2'
  }
];
