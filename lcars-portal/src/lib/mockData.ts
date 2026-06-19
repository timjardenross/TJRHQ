/**
 * ============================================================================
 * SINGLE SOURCE OF MOCK DATA — Starship Endeavour LCARS Portal (Phase 1)
 * ============================================================================
 *
 * Every screen in the portal reads from this file. Nothing else hardcodes
 * domain data. This is intentional: Phase 2 replaces each export below with a
 * live API call (see endpoint notes per section) WITHOUT touching any page or
 * component.
 *
 * Mapping to existing, unmodified Command Centre backend (MSN-0035):
 *   missions       → GET /api/v1/missions/active     + /summary
 *   captainBrief   → GET /api/v1/context/captain-brief
 *   operating...   → GET /api/v1/context/operating-picture
 *   alerts         → GET /api/v1/health/alerts
 *   crew           → GET /api/v1/agents/status
 *   wellness       → GET /api/v1/personal-health  / context/health
 *   services       → GET /api/v1/health/services
 *   intelligence   → GET /api/v1/intelligence/latest
 *   knowledge      → knowledge/ + Supabase (knowledge prototype, MSN-0004+)
 *
 * Phase 1 rule: placeholder data ONLY. Do not wire live calls here yet.
 * ============================================================================
 */

import type {
  Alert,
  BriefingItem,
  CaptainBrief,
  CrewMember,
  DecisionItem,
  Department,
  IntelligenceBrief,
  KnowledgeArticle,
  Mission,
  MissionBoardColumn,
  MissionSummary,
  OperatingPicture,
  QueueItem,
  ServiceStatus,
  ShipSystemStatus,
  TimelineEvent,
  WellnessMetric
} from './types';

export const SHIP = {
  name: 'USS TJR — Starship Endeavour',
  registry: 'NCC-170230',
  captain: 'Captain TJR',
  stardate: '79874.3',
  date: '2026-06-19'
};

// ── Captain's Chair ─────────────────────────────────────────────────────────
export const captainBrief: CaptainBrief = {
  stardate: SHIP.stardate,
  greeting: 'Good morning, Captain.',
  headline: 'Ship is at general readiness. Three priorities require command attention.',
  priorities: [
    'Review LCARS Portal Phase 1 acceptance before fleet demo.',
    'Clear the blocked Supabase migration on MSN-0011.',
    'Confirm wellness recovery block is protected this afternoon.'
  ],
  posture: [
    { label: 'Readiness', value: 'CONDITION GREEN', tone: 'status' },
    { label: 'Command Tempo', value: 'Steady', tone: 'command' },
    { label: 'Risk', value: '1 Blocker', tone: 'operations' }
  ]
};

export const operatingPicture: OperatingPicture = {
  readiness: 'CONDITION GREEN',
  activeMissions: 6,
  blockers: 1,
  crewOnDuty: 6
};

// ── Ship Status bars ─────────────────────────────────────────────────────────
export const shipSystemStatus: ShipSystemStatus[] = [
  { label: 'Hull Integrity', value: 100 },
  { label: 'Shield Strength', value: 98 },
  { label: 'Power Level', value: 97 },
  { label: 'Systems Nominal', value: 96 },
  { label: 'Crew Readiness', value: 93 },
  { label: 'Sensor Capacity', value: 95 }
];

// ── Captain's Timeline ───────────────────────────────────────────────────────
export const captainTimeline: TimelineEvent[] = [
  { time: '07:00', title: 'Daily Briefing', status: 'completed' },
  { time: '09:00', title: 'ANZ Priority Review', status: 'completed' },
  { time: '11:30', title: 'Engineering Review', status: 'in_progress' },
  { time: '13:00', title: 'Research Sync', status: 'scheduled' },
  { time: '15:00', title: 'Medical Council', status: 'scheduled' },
  { time: '16:30', title: 'Operations Update', status: 'scheduled' }
];

// ── Decisions Awaiting Approval ──────────────────────────────────────────────
export const decisionsAwaitingApproval: DecisionItem[] = [
  { id: '01', title: 'Security Remediation Plan', detail: 'XO Review Required', from: 'Security Chief' },
  { id: '02', title: 'Engineering Handoff Policy', detail: 'Approval Required', from: 'Chief Engineer' },
  { id: '03', title: 'Travel Readiness Assessment', detail: 'Review & Approve', from: 'Operations' }
];

// ── Mission Board (Kanban) ───────────────────────────────────────────────────
export const missionBoard: MissionBoardColumn[] = [
  {
    label: 'Pending Triage', count: 3, tone: 'command',
    items: [
      { title: 'Security Audit', meta: 'Submitted 2h ago' },
      { title: 'Medical Supplies', meta: 'Submitted 3h ago' },
      { title: 'Research Request', meta: 'Submitted 5h ago' }
    ]
  },
  {
    label: 'Assigned', count: 2, tone: 'medical',
    items: [
      { title: 'VPS Hardening', meta: 'Assigned to Eng' },
      { title: 'Travel Plan Review', meta: 'Assigned to XO' }
    ]
  },
  {
    label: 'In Progress', count: 4, tone: 'science',
    items: [
      { title: 'Engine Diagnostics', meta: '72% Complete' },
      { title: 'Bot Refactor', meta: '55% Complete' },
      { title: 'Data Pipeline', meta: 'In Progress' }
    ]
  },
  {
    label: 'Awaiting Review', count: 2, tone: 'engineering',
    items: [
      { title: 'Handoff Process', meta: 'Eng Review' },
      { title: 'Research Report', meta: 'Ready for Review' }
    ]
  },
  {
    label: 'Completed', count: 8, tone: 'status',
    items: [
      { title: 'Daily Brief 0619', meta: 'Completed' },
      { title: 'Medical Report 0619', meta: 'Completed' },
      { title: 'Backup Verification', meta: 'Completed' }
    ]
  }
];

// ── Today's Briefing ─────────────────────────────────────────────────────────
export const todaysBriefing: BriefingItem[] = [
  { label: 'Operational Readiness', value: '94%', tone: 'status' },
  { label: 'Risk Posture', value: 'LOW', tone: 'status' },
  { label: 'Threat Status', value: 'NOMINAL', tone: 'status' },
  { label: 'Weather / Space', value: 'CLEAR', tone: 'status' },
  { label: 'Travel Schedule', value: '2 EVENTS', tone: 'command' }
];

// ── Engineering Queue Summary ────────────────────────────────────────────────
export const engineeringQueueSummary: QueueItem[] = [
  { label: 'Awaiting Triage', count: 3, tone: 'command' },
  { label: 'In Progress', count: 4, tone: 'medical' },
  { label: 'Awaiting Review', count: 2, tone: 'science' },
  { label: 'Completed (24h)', count: 5, tone: 'status' }
];

// ── Missions ────────────────────────────────────────────────────────────────
// Shape mirrors mission-registry-reader.js rows.
export const missions: Mission[] = [
  {
    mission_id: 'USS-TJR-MSN-0072',
    title: 'Starship LCARS Web Portal — Phase 1',
    priority: 'P1',
    status: 'IN_PROGRESS',
    owner: 'Captain TJR',
    specialist: 'UX Design Officer',
    reference: 'PORTAL-P1',
    department: 'command'
  },
  {
    mission_id: 'USS-TJR-MSN-0011',
    title: 'Supabase Knowledge Migration',
    priority: 'P0',
    status: 'BLOCKED',
    owner: 'Chief Engineer',
    specialist: 'Coder Agent',
    reference: 'KNOW-MIG',
    department: 'engineering'
  },
  {
    mission_id: 'USS-TJR-MSN-0040A',
    title: 'Number One Slack Bot — WP3 Advanced Features',
    priority: 'P2',
    status: 'ASSIGNED',
    owner: 'Chief of Staff',
    specialist: 'Coder Agent',
    reference: 'NO-WP3',
    department: 'operations'
  },
  {
    mission_id: 'USS-TJR-MSN-0035',
    title: 'Command Centre Integration Layer',
    priority: 'P1',
    status: 'REVIEW',
    owner: 'Chief Engineer',
    specialist: 'QA & Test Officer',
    reference: 'CC-INT',
    department: 'engineering'
  },
  {
    mission_id: 'USS-TJR-MSN-HEALTH-001',
    title: 'Health Data Architecture (ADR-HEALTH-001)',
    priority: 'P2',
    status: 'ACTIVE',
    owner: 'Medical Officer',
    specialist: 'Knowledge Officer',
    reference: 'HEALTH-ARCH',
    department: 'medical'
  },
  {
    mission_id: 'USS-TJR-MSN-OR-INT',
    title: 'OR Intelligence Brief Pipeline',
    priority: 'P2',
    status: 'IN_PROGRESS',
    owner: 'Science Officer',
    specialist: 'Tactical Analysis Officer',
    reference: 'OR-INTEL',
    department: 'science'
  }
];

export const missionSummary: MissionSummary = {
  total: 72,
  active: 6,
  in_progress: 3,
  completed: 64,
  blocked: 1,
  by_priority: { P0: 1, P1: 2, P2: 3, P3: 0 },
  timestamp: `${SHIP.date}T08:00:00Z`
};

// ── Departments (Engineering page + Captain's Chair grid) ────────────────────
export const departments: Department[] = [
  {
    key: 'command',
    name: 'Command',
    lead: 'Captain TJR',
    status: 'On the bridge',
    tone: 'command',
    summary: 'Daily posture set. Mission priorities confirmed for the cycle.',
    metrics: [
      { label: 'Active Missions', value: '6' },
      { label: 'Decisions Pending', value: '2' }
    ]
  },
  {
    key: 'engineering',
    name: 'Engineering',
    lead: 'Chief Engineer',
    status: 'Systems nominal',
    tone: 'status',
    summary: 'Command Centre backend operational. One migration blocked on review.',
    metrics: [
      { label: 'Services Up', value: '7 / 8' },
      { label: 'Build', value: 'Passing' }
    ]
  },
  {
    key: 'operations',
    name: 'Operations',
    lead: 'Number One',
    status: 'Coordinating',
    tone: 'operations',
    summary: 'Crew assignments balanced. Slack runtime standing by for WP3.',
    metrics: [
      { label: 'Crew On Duty', value: '6' },
      { label: 'Queue Depth', value: '4' }
    ]
  },
  {
    key: 'medical',
    name: 'Medical / Wellness',
    lead: 'Medical Officer',
    status: 'Monitoring',
    tone: 'medical',
    summary: 'Recovery trending positive. Protected focus block scheduled.',
    metrics: [
      { label: 'Recovery', value: '78%' },
      { label: 'Sleep', value: '7h 10m' }
    ]
  },
  {
    key: 'science',
    name: 'Astrometrics',
    lead: 'Science Officer',
    status: 'Analysing',
    tone: 'science',
    summary: 'Latest OR intelligence brief generated. Three emerging themes flagged.',
    metrics: [
      { label: 'Active Research', value: '5' },
      { label: 'Reports Ready', value: '3' }
    ]
  },
  {
    key: 'status',
    name: 'Ship Status',
    lead: 'Computer Core',
    status: 'Operational',
    tone: 'status',
    summary: 'All core integrations green: Dashy, Slack, Commander, Supabase.',
    metrics: [
      { label: 'Uptime', value: '99.9%' },
      { label: 'Integrations', value: '5 / 5' }
    ]
  }
];

// ── Alerts (AlertPanel across pages) ─────────────────────────────────────────
export const alerts: Alert[] = [
  {
    id: 'ALRT-001',
    level: 'warning',
    title: 'Mission MSN-0011 blocked',
    detail: 'Supabase migration awaiting schema sign-off from Chief Engineer.',
    source: 'Mission Registry',
    timestamp: `${SHIP.date}T07:42:00Z`
  },
  {
    id: 'ALRT-002',
    level: 'info',
    title: 'OR Intelligence brief ready',
    detail: 'Daily operational resilience brief generated and archived.',
    source: 'Intelligence Pipeline',
    timestamp: `${SHIP.date}T06:15:00Z`
  },
  {
    id: 'ALRT-003',
    level: 'nominal',
    title: 'All integrations green',
    detail: 'Dashy, Slack bot, Commander backend, Context Assembly, Supabase online.',
    source: 'System Health',
    timestamp: `${SHIP.date}T06:00:00Z`
  }
];

// ── Number One (crew) ────────────────────────────────────────────────────────
export const crew: CrewMember[] = [
  {
    id: 'USS-TJR-002',
    name: 'Chief of Staff',
    role: 'Mission intake & coordination',
    department: 'command',
    status: 'On duty',
    tone: 'command',
    focus: 'Triaging mission queue; prepping XO review gate.'
  },
  {
    id: 'USS-TJR-003',
    name: 'Chief Engineer',
    role: 'Systems & runtime',
    department: 'engineering',
    status: 'On duty',
    tone: 'engineering',
    focus: 'Unblocking Supabase migration on MSN-0011.'
  },
  {
    id: 'USS-TJR-004',
    name: 'Coder Agent',
    role: 'Implementation',
    department: 'operations',
    status: 'Assigned',
    tone: 'operations',
    focus: 'Number One WP3 advanced features.'
  },
  {
    id: 'USS-TJR-005',
    name: 'QA & Test Officer',
    role: 'Verification',
    department: 'science',
    status: 'On duty',
    tone: 'science',
    focus: 'Smoke testing Command Centre integration layer.'
  },
  {
    id: 'USS-TJR-006',
    name: 'Knowledge Officer',
    role: 'Knowledge & memory',
    department: 'medical',
    status: 'On duty',
    tone: 'medical',
    focus: 'Archiving health architecture decisions.'
  },
  {
    id: 'USS-TJR-009',
    name: 'UX Design Officer',
    role: 'Experience & interface',
    department: 'science',
    status: 'On duty',
    tone: 'science',
    focus: 'LCARS portal Phase 1 layout and components.'
  }
];

// ── XO Brief (intelligence) ──────────────────────────────────────────────────
export const intelligenceBrief: IntelligenceBrief = {
  id: 'BRIEF-2026-06-19',
  title: 'Operational Resilience Brief',
  generated: `${SHIP.date}T06:15:00Z`,
  summary:
    'Steady operating picture. One blocker on the critical path; wellness and intelligence systems nominal. Recommend protecting the afternoon focus block.',
  sections: [
    {
      heading: 'Command Posture',
      body: 'Six active missions, one blocked. Command tempo steady with two decisions pending Captain review.'
    },
    {
      heading: 'Risks & Blockers',
      body: 'MSN-0011 (Supabase migration) is the single critical-path blocker. Engineering is engaged; expected clearance within the cycle.'
    },
    {
      heading: 'Wellness',
      body: 'Recovery at 78% and trending up. Sleep within target. Protected focus block recommended this afternoon.'
    },
    {
      heading: 'Recommendations',
      body: 'Approve LCARS Portal Phase 1, clear MSN-0011 dependency, and hold the wellness block.'
    }
  ],
  themes: ['Critical-path dependency', 'Recovery momentum', 'Portal readiness']
};

// ── Medical / Wellness ───────────────────────────────────────────────────────
export const wellness: WellnessMetric[] = [
  { label: 'Recovery', value: '78%', trend: 'up', tone: 'status' },
  { label: 'Sleep', value: '7h 10m', trend: 'steady', tone: 'medical' },
  { label: 'Strain', value: 'Moderate', trend: 'down', tone: 'command' },
  { label: 'Mood', value: 'Steady', trend: 'steady', tone: 'medical' },
  { label: 'Hydration', value: 'On target', trend: 'up', tone: 'status' },
  { label: 'Focus Blocks', value: '2 protected', trend: 'steady', tone: 'science' }
];

// ── Operations (service / integration status) ────────────────────────────────
// Each entry corresponds to an integration the portal must NOT break.
export const services: ServiceStatus[] = [
  {
    name: 'Dashy Control Deck',
    state: 'operational',
    detail: 'Starfleet command bridge dashboard (port 8000).',
    tone: 'status'
  },
  {
    name: 'Number One Slack Bot',
    state: 'operational',
    detail: 'Commander runtime; Slack ↔ Supabase integration online.',
    tone: 'status'
  },
  {
    name: 'Commander Backend',
    state: 'operational',
    detail: 'Command Centre Express API (port 5050).',
    tone: 'status'
  },
  {
    name: 'Context Assembly',
    state: 'operational',
    detail: 'Captain brief / operating picture context service.',
    tone: 'status'
  },
  {
    name: 'Supabase',
    state: 'operational',
    detail: 'Knowledge prototype, missions and decisions registries.',
    tone: 'status'
  },
  {
    name: 'Intelligence Pipeline',
    state: 'degraded',
    detail: 'One upstream source slow; brief generation unaffected.',
    tone: 'command'
  }
];

// ── Knowledge Base ───────────────────────────────────────────────────────────
export const knowledgeArticles: KnowledgeArticle[] = [
  {
    id: 'ADR-HEALTH-001',
    title: 'Health Data Architecture',
    category: 'Architecture Decision Record',
    owner: 'Knowledge Officer',
    updated: '2026-06-14',
    excerpt: 'Defines storage, privacy and access model for captain health data.',
    department: 'medical'
  },
  {
    id: 'ADR-0001',
    title: 'Decision Rights & Enforcement Framework',
    category: 'Architecture Decision Record',
    owner: 'Chief of Staff',
    updated: '2026-06-10',
    excerpt: 'Establishes ADR enforcement with Supabase-backed registry.',
    department: 'command'
  },
  {
    id: 'KB-MISSION-LIFECYCLE',
    title: 'Mission Lifecycle Standard',
    category: 'Governance',
    owner: 'Chief of Staff',
    updated: '2026-06-08',
    excerpt: 'Intake → assignment → execution → review → closure → archive.',
    department: 'operations'
  },
  {
    id: 'KB-SUPABASE-PROTOTYPE',
    title: 'Supabase Knowledge Prototype',
    category: 'Engineering',
    owner: 'Chief Engineer',
    updated: '2026-06-05',
    excerpt: 'Schema, ingestion, keyword + semantic retrieval and access logging.',
    department: 'engineering'
  },
  {
    id: 'KB-OR-INTEL',
    title: 'OR Intelligence Pipeline',
    category: 'Science',
    owner: 'Science Officer',
    updated: '2026-06-12',
    excerpt: 'Four-stage brief pipeline with Tactical Analysis Officer stage.',
    department: 'science'
  }
];
