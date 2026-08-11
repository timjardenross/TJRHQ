// Shared contract for the Human Systems Workbench — imported by both the
// unified API route (src/app/api/human-systems/route.ts) and the page, so the
// wire format has a single source of truth.

export type Domain = 'recovery' | 'medical' | 'readiness';

export type PostureBand = 'STRONG' | 'STABLE' | 'FRAGILE' | 'REST' | 'UNKNOWN';
export type Band = 'good' | 'moderate' | 'limited' | 'rest' | 'unknown';

/** Cross-domain KPI strip shown above every tab (design proposition §4). Every
 *  domain payload carries the same block so switching tabs never blanks it. */
export interface Kpis {
  posture: PostureBand;
  lp_score: number | null;
  lp_band: Band;
  sessions_7d: number;
  capacity_band: Band;
  sleep_hours: number | null;
  pulse_confidence: number; // 0–100, recovery_confidence_today
  pulses_completed: number; // 0–3 today (morning/midday/evening — 3x/day model, 2026-08-10)
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
  /** Pulse completion for today. Canonical cadence (2026-08-10) is
   *  morning/midday/evening — `end_of_day` is a retired bucket kept here
   *  only because recovery_confidence_today still exposes the column for
   *  backward compat (matches RecoveryConfidencePanel's own deferred
   *  reconciliation); the UI no longer renders it as a 4th slot. */
  pulses: { morning: boolean; midday: boolean; end_of_day: boolean; evening: boolean };
  confidence_label: string;
  wellness: WellnessInsight;
  /** true when the posture engine had a real check-in to work from. */
  data_available: boolean;
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
  energy_domains: EnergyDomain[];
  recovery_indexes: RecoveryIndex[];
  trends: TrendRow[];
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
