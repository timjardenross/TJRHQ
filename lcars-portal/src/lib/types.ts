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

/** Research queue item (Astrometrics / XO Brief). */
export interface ResearchQueueItem {
  id: string;
  title: string;
  location: string;
  status: 'in_progress' | 'queued' | 'completed';
  tone: StatusTone;
}

/** Crew headcount per department (Number One / XO Command). */
export interface DeptCrewCount {
  key: DepartmentKey;
  count: number;
  status: StatusTone;
}

/** Latest discovery highlight (Astrometrics). */
export interface LatestDiscovery {
  designation: string;
  classification: string;
  distance: string;
  detail: string;
}

// ── ROS-001 v1.1 — Recovery Operating System types ────────────────────────────

export type RecoveryPostureBand = 'STRONG' | 'STABLE' | 'FRAGILE' | 'REST' | 'UNKNOWN';
export type CapacityBand = 'GOOD' | 'MODERATE' | 'LIMITED' | 'REST' | 'UNKNOWN';
export type NervousSystemState = 'calm' | 'activated' | 'dysregulated';

/** Operational recovery posture — from get_recovery_posture(). */
export interface RecoveryPosture {
  posture: RecoveryPostureBand;
  posture_message: string;
  capacity_band: CapacityBand;
  capacity_message: string;
  best_window: string;
  mission_guidance: string;
  data_available: boolean;
}

/** Today's body context signals — from analytics_health_daily. */
export interface BodyContext {
  sleep_hours: number;
  sleep_quality: 'Good' | 'Fair' | 'Poor';
  cpap_compliant: boolean;
  nervous_system_state: NervousSystemState;
  energy: 'High' | 'Moderate' | 'Low';
  body_signals: 'Low' | 'Moderate' | 'High';
  sitting_window_minutes: number;
}

/** Mission load guidance derived from recovery posture. */
export interface MissionLoadGuidanceData {
  posture: RecoveryPostureBand;
  active_mission_id: string;
  active_mission_safe: boolean;
  new_starts_recommended: boolean;
  decisions_pending: number;
  defer_decisions: boolean;
}

/** One of the four recovery indexes displayed in Medical Bay. */
export interface RecoveryIndex {
  key: 'sleep' | 'nervous_system' | 'energy' | 'capacity';
  label: string;
  band: 'good' | 'moderate' | 'limited' | 'rest' | 'unknown';
  detail: string;
  tone: StatusTone;
}

/** Life Participation score and its five component signals. */
export interface LifeParticipationScore {
  score: number; // 0–100
  band: 'good' | 'moderate' | 'limited' | 'rest';
  movement_done: boolean;
  pleasure_marker: string | null;
  social_noted: boolean;
  sitting_minutes: number;
  sitting_baseline_minutes: number;
  workload_constraint: 'none' | 'light' | 'moderate' | 'severe' | 'unknown';
}

/** Stage 1 / Stage 2 display — no countdown, no progress bar. */
export interface StageStatus {
  stage: 1 | 2;
  label: string;
  description: string;
  tone: StatusTone;
}

/** A single data point for the PosturePatternChart (last N days). */
export interface PostureDataPoint {
  date: string; // ISO YYYY-MM-DD
  posture: RecoveryPostureBand;
  score: number | null; // Medical Officer only — not displayed to Captain
}

/** Recent posture history for the Medical Bay pattern chart. */
export interface PostureHistory {
  days: PostureDataPoint[];
  period_label: string; // e.g. "Last 7 days"
}

/**
 * Emotional Load Flag — raised when nervous system state is activated or
 * dysregulated for 3+ of the last 7 days (WP2 Stage 1 guardrail).
 */
export interface EmotionalLoadFlag {
  raised: boolean;
  activated_days: number;
  dysregulated_days: number;
  period: string; // e.g. "Last 7 days"
  message: string;
}

/** 7-day and 30-day pattern summary for Medical Bay. */
export interface WeeklyPatternSummary {
  period_7d: {
    strong: number;
    stable: number;
    fragile: number;
    rest: number;
    unknown: number;
  };
  period_30d: {
    stable_or_strong: number;
    total_recorded: number;
  };
  direction: 'settling' | 'steady' | 'variable' | 'insufficient_data';
  direction_label: string;
}

/** Full Recovery Brief — WP7 morning brief format. */
export interface RecoveryBrief {
  stardate: string;
  generated: string; // ISO timestamp
  posture: RecoveryPostureBand;
  posture_message: string;
  sleep_summary: string;
  nervous_system: NervousSystemState;
  energy: string;
  capacity_message: string;
  best_window: string;
  afternoon_note: string;
  guidance: string[];
  load_summary: string;
  active_mission_note: string;
  new_starts_note: string;
  decisions_note: string;
  fleet_summary: string;
}
