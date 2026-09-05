// Captain's Chair synthesis (MSN-0364) — pure functions, no React/fetch.
// Turns the same signals the old 5-badge situation strip rendered
// independently into one interpreted Command Status, per the brief's core
// principle: "the workbenches produce information, Captain's Chair
// produces meaning." Template-based by design (Captain-locked decision,
// mission doc §10) — must render instantly with zero network dependency,
// unlike Captain's Brief's LLM synthesis.
//
// Deliberately does not read useROSData().guidance (mockData's
// mockGuidance array) — that field stays hardcoded pending its own
// "Phase 2: replace with health_insights fetch" (see useROSData.ts).
// posture.posture_message/mission_guidance ARE real (from the
// get_recovery_posture() RPC) and safe to surface.

import type { CapacityBand, RecoveryPostureBand } from './types';

export interface CommandStatusInputs {
  postureBand: RecoveryPostureBand;
  postureFetchFailed: boolean;
  capacityBand: CapacityBand;
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
  posture: RecoveryPostureBand;
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

const POSTURE_LABEL: Record<RecoveryPostureBand, string> = {
  STRONG: 'Strong',
  STABLE: 'Stable',
  FRAGILE: 'Fragile',
  REST: 'Rest',
  UNKNOWN: 'Unknown',
};

function personalConcern(postureBand: RecoveryPostureBand, capacityBand: CapacityBand): boolean {
  return postureBand === 'REST' || postureBand === 'FRAGILE' || capacityBand === 'LIMITED' || capacityBand === 'REST';
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

function personalLineFor(postureBand: RecoveryPostureBand, capacityBand: CapacityBand): string {
  if (postureBand === 'REST') return `Capacity is constrained (${capacityBand.toLowerCase()}) — recovery posture is REST.`;
  if (postureBand === 'FRAGILE') return `Capacity is stretched (${capacityBand.toLowerCase()}) — recovery posture is FRAGILE.`;
  if (postureBand === 'STABLE' || postureBand === 'STRONG') return `Capacity is ${capacityBand.toLowerCase()} — recovery posture is ${POSTURE_LABEL[postureBand].toLowerCase()}.`;
  return 'Recovery posture is unknown — no check-in data available.';
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
function interpretationFor(hasPersonal: boolean, hasEnvironment: boolean, postureBand: RecoveryPostureBand): string {
  const postureLabel = POSTURE_LABEL[postureBand];
  if (!hasPersonal && !hasEnvironment) {
    return 'Capacity and the external environment are both stable — nothing currently requires intervention.';
  }
  if (!hasPersonal && hasEnvironment) {
    return 'Capacity is fine, but something in the environment needs attention — see Needs You.';
  }
  if (hasPersonal && !hasEnvironment) {
    return `Capacity is constrained, but the external environment is stable. Protect ${postureLabel === 'Rest' ? 'recovery' : 'capacity'}; nothing currently warrants overriding ${postureLabel}.`;
  }
  return `Capacity is constrained AND something external needs attention — this may warrant overriding ${postureLabel} posture. See Needs You.`;
}

export function deriveCommandStatus(inputs: CommandStatusInputs): CommandStatusResult {
  const hasPersonal = personalConcern(inputs.postureBand, inputs.capacityBand);
  const hasEnvironment = environmentConcern(inputs);

  return {
    posture: inputs.postureFetchFailed ? 'UNKNOWN' : inputs.postureBand,
    interpretation: inputs.postureFetchFailed
      ? 'Recovery data is unavailable — check connection. Treat posture as unknown, not clear.'
      : interpretationFor(hasPersonal, hasEnvironment, inputs.postureBand),
    personalLine: inputs.postureFetchFailed ? 'Recovery posture data unavailable.' : personalLineFor(inputs.postureBand, inputs.capacityBand),
    environmentLine: environmentLineFor(inputs),
    postureLine: inputs.postureFetchFailed ? 'Unknown — data error' : POSTURE_LABEL[inputs.postureBand],
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
