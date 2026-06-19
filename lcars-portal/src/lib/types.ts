/**
 * Shared types for the LCARS portal.
 *
 * Where a type maps onto an existing Command Centre backend response, the
 * source endpoint is noted so Phase 2 can map live data onto the same shape
 * (see core/command-centre/backend/api/*). Phase 1 fills these with mock data.
 */

export type DepartmentKey =
  | 'command'
  | 'engineering'
  | 'operations'
  | 'medical'
  | 'science'
  | 'status';

export type StatusTone =
  | 'command'
  | 'engineering'
  | 'operations'
  | 'medical'
  | 'science'
  | 'status'
  | 'neutral';

/** Mirrors mission-registry-reader.js mission rows. */
export interface Mission {
  mission_id: string;
  title: string;
  priority: 'P0' | 'P1' | 'P2' | 'P3' | '—';
  status: string;
  owner: string;
  specialist: string;
  reference: string;
  department: DepartmentKey;
}

/** Mirrors GET /api/v1/missions/summary. */
export interface MissionSummary {
  total: number;
  active: number;
  in_progress: number;
  completed: number;
  blocked: number;
  by_priority: { P0: number; P1: number; P2: number; P3: number };
  timestamp: string;
}

export interface Department {
  key: DepartmentKey;
  name: string;
  lead: string;
  status: string;
  tone: StatusTone;
  summary: string;
  metrics: { label: string; value: string }[];
}

export interface Alert {
  id: string;
  level: 'critical' | 'warning' | 'info' | 'nominal';
  title: string;
  detail: string;
  source: string;
  timestamp: string;
}

/** Mirrors GET /api/v1/context/captain-brief (subset). */
export interface CaptainBrief {
  stardate: string;
  greeting: string;
  headline: string;
  priorities: string[];
  posture: { label: string; value: string; tone: StatusTone }[];
}

/** Mirrors GET /api/v1/context/operating-picture (subset). */
export interface OperatingPicture {
  readiness: string;
  activeMissions: number;
  blockers: number;
  crewOnDuty: number;
}

export interface CrewMember {
  id: string;
  name: string;
  role: string;
  department: DepartmentKey;
  status: string;
  tone: StatusTone;
  focus: string;
}

/** Mirrors GET /api/v1/personal-health / context/health (subset). */
export interface WellnessMetric {
  label: string;
  value: string;
  trend: 'up' | 'down' | 'steady';
  tone: StatusTone;
}

/** Mirrors GET /api/v1/health/services (subset). */
export interface ServiceStatus {
  name: string;
  state: 'operational' | 'degraded' | 'offline';
  detail: string;
  tone: StatusTone;
}

/** Mirrors GET /api/v1/intelligence/latest (subset) — drives the XO Brief. */
export interface BriefSection {
  heading: string;
  body: string;
}

export interface IntelligenceBrief {
  id: string;
  title: string;
  generated: string;
  summary: string;
  sections: BriefSection[];
  themes: string[];
}

export interface KnowledgeArticle {
  id: string;
  title: string;
  category: string;
  owner: string;
  updated: string;
  excerpt: string;
  department: DepartmentKey;
}

/** Ship system health bar (0–100). */
export interface ShipSystemStatus {
  label: string;
  value: number;
}

/** Captain's daily schedule entry. */
export interface TimelineEvent {
  time: string;
  title: string;
  status: 'completed' | 'in_progress' | 'scheduled';
}

/** Decision item awaiting captain approval. */
export interface DecisionItem {
  id: string;
  title: string;
  detail: string;
  from: string;
}

/** Single column in the mission Kanban board. */
export interface MissionBoardColumn {
  label: string;
  count: number;
  tone: DepartmentKey;
  items: { title: string; meta: string }[];
}

/** Single row in Today's Briefing / summary panels. */
export interface BriefingItem {
  label: string;
  value: string;
  tone: StatusTone;
}

/** Engineering / ops queue summary row. */
export interface QueueItem {
  label: string;
  count: number;
  tone: StatusTone;
}
