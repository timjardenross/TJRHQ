// Shared contract for the Human Systems Workbench — imported by both the
// unified API route (src/app/api/human-systems/route.ts) and the page, so the
// wire format has a single source of truth.

export type Domain = 'recovery' | 'medical' | 'readiness';

export type PostureBand = 'STRONG' | 'STABLE' | 'FRAGILE' | 'REST' | 'UNKNOWN';
export type Band = 'good' | 'moderate' | 'limited' | 'rest' | 'unknown';

/** VNext consolidation (Human_Systems_Workbench_VNext_Consolidation_Mission_
 *  Scope.md §6) — a higher-order operating mode replacing the narrow
 *  posture RPC's STRONG/STABLE/FRAGILE/REST bands, deterministic from
 *  today's latest capacity_checkins row (spec §36). ENGAGE only when
 *  capacity is sustainable AND nothing else flags; RESET is the one state
 *  the old posture engine had no equivalent for (short-regulation-first,
 *  distinct from RECOVER's rest-priority). */
export type SystemPostureBand = 'ENGAGE' | 'STEADY' | 'PROTECT' | 'RECOVER' | 'RESET' | 'UNKNOWN';

export type ManagementLever = 'reduce_load' | 'regulate' | 'recover' | 'redesign';

/** Spec §11 — TOO MUCH / SUSTAINABLE / NOT ENOUGH, derived from capacity +
 *  stimulation together, not a single numeric gauge. */
export type CapacityBalance = 'too_much' | 'sustainable' | 'not_enough' | 'unknown';

export interface CapacityLoad {
  label: string;
  count: number; // check-ins today that selected this load
}

export interface NextMove {
  lever: ManagementLever | null;
  intervention_title: string | null;
  intervention_description: string | null;
  /** Present only when the suggestion comes from a real accepted
   *  capacity_intervention_events row (WP04) rather than the legacy
   *  capacity_checkins.selected_action text fallback. */
  event_id: number | null;
  event_source: 'capacity_q9' | 'helpme' | 'guide' | 'manual' | null;
  accepted_at: string | null;
  outcome: 'better' | 'same' | 'worse' | 'not_completed' | 'unknown' | null;
}

/** Cross-domain KPI strip shown above every tab (design proposition §4). Every
 *  domain payload carries the same block so switching tabs never blanks it. */
export interface Kpis {
  posture: PostureBand;
  lp_score: number | null;
  lp_band: Band;
  sessions_7d: number;
  capacity_band: Band;
  sleep_hours: number | null;
  checkins_today: number; // raw count of today's capacity_checkins rows (capacity_checkins_today view, replaces the retired 3x/day pulse model, 2026-08-21) — unlimited per day, not a percentage
  latest_capacity_state: string | null; // 'green' | 'orange' | 'red' | null, from capacity_checkins_today
  /** VNext consolidation (spec §6) — replaces `posture` as the primary
   *  hero indicator across all three domain views. Computed once in
   *  buildKpis() from the same latest capacity_checkins row every domain
   *  already shares via Ctx, so Medical/Readiness see the same value
   *  Recovery does — no per-domain drift. `posture` (the old RPC-based
   *  STRONG/STABLE/FRAGILE/REST band) is kept on this type for now rather
   *  than removed outright — deferred to the WP05-10 pass rather than
   *  risking a silent break in any other consumer of the old field. */
  system_posture: SystemPostureBand;
}

export interface WellnessInsight {
  narrative: string | null;
  risk_flags: string[];
  positive_flags: string[];
  wins: string[];
  insight_date: string | null;
}

export interface RecoveryPayload {
  domain: 'recovery';
  kpis: Kpis;
  posture: PostureBand;
  posture_message: string;
  capacity_band: Band;
  capacity_message: string;
  mission_guidance: string;
  best_window: string;
  sleep_hours: number | null;
  sleep_quality: string | null;
  nervous_system: string | null;
  energy: string | null;
  /** "MY CAPACITY TODAY" telemetry (capacity_checkins_today view,
   *  2026-08-21) — replaces the retired 3x/day recovery-pulse model.
   *  There is no slot concept any more (no morning/midday/evening): a
   *  Captain can log an unlimited number of capacity check-ins per day, so
   *  this is just today's raw count plus the latest reading. */
  checkins_today: number;
  latest_capacity_state: string | null;
  latest_regulation_state: string | null;
  confidence_label: string;
  wellness: WellnessInsight;
  /** true when the posture engine had a real check-in to work from. */
  data_available: boolean;

  // ── VNext consolidation additions (WP02-04) ──────────────────────────────
  system_posture: SystemPostureBand;
  system_posture_message: string;
  stimulation_state: string | null;
  pain_state: string | null;
  pain_score: number | null;
  executive_function: string | null;
  compensation_load: string | null;
  capacity_balance: CapacityBalance;
  /** Today's active_loads across every capacity check-in, ranked by
   *  selection count (spec §7 — "top load today: Sensory input · selected
   *  in 2/2 check-ins"). */
  active_loads_today: CapacityLoad[];
  /** identified_needs from the single latest check-in only (spec §9 — "do
   *  not show 15 empty tiles", current selection only, not aggregated). */
  identified_needs_latest: string[];
  next_move: NextMove;
  /** WP09 System Learning "What I Know" layer — a directly observed fact,
   *  not an interpretation (spec §17 example: "8 check-ins recorded in
   *  the last 7 days"). */
  checkins_last_7d: number;
}

export interface RecoveryIndex {
  key: string;
  label: string;
  band: Band;
  detail: string;
}

export interface EnergyDomain {
  key: string;
  label: string;
  band: Band;
  value: string | null;
}

export interface TrendRow {
  log_date: string;
  energy: string | null;
  sleep_quality: string | null;
  nervous_system_state: string | null;
  pain_score: number | null;
}

/** Spec §19 — capacity debt trend from evening reflections
 *  (capacity_checkins.checkin_type='evening'). */
export interface CapacityDebt {
  days_with_debt: number; // 'yes' or 'maybe' in the window
  days_total: number; // evening reflections logged in the window
  window_days: number;
}

/** Spec §20 — recovery-duration summary from deep-check
 *  capacity_checkins.recovery_duration. Only meaningful once enough
 *  records exist (spec: "only produce summary when enough records
 *  exist") — `sample_size` lets the view decide whether to show it. */
export interface RecoveryDurationSummary {
  most_common: string | null;
  most_common_count: number;
  sample_size: number;
}

/** Spec §18 — What Helps Me. Mirrors the Capacity Bot's own
 *  personal_effectiveness_summary() (intervention_engine.py) — counts
 *  only, never a percentage below the sample floor (spec §15/§31). */
export interface InterventionEffectiveness {
  intervention_id: string;
  title: string;
  attempts: number;
  better: number;
  same: number;
  worse: number;
  not_completed: number;
  meets_sample_threshold: boolean;
  /** Most common help_state this intervention was used for, when any
   *  /helpme-sourced events exist for it (spec: "most often useful
   *  when: Stretched + high stimulation"). */
  common_context: string | null;
}

/** Spec §23 — a recurring load/state combination that shows up often
 *  enough on stretched/depleted days to be worth redesigning around
 *  rather than repeatedly regulating. Auto-detected, read-only for V02
 *  (spec: "V02 may ship with defaults... capture as they become
 *  obvious" — no manual-entry form yet). */
export interface RedesignCandidate {
  load: string;
  stretched_or_depleted_count: number;
  window_days: number;
}

export interface MedicalPayload {
  domain: 'medical';
  kpis: Kpis;
  life_participation: {
    score: number | null;
    band: Band;
    components: {
      movement: boolean;
      pleasure: string | null;
      social: boolean;
      sitting_minutes: number;
      sitting_baseline: number;
      workload: string;
    };
  };
  /** Renamed from "Energy Domains" (spec §15) — same Physical/Cognitive/
   *  Emotional/Social domains plus a new Sensory domain. */
  capacity_domains: EnergyDomain[];
  /** Renamed from "Recovery Indexes" (spec §16) — Sleep/Nervous System/
   *  Pain Burden/Sensory Load/Recovery Time inputs. Deliberately does NOT
   *  re-display Capacity — Capacity is the outcome these conditions
   *  influence, not one of them. */
  recovery_conditions: RecoveryIndex[];
  trends: TrendRow[];
  capacity_debt: CapacityDebt;
  recovery_duration: RecoveryDurationSummary;
  intervention_effectiveness: InterventionEffectiveness[];
  redesign_candidates: RedesignCandidate[];
}

export interface ReadinessPayload {
  domain: 'readiness';
  kpis: Kpis;
  last_session: {
    id: string;
    type: string;
    status: string;
    date: string;
    duration: number | null;
  } | null;
  weekly_count: number;
  last_checkin_at: string | null;
}

export type Payload = RecoveryPayload | MedicalPayload | ReadinessPayload;

// ── Presentation helpers (shared by the domain views) ────────────────────────

import type { BadgeStatus } from '@/components/ui';

/** Posture band → Badge status. STABLE reads as info (settled), STRONG success. */
export function postureStatus(p: PostureBand): BadgeStatus {
  switch (p) {
    case 'STRONG': return 'success';
    case 'STABLE': return 'info';
    case 'FRAGILE': return 'warning';
    case 'REST': return 'error';
    default: return 'neutral';
  }
}

/** System Posture → Badge status (spec §6). RESET reads as warning, not
 *  error — it's a short regulation-first detour, not a depletion state. */
export function systemPostureStatus(p: SystemPostureBand): BadgeStatus {
  switch (p) {
    case 'ENGAGE': return 'success';
    case 'STEADY': return 'info';
    case 'PROTECT': return 'warning';
    case 'RESET': return 'warning';
    case 'RECOVER': return 'error';
    default: return 'neutral';
  }
}

export const CAPACITY_BALANCE_LABEL: Record<CapacityBalance, string> = {
  too_much: 'Too Much',
  sustainable: 'Sustainable',
  not_enough: 'Not Enough',
  unknown: 'No data',
};

/** capacity_state ('green'|'orange'|'red'|null, from capacity_checkins) →
 *  Badge status. THE primary capacity indicator (spec §5 — "Capacity is
 *  the primary state") — every place that shows Capacity Today should
 *  read from the same latest_capacity_state field and use this mapping,
 *  not the older RPC-derived capacity_band. */
export function capacityStateStatus(state: string | null): BadgeStatus {
  switch (state) {
    case 'green': return 'success';
    case 'orange': return 'warning';
    case 'red': return 'error';
    default: return 'neutral';
  }
}

export const CAPACITY_STATE_LABEL: Record<string, string> = {
  green: '🟢 Sustainable', orange: '🟠 Stretched', red: '🔴 Depleted',
};

/** good/moderate/limited/rest band → Badge status. */
export function bandStatus(b: Band): BadgeStatus {
  switch (b) {
    case 'good': return 'success';
    case 'moderate': return 'info';
    case 'limited': return 'warning';
    case 'rest': return 'error';
    default: return 'neutral';
  }
}

export const BAND_LABEL: Record<Band, string> = {
  good: 'Good',
  moderate: 'Moderate',
  limited: 'Limited',
  rest: 'Rest',
  unknown: 'No data',
};
