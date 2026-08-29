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

/** V3 Mission 1 (TJR_Human_Systems_Workbench_V3_Mission_and_Change_Proposal.md
 *  §5) — the TRAJECTORY signal: "what condition has my system been
 *  operating in over days/weeks?", kept strictly separate from
 *  SystemPostureBand (the NOW signal, unchanged by V3). Mirrors
 *  burnout_profile.system_trajectory (migration 0154) and the bucket names
 *  core/health/burnout_trajectory.py's compute_burnout_trajectory() /
 *  this file's computeStrategicPosture() (api/human-systems/route.ts)
 *  return — the two must stay in lock-step (see that function's header
 *  comment). §2: "These must never be collapsed into one score." */
export type SystemTrajectory =
  | 'insufficient_data' | 'stable' | 'accumulating_strain' | 'sustained_high_strain'
  | 'burnout_like_depletion' | 'recovery_signals_emerging' | 'rebuilding';

/** V3 doc §18 "Confidence" line (e.g. "Moderate — 12 relevant check-ins
 *  across 18 days") — sample-size derived, never a fabricated percentage
 *  (Rule F: "if data is insufficient, say so; do not fabricate a
 *  trajectory"). */
export type TrajectoryConfidence = 'low' | 'moderate' | 'high';

/** V3 doc §7 — Strategic Posture, TRAJECTORY-aware and distinct from
 *  SystemPostureBand. Shares engage/steady/protect/recover vocabulary
 *  (lowercased) with SystemPostureBand so Rule A ("today's capacity
 *  improves but sustained strain remains high -> strategic posture must
 *  stay protective, never jump to engage") is a same-scale comparison;
 *  stabilise/re_engage/rebuild/redesign are the additional Burnout
 *  Recovery Stage postures (§8) SystemPostureBand has no equivalent for.
 *  Mirrors burnout_profile.strategic_posture. */
export type StrategicPosture =
  | 'engage' | 'steady' | 'protect' | 'recover' | 'stabilise' | 're_engage' | 'rebuild' | 'redesign';

/** V3 doc §8 — Burnout Recovery Stages (PROTECT -> STABILISE -> RECOVER ->
 *  RE-ENGAGE -> REBUILD -> REDESIGN). Mirrors
 *  burnout_profile.current_recovery_stage; null when the trajectory is
 *  'stable' or 'insufficient_data' — there is no active recovery stage to
 *  name. */
export type RecoveryStage = 'protect' | 'stabilise' | 'recover' | 're_engage' | 'rebuild' | 'redesign';

/** V3 doc §5.1 "User framing" — the user's OWN self-identification,
 *  captured on capacity_checkins.user_burnout_framing (migration 0153,
 *  deep-check tier). Strictly independent of SystemTrajectory (the
 *  system's own observation) — the two must never be silently converted
 *  into each other (§5.1: "The system must never silently convert its
 *  observation into a diagnosis"). null means no deep-check has ever
 *  asked/answered this yet, distinct from the explicit 'not_set' value a
 *  user can choose (V3 doc's own enumeration lists "not set" as one of
 *  the framing options, alongside a genuine "I don't want a label"). */
export type UserBurnoutFraming =
  | 'identify_as_burnout' | 'may_be_in_burnout' | 'recovering_from_burnout' | 'no_label' | 'not_set';

export const USER_BURNOUT_FRAMING_LABEL: Record<UserBurnoutFraming, string> = {
  identify_as_burnout: 'Identifies this period as autistic burnout',
  may_be_in_burnout: 'May be in burnout',
  recovering_from_burnout: 'Recovering from burnout',
  no_label: "Doesn't want a label",
  not_set: 'Not sure yet',
};

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
  /** Midday micro check-in (checkin_type='midday', migration 0169,
   *  2026-08-25) — a separate 2-tap pulse from the bot's new 08:00/13:00/
   *  20:00 proactive cadence. Distinct from checkins_today/
   *  latest_capacity_state above (still scoped to checkin_type='capacity'
   *  only) — this is informational, not a substitute for a real check-in. */
  has_midday_checkin: boolean;
  latest_midday_capacity_state: string | null;
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

  // ── V3 Mission 1 — Burnout / Sustained-Strain Trajectory ────────────────
  // (TJR_Human_Systems_Workbench_V3_Mission_and_Change_Proposal.md §5-§8).
  // Computed by computeStrategicPosture() in the API route, a TypeScript
  // mirror of core/health/burnout_trajectory.py's
  // compute_burnout_trajectory() — see that route function's header
  // comment for the lock-step requirement. Never collapsed into
  // `system_posture` above — that field stays NOW-only and unchanged.
  system_trajectory: SystemTrajectory;
  trajectory_confidence: TrajectoryConfidence;
  strategic_posture: StrategicPosture;
  strategic_posture_message: string;
  current_recovery_stage: RecoveryStage | null;
  /** The user's own self-identification (V3 doc §5.1), from the latest
   *  check-in that has one set — not aggregated/derived, displayed
   *  verbatim (or via USER_BURNOUT_FRAMING_LABEL) exactly as chosen. */
  user_burnout_framing: UserBurnoutFraming | null;

  // ── V3 Mission 4 — Personal Experiment Engine (§15/§19) ──────────────────
  // Every 'proposed'/'active' experiment plus recently completed/stopped
  // ones (see buildRecovery()'s fetch window) — ordered newest-first by
  // the API. RecoveryView.tsx picks the current proposed/active one (if
  // any) to replace the narrative worthTesting() fallback, and the most
  // recent completed/stopped one with a `result` to populate "What
  // Changed". An empty array is the honest default (V3 Rule F — don't
  // fabricate structure where there isn't any) and worthTesting() keeps
  // running exactly as before in that case.
  experiments: CapacityExperiment[];
}

/** V3 doc §15 "Personal Experiment Engine" / §19 "System Learning Upgrade"
 *  — mirrors capacity_experiments (migration 0159). Written only by the
 *  Capacity Bot's /experiment command (this route has no POST/PATCH — see
 *  route.ts's header comment, all writes go through the bot); the
 *  workbench reads it read-only. 'stopped' is kept distinct from
 *  'completed' — §15: an experiment must "be stoppable if worse", and that
 *  is a different, equally legitimate outcome from one that ran its full
 *  trial window. */
export type ExperimentStatus = 'proposed' | 'active' | 'completed' | 'stopped';
export type ExperimentConfidence = 'low' | 'moderate' | 'high';

export interface CapacityExperiment {
  id: number;
  hypothesis: string;
  target_condition: string | null;
  proposed_change: string;
  /** Free text, not a date range (V3 §15 example: "4 of 5 office
   *  afternoons reached Stretched or Depleted"). */
  baseline_window: string | null;
  /** Free text (e.g. "two weeks"). See migration 0159's comment — a small
   *  set of presets drive reminder scheduling in the bot, but this field
   *  itself is never parsed as a structured duration. */
  trial_window: string | null;
  outcome_measures: string[];
  status: ExperimentStatus;
  /** Non-null once status is 'completed' or 'stopped' — the §19 "WHAT
   *  CHANGED" layer's source. Deliberately free text/personal-language,
   *  never a supported/not-supported flag (§15: must not masquerade as a
   *  medical/diagnostic conclusion). */
  result: string | null;
  confidence: ExperimentConfidence | null;
  notes: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export const EXPERIMENT_STATUS_LABEL: Record<ExperimentStatus, string> = {
  proposed: 'Worth testing',
  active: 'In progress',
  completed: 'Completed',
  stopped: 'Stopped',
};

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
  /** General (non-personal) evidence metadata from capacity_interventions,
   *  V3 doc §16 "Evidence Metadata" — migration 0157. Deliberately kept
   *  separate from the personal attempts/better/same/worse fields above:
   *  §16 requires personal and general evidence to never be blended into
   *  one confidence number. 'unknown' means nobody has reviewed this
   *  intervention's evidence yet, not that it was checked and found
   *  lacking — the UI should treat 'unknown' as "nothing to show", not
   *  render it as a badge. */
  evidence_strength: 'established_guideline_aligned' | 'moderate' | 'emerging' | 'lived_experience_informed' | 'personal_only' | 'unknown';
  /** Free-text summary of what the general evidence says (spec §16). Null
   *  for the 30 originally-seeded interventions until a human curates it
   *  — never fabricated. */
  evidence_basis: string | null;
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

// ── V3 Mission 3 — Sensory + Regulation Profile ─────────────────────────────
// (TJR_Human_Systems_Workbench_V3_Mission_and_Change_Proposal.md §10
// "Sensory Regulation Upgrade" + §11 "Natural Regulation Response").
// Deep-check-tier, additive on top of the unchanged coarse
// stimulation_state summary — mirrors capacity_checkins.sensory_channels /
// natural_regulation_response / suppressed_regulation_response (migration
// 0158).

/** V3 doc §10 — the 8 potential sensory channels a deep check can flag
 *  ("most check-ins will only flag 1-2 channels, not all 8" — migration
 *  0158's comment). Keys match the jsonb keys
 *  telegram-bots/capacitybot/capacity_today.py's SENSORY_CHANNEL_KEYS
 *  writes. */
export type SensoryChannelKey =
  | 'auditory' | 'visual' | 'touch' | 'smell' | 'movement' | 'pressure'
  | 'temperature' | 'environmental_complexity';

/** V3 doc §10's per-channel response vocabulary. */
export type SensoryChannelResponse =
  | 'reduce_avoid' | 'neutral' | 'seek_helpful' | 'context_dependent' | 'unknown';

/** capacity_checkins.sensory_channels (migration 0158) — sparse by design;
 *  only channels the Captain actually flagged appear as keys. Never
 *  backfilled with a default for an unflagged channel (V3 doc's "do not
 *  fabricate" discipline applies to display, not just missing values). */
export type SensoryChannelBreakdown = Partial<Record<SensoryChannelKey, SensoryChannelResponse>>;

export const SENSORY_CHANNEL_LABEL: Record<SensoryChannelKey, string> = {
  auditory: 'Auditory', visual: 'Visual', touch: 'Touch', smell: 'Smell',
  movement: 'Movement', pressure: 'Pressure', temperature: 'Temperature',
  environmental_complexity: 'Environmental complexity',
};

export const SENSORY_RESPONSE_LABEL: Record<SensoryChannelResponse, string> = {
  reduce_avoid: 'Reduce / avoid', neutral: 'Neutral', seek_helpful: 'Seek / helpful',
  context_dependent: 'Context dependent', unknown: 'Unknown',
};

/** Sensory response → Badge status. Deliberately non-pathologising: a
 *  channel someone reduces/avoids is not shown as "bad" and one they seek
 *  out is not shown as automatically "good" — reduce_avoid/context_
 *  dependent read as a mild flag worth noting, seek_helpful reads as a
 *  positive signal, neutral/unknown as plain info (V3 doc §3.6 — sensory
 *  responses are not symptoms to correct). */
export function sensoryResponseStatus(r: SensoryChannelResponse): BadgeStatus {
  switch (r) {
    case 'seek_helpful': return 'success';
    case 'neutral': return 'info';
    case 'reduce_avoid': return 'warning';
    case 'context_dependent': return 'warning';
    default: return 'neutral'; // unknown
  }
}

/** V3 doc §11 "Natural Regulation Response" — "what does my system seem to
 *  want right now?". capacity_checkins.natural_regulation_response
 *  (migration 0158). */
export type NaturalRegulationResponse =
  | 'less_input' | 'more_input' | 'move' | 'fidget_repeat' | 'quiet' | 'stop_talking'
  | 'be_alone' | 'connect_with_someone_safe' | 'something_familiar' | 'something_interesting'
  | 'pressure_sensory_comfort' | 'get_thoughts_out' | 'rest' | 'dont_know';

export const NATURAL_REGULATION_LABEL: Record<NaturalRegulationResponse, string> = {
  less_input: 'Less input', more_input: 'More input', move: 'Move', fidget_repeat: 'Fidget / repeat',
  quiet: 'Quiet', stop_talking: 'Stop talking', be_alone: 'Be alone',
  connect_with_someone_safe: 'Connect with someone safe', something_familiar: 'Something familiar',
  something_interesting: 'Something interesting', pressure_sensory_comfort: 'Pressure / sensory comfort',
  get_thoughts_out: 'Get thoughts out', rest: 'Rest', dont_know: "Doesn't know",
};

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

  // ── V3 Mission 3 — Sensory + Regulation Profile (§10/§11) ───────────────
  /** V3 doc §10 — the coarse stimulation_state summary paired with an
   *  optional deeper per-channel breakdown, so the UI can say something
   *  like "Overall stimulation is balanced, but auditory load is high"
   *  (the worked example in §10 itself) instead of collapsing all sensory
   *  experience into one value. `channels` is read from the most recent
   *  check-in that has ANY channel flagged, not restricted to today — same
   *  deep-check-tier latest-non-null fallback user_burnout_framing already
   *  uses elsewhere in this workbench, since this is an optional,
   *  occasionally-answered layer (spec §24). */
  sensory_profile: {
    stimulation_state: string | null;
    channels: SensoryChannelBreakdown | null;
  };
  /** V3 doc §11 — "what does my system seem to want right now?" plus the
   *  optional suppressed-response flag ("Am I stopping myself from doing
   *  something that may help because it feels inappropriate, inconvenient
   *  or noticeable?"). Feeds compensation-cost learning per the doc — never
   *  render `suppressed` as something to correct. Same latest-non-null
   *  fallback as sensory_profile.channels above. */
  natural_regulation: {
    response: NaturalRegulationResponse | null;
    suppressed: boolean | null;
  };
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

import { toneToStatus, type BadgeStatus } from '@/components/ui';
import { capacityStateToTone } from '@/lib/departments';

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

/** System Trajectory → Badge status. Deliberately its own scale, not
 *  reused from systemPostureStatus() — a trajectory read must never
 *  visually read as identical to a NOW posture (V3 doc §2). */
export function systemTrajectoryStatus(t: SystemTrajectory): BadgeStatus {
  switch (t) {
    case 'stable': return 'success';
    case 'recovery_signals_emerging': return 'info';
    case 'rebuilding': return 'info';
    case 'accumulating_strain': return 'warning';
    case 'sustained_high_strain': return 'warning';
    case 'burnout_like_depletion': return 'error';
    default: return 'neutral'; // insufficient_data
  }
}

/** V3 doc §5/§14 plain-language labels — never a percentage, never a
 *  diagnostic claim (spec §27 language standard). */
export const SYSTEM_TRAJECTORY_LABEL: Record<SystemTrajectory, string> = {
  insufficient_data: 'Not enough data yet',
  stable: 'Stable',
  accumulating_strain: 'Accumulating strain',
  sustained_high_strain: 'Sustained high strain',
  burnout_like_depletion: 'Burnout-like depletion',
  recovery_signals_emerging: 'Recovery signals emerging',
  rebuilding: 'Rebuilding',
};

export const STRATEGIC_POSTURE_LABEL: Record<StrategicPosture, string> = {
  engage: 'ENGAGE', steady: 'STEADY', protect: 'PROTECT', recover: 'RECOVER',
  stabilise: 'STABILISE', re_engage: 'RE-ENGAGE', rebuild: 'REBUILD', redesign: 'REDESIGN',
};

/** Strategic Posture → Badge status. Mirrors systemPostureStatus()'s
 *  colour intent for the shared engage/steady/protect/recover vocabulary;
 *  the additional burnout-stage postures read progressively more settled
 *  (stabilise/re_engage warning, rebuild info) without ever reaching the
 *  unqualified 'success' engage carries — a rebuild/re-engage state is
 *  still a recovery-in-progress state, not a clean bill of health. */
export function strategicPostureStatus(p: StrategicPosture): BadgeStatus {
  switch (p) {
    case 'engage': return 'success';
    case 'steady': return 'info';
    case 'rebuild': return 'info';
    case 're_engage': return 'warning';
    case 'stabilise': return 'warning';
    case 'protect': return 'warning';
    case 'recover': return 'error';
    case 'redesign': return 'neutral';
    default: return 'neutral';
  }
}

export const RECOVERY_STAGE_LABEL: Record<RecoveryStage, string> = {
  protect: 'Protect', stabilise: 'Stabilise', recover: 'Recover',
  re_engage: 'Re-engage', rebuild: 'Rebuild', redesign: 'Redesign',
};

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
 *  not the older RPC-derived capacity_band. 2026-08-29: delegates to the
 *  shared capacityStateToTone adapter (departments.ts) instead of its own
 *  copy of the same mapping — this function's external contract (still
 *  the canonical call site for this) is unchanged. */
export function capacityStateStatus(state: string | null): BadgeStatus {
  return toneToStatus(capacityStateToTone(state));
}

export const CAPACITY_STATE_LABEL: Record<string, string> = {
  green: '🟢 Sustainable', orange: '🟠 Stretched', red: '🔴 Depleted',
};

// Trends page label constants (2026-08-27) — real vocabularies from
// capacity_checkins' own CHECK constraints (migrations 0148/0152), not
// invented. Used by /human-systems-workbench/trends alongside each
// field's ordinal map for its sparkline.
export const STIMULATION_STATE_TREND_LABEL: Record<string, string> = {
  low: 'Not enough', balanced: 'Balanced', high: 'Too much',
};
export const PAIN_STATE_LABEL: Record<string, string> = {
  low: 'Low', baseline: 'Baseline', elevated: 'Elevated', high: 'High',
};
export const REGULATION_STATE_LABEL: Record<string, string> = {
  settled: 'Settled', manageable: 'Manageable', activated: 'Activated', overloaded: 'Overloaded',
};
export const EXECUTIVE_FUNCTION_LABEL: Record<string, string> = {
  good: 'Good', strained: 'Strained', difficult: 'Difficult', very_difficult: 'Very difficult',
};
export const COMPENSATION_LOAD_LABEL: Record<string, string> = {
  low: 'Low', moderate: 'Moderate', high: 'High', extreme: 'Extreme',
};
export const EMOTIONAL_STATE_LABEL: Record<string, string> = {
  light: 'Light', moderate: 'Moderate', heavy: 'Heavy', overwhelming: 'Overwhelming',
};
export const SOCIAL_STATE_LABEL: Record<string, string> = {
  plenty: 'Plenty', some: 'Some', limited: 'Limited', none: 'None',
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
