// Captain's Chair synthesis (MSN-0364, revised for the Captain's Chair +
// LifeOS Command Experience redesign) — pure functions, no React/fetch.
// Turns the same signals the old 5-badge situation strip rendered
// independently into one interpreted Command Status, per the brief's core
// principle: "the workbenches produce information, Captain's Chair
// produces meaning." Template-based by design (Captain-locked decision,
// mission doc §10) — must render instantly with zero network dependency,
// unlike Captain's Brief's LLM synthesis.
//
// P0 correctness repair: this module used to take a RecoveryPostureBand/
// CapacityBand pair sourced from useROSData() (the retired get_recovery_
// posture() RPC, `?? mockPosture` fallback). That let a day with literally
// no capacity check-in render a fabricated STABLE/MODERATE sentence with
// full confidence. It now takes the canonical Human Systems assessed
// context (SystemPostureBand + has_checkin_today), the same object Ready
// Room and Weekly Review already consume — see
// src/app/api/human-systems/assessed-context.ts. deriveSystemPosture(null)
// already returns UNKNOWN with an honest message, so "no check-in today"
// propagates as UNKNOWN here rather than needing a second mock-detection
// path.

import type { SystemPostureBand } from '@/app/human-systems-workbench/_components/types';

/** Mirrors assessed-context.ts's `available_capacity` field. */
export type AvailableCapacity = 'green' | 'orange' | 'red' | 'unknown';

export interface CommandStatusInputs {
  /** Canonical NOW posture (assessed-context.ts). Already UNKNOWN when
   *  hasCheckinToday is false — never fed a mock value. */
  posture: SystemPostureBand;
  /** assessed-context.ts's posture_message — real, deriveSystemPosture()
   *  output, safe to surface verbatim. */
  postureMessage: string;
  availableCapacity: AvailableCapacity;
  hasCheckinToday: boolean;
  /** True only when the /api/human-systems/context fetch itself failed —
   *  distinct from a successful response reporting hasCheckinToday: false. */
  humanSystemsUnavailable: boolean;
  operationalRisk: 'GREEN' | 'AMBER' | 'RED' | null;
  operationalRiskUnknown: boolean;
  escalateCount: number;
  /** null = genuinely unknown (source fetch failed), not zero. */
  interruptNow: number | null;
  emergencyCount: number;
  emergencyWorstTier: 'emergency_warning' | 'watch_and_act' | null;
  systemsFailedCount: number;
  systemsUnknown: boolean;
}

export interface CommandStatusResult {
  posture: SystemPostureBand;
  /** One-line interpretation — the sentence the whole redesign hinges on. */
  interpretation: string;
  /** Distinct personal/environment/command lines, brief §6. */
  personalLine: string;
  environmentLine: string;
  postureLine: string;
  /** True when something needs urgent attention regardless of posture —
   *  Needs You should never be empty when this is true. */
  hasUrgentException: boolean;
}

const POSTURE_LABEL: Record<SystemPostureBand, string> = {
  ENGAGE: 'Engage',
  STEADY: 'Steady',
  PROTECT: 'Protect',
  RECOVER: 'Recover',
  RESET: 'Reset',
  UNKNOWN: 'Unknown',
};

function personalConcern(posture: SystemPostureBand, availableCapacity: AvailableCapacity): boolean {
  return (
    posture === 'PROTECT' ||
    posture === 'RECOVER' ||
    posture === 'RESET' ||
    availableCapacity === 'orange' ||
    availableCapacity === 'red'
  );
}

function environmentConcern(inputs: CommandStatusInputs): boolean {
  return (
    inputs.operationalRisk === 'RED' ||
    inputs.escalateCount > 0 ||
    inputs.emergencyWorstTier === 'emergency_warning' ||
    (inputs.interruptNow ?? 0) > 0 ||
    inputs.systemsFailedCount > 0
  );
}

function personalLineFor(inputs: CommandStatusInputs): string {
  if (inputs.humanSystemsUnavailable) return 'Human Systems is unavailable — treat capacity as unknown, not clear.';
  if (!inputs.hasCheckinToday) return `No check-in today — ${inputs.postureMessage}`;
  const label = POSTURE_LABEL[inputs.posture].toLowerCase();
  if (inputs.posture === 'RECOVER') return `Capacity is depleted — recovery posture is ${label}.`;
  if (inputs.posture === 'RESET') return `The system needs a regulation step — recovery posture is ${label}.`;
  if (inputs.posture === 'PROTECT') return `Capacity is stretched — recovery posture is ${label}.`;
  return `Capacity is available — recovery posture is ${label}.`;
}

function environmentLineFor(inputs: CommandStatusInputs): string {
  const parts: string[] = [];
  if (inputs.emergencyWorstTier === 'emergency_warning') parts.push(`${inputs.emergencyCount} active emergency alert${inputs.emergencyCount === 1 ? '' : 's'}`);
  else if (inputs.emergencyWorstTier === 'watch_and_act') parts.push(`${inputs.emergencyCount} alert${inputs.emergencyCount === 1 ? '' : 's'} under watch`);
  if (inputs.operationalRisk === 'RED') parts.push('operational risk RED');
  else if (inputs.escalateCount > 0) parts.push(`${inputs.escalateCount} threat${inputs.escalateCount === 1 ? '' : 's'} at escalate`);
  if ((inputs.interruptNow ?? 0) > 0) parts.push(`${inputs.interruptNow} item${inputs.interruptNow === 1 ? '' : 's'} flagged to interrupt now`);
  if (inputs.systemsFailedCount > 0) parts.push(`${inputs.systemsFailedCount} system${inputs.systemsFailedCount === 1 ? '' : 's'} failing`);

  if (parts.length === 0) {
    return inputs.systemsUnknown || inputs.operationalRiskUnknown
      ? 'Mostly stable — some sources unavailable, see Situation for detail.'
      : 'Stable — no emergency alerts, no elevated risk, systems nominal.';
  }
  return `Not clear: ${parts.join('; ')}.`;
}

/** The one sentence the redesign hinges on. Deterministic 2x2 matrix over
 * personal/environment concern, per brief §6's worked example. */
function interpretationFor(hasPersonal: boolean, hasEnvironment: boolean, posture: SystemPostureBand): string {
  const postureLabel = POSTURE_LABEL[posture];
  if (!hasPersonal && !hasEnvironment) {
    return 'Capacity and the external environment are both stable — nothing currently requires intervention.';
  }
  if (!hasPersonal && hasEnvironment) {
    return 'Capacity is fine, but something in the environment needs attention — see Needs You.';
  }
  if (hasPersonal && !hasEnvironment) {
    return `Capacity is constrained, but the external environment is stable. Protect ${posture === 'RECOVER' ? 'recovery' : 'capacity'}; nothing currently warrants overriding ${postureLabel}.`;
  }
  return `Capacity is constrained AND something external needs attention — this may warrant overriding ${postureLabel} posture. See Needs You.`;
}

export function deriveCommandStatus(inputs: CommandStatusInputs): CommandStatusResult {
  const posture: SystemPostureBand = inputs.humanSystemsUnavailable ? 'UNKNOWN' : inputs.posture;
  const hasEnvironment = environmentConcern(inputs);
  // A stale/absent check-in never contributes a personal concern signal —
  // "unknown" must not silently read as "fine" OR as "constrained." It
  // shows up honestly in the interpretation branch below instead.
  const hasPersonal = !inputs.humanSystemsUnavailable && inputs.hasCheckinToday && personalConcern(posture, inputs.availableCapacity);

  let interpretation: string;
  if (inputs.humanSystemsUnavailable) {
    interpretation = 'Human Systems is unavailable — check connection. Treat capacity as unknown, not clear.';
  } else if (!inputs.hasCheckinToday) {
    interpretation = hasEnvironment
      ? 'No check-in today, so capacity is unknown — something in the environment needs attention. See Needs You.'
      : 'No check-in today, so capacity is unknown. The external environment is stable.';
  } else {
    interpretation = interpretationFor(hasPersonal, hasEnvironment, posture);
  }

  return {
    posture,
    interpretation,
    personalLine: personalLineFor(inputs),
    environmentLine: environmentLineFor(inputs),
    postureLine: inputs.humanSystemsUnavailable
      ? 'Unknown — data error'
      : !inputs.hasCheckinToday
        ? 'Unknown — no check-in today'
        : POSTURE_LABEL[posture],
    hasUrgentException: inputs.emergencyWorstTier === 'emergency_warning' || (inputs.interruptNow ?? 0) > 0,
  };
}

// ── Needs You priority ordering ─────────────────────────────────────────────
// Brief §7: "urgency and severity should not be treated as the same thing."
// Lower number = higher priority, rendered first.

export type NeedsYouKind = 'safety' | 'time_critical' | 'blocker' | 'approval' | 'review' | 'triage';

const KIND_PRIORITY: Record<NeedsYouKind, number> = {
  safety: 0,
  time_critical: 1,
  blocker: 2,
  approval: 3,
  review: 4,
  triage: 5,
};

export interface NeedsYouItem {
  id: string;
  kind: NeedsYouKind;
  title: string;
  detail: string;
  href: string;
  actionLabel: string;
}

export function sortNeedsYou(items: NeedsYouItem[]): NeedsYouItem[] {
  return [...items].sort((a, b) => KIND_PRIORITY[a.kind] - KIND_PRIORITY[b.kind]);
}
