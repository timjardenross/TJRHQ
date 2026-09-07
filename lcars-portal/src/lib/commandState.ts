// Command State (Captain's Chair + LifeOS Command Experience, Phase 2) —
// pure functions, no React/fetch. This is the shared composition layer the
// mission brief calls for: Captain's Chair and LifeOS must consume the same
// interpreted "what kind of day is this" / "what needs you" / "what's the
// intelligence headline" outputs rather than each re-deriving their own.
//
// Domain owners keep domain truth — this module composes already-assessed
// signals (Human Systems' canonical posture, the canonical HQ Status
// summary, Emergency Alert Hub's worst tier, the Brief's own stats) into
// one command-level read. It does not re-interpret any domain's own data
// (e.g. it never queries capacity_checkins or job telemetry itself).
//
// Do not add a new posture taxonomy without checking existing vocabulary
// first (mission §6) — CommandPosture deliberately reuses Human Systems'
// PROTECT/RECOVER labels where the meaning already lines up (mission §17
// explicitly treats identical wording across both surfaces as the *goal*,
// not a collision to avoid), and only introduces FOCUS/RESPOND/STEADY for
// the states Human Systems' own vocabulary has no equivalent for (a
// command-level "nothing needs overriding, but something outside capacity
// deserves attention" state, and a genuinely calm baseline day).

import type { SystemPostureBand } from '@/app/human-systems-workbench/_components/types';
import type { NeedsYouItem } from './captainsChairSynthesis';

// ── "What kind of day is this?" — command posture ───────────────────────────

export type CommandPosture = 'RESPOND' | 'RECOVER' | 'PROTECT' | 'FOCUS' | 'STEADY' | 'UNKNOWN';

export interface CommandPostureInputs {
  /** From CommandStatusResult.hasEnvironmentConcern — already folds in
   *  operational risk, escalations, emergency, interrupt-now, and HQ
   *  Status ATTENTION. Not re-derived here. */
  hasEnvironmentConcern: boolean;
  /** A genuine, curated Needs You count (buildNeedsYouItems().length) — a
   *  command posture must never read RESPOND off of raw backlog counts. */
  needsYouCount: number;
  humanSystemsUnavailable: boolean;
  hasCheckinToday: boolean;
  humanSystemsPosture: SystemPostureBand;
  /** Count of genuinely meaningful commitments today (e.g. Calendar events
   *  when status is 'ok') — 0 when disconnected/errored/empty. */
  meaningfulCommitmentsToday: number;
}

export interface CommandPostureResult {
  posture: CommandPosture;
  /** Short one-line headline, e.g. "PROTECT TODAY". */
  headline: string;
  /** One-sentence explanation, safe to read aloud verbatim. */
  explanation: string;
}

const POSTURE_HEADLINE: Record<CommandPosture, string> = {
  RESPOND: 'RESPOND',
  RECOVER: 'RECOVER',
  PROTECT: 'PROTECT',
  FOCUS: 'FOCUS',
  STEADY: 'STEADY',
  UNKNOWN: 'UNKNOWN',
};

export function deriveCommandPosture(inputs: CommandPostureInputs): CommandPostureResult {
  // A material external condition or a genuine human-attention item always
  // takes priority — mission scenario D: "Emergency overrides calm
  // presentation; no hiding behind recovery posture."
  if (inputs.hasEnvironmentConcern || inputs.needsYouCount > 0) {
    return {
      posture: 'RESPOND',
      headline: POSTURE_HEADLINE.RESPOND,
      explanation: inputs.needsYouCount > 0
        ? `${inputs.needsYouCount} thing${inputs.needsYouCount === 1 ? '' : 's'} genuinely need${inputs.needsYouCount === 1 ? 's' : ''} you today.`
        : 'A material external condition needs priority today.',
    };
  }

  if (inputs.humanSystemsUnavailable) {
    return { posture: 'UNKNOWN', headline: POSTURE_HEADLINE.UNKNOWN, explanation: 'Human Systems is unavailable — today is unknown, not clear.' };
  }
  if (!inputs.hasCheckinToday) {
    return { posture: 'UNKNOWN', headline: POSTURE_HEADLINE.UNKNOWN, explanation: 'No capacity check-in yet today — today is unknown, not clear.' };
  }

  if (inputs.humanSystemsPosture === 'RECOVER') {
    return { posture: 'RECOVER', headline: POSTURE_HEADLINE.RECOVER, explanation: 'Recovery conditions should dominate discretionary demand today. Nothing external overrides that.' };
  }
  if (inputs.humanSystemsPosture === 'PROTECT' || inputs.humanSystemsPosture === 'RESET') {
    return { posture: 'PROTECT', headline: POSTURE_HEADLINE.PROTECT, explanation: 'Capacity is constrained; nothing external warrants overriding recovery.' };
  }

  if (inputs.meaningfulCommitmentsToday > 0) {
    return {
      posture: 'FOCUS',
      headline: POSTURE_HEADLINE.FOCUS,
      explanation: `Capacity is workable. ${inputs.meaningfulCommitmentsToday} commitment${inputs.meaningfulCommitmentsToday === 1 ? '' : 's'} today deserve${inputs.meaningfulCommitmentsToday === 1 ? 's' : ''} protected attention.`,
    };
  }

  return { posture: 'STEADY', headline: POSTURE_HEADLINE.STEADY, explanation: 'Capacity is workable and nothing external needs priority — a normal operating day.' };
}

// ── Needs You — one curated human-attention list ────────────────────────────
//
// Moved out of captains-chair-workbench/page.tsx (Phase 2) so LifeOS can
// render the identical list rather than re-deriving its own — mission
// requirement: "no duplicate Needs You logic exists between Captain and
// LifeOS." Every source here is something genuinely awaiting a TJR
// decision, never a raw backlog/queue count (mission §7).

export interface NeedsYouBuildInputs {
  emergency: { worstTier: 'emergency_warning' | 'watch_and_act' | null; count: number; worstHeadline: string | null } | null;
  briefingError: boolean;
  interruptNow: number | null;
  contentAwaitingPublish: number | null;
  oldestContentAwaitingPublish: string | null;
  wellnessRiskFlags: number | null;
  notebookReadyCount: number | null;
  capturePending: number | null;
  oldestCapturePending: string | null;
  evolutionPendingCount: number | null;
  evolutionHighestValueTitle: string | null;
  /** Genuine HQ intervention required (mission scenario F) — only ATTENTION
   *  posture reaches here; DEGRADED never generates a Needs You item. */
  hqPosture: 'NORMAL' | 'DEGRADED' | 'ATTENTION' | 'UNKNOWN' | null;
  hqAttentionItems: Array<{ title: string; detail: string }>;
  criticalAlerts: Array<{ id: string; title: string; detail: string; href: string }>;
}

export function buildNeedsYouItems(inputs: NeedsYouBuildInputs): NeedsYouItem[] {
  const items: NeedsYouItem[] = [];

  if (inputs.emergency?.worstTier === 'emergency_warning') {
    items.push({
      id: 'emergency', kind: 'safety',
      title: inputs.emergency.worstHeadline ?? 'Active emergency warning',
      detail: `${inputs.emergency.count} active alert${inputs.emergency.count === 1 ? '' : 's'} at emergency tier.`,
      href: '/emergency-alert-hub-workbench', actionLabel: 'Review',
    });
  }

  if (!inputs.briefingError && (inputs.interruptNow ?? 0) > 0) {
    items.push({
      id: 'interrupt', kind: 'time_critical',
      title: `${inputs.interruptNow} item${inputs.interruptNow === 1 ? '' : 's'} flagged to interrupt now`,
      detail: 'The Attention Engine flagged this as needing you right now.',
      href: '/captains-brief-workbench', actionLabel: 'Review',
    });
  }

  if (inputs.hqPosture === 'ATTENTION') {
    const first = inputs.hqAttentionItems[0];
    items.push({
      id: 'hq-status', kind: 'blocker',
      title: first?.title ?? 'HQ needs your attention',
      detail: first?.detail ?? 'A critical HQ capability is unavailable.',
      href: '/agent-status-workbench', actionLabel: 'Review',
    });
  }

  if ((inputs.contentAwaitingPublish ?? 0) > 0) {
    items.push({
      id: 'content-publish', kind: 'approval',
      title: inputs.oldestContentAwaitingPublish ?? 'Content ready to publish',
      detail: `${inputs.contentAwaitingPublish} item${inputs.contentAwaitingPublish === 1 ? '' : 's'} QA'd and ready for your publish decision.`,
      href: '/content-workbench', actionLabel: 'Publish / Schedule',
    });
  }

  if ((inputs.wellnessRiskFlags ?? 0) > 0) {
    items.push({
      id: 'wellness', kind: 'review',
      title: 'Nervous-system load remains elevated',
      detail: `${inputs.wellnessRiskFlags} wellness risk flag${inputs.wellnessRiskFlags === 1 ? '' : 's'} raised.`,
      href: '/human-systems-workbench', actionLabel: 'Review',
    });
  }

  if (inputs.notebookReadyCount !== null && inputs.notebookReadyCount > 0) {
    items.push({
      id: 'notebook', kind: 'review',
      title: `${inputs.notebookReadyCount} note${inputs.notebookReadyCount === 1 ? '' : 's'} ready for routing`,
      detail: 'Captured in the Log, reviewed, waiting on your routing decision.',
      href: '/captains-chair-workbench/notebook', actionLabel: 'Review',
    });
  }

  if ((inputs.capturePending ?? 0) > 0) {
    items.push({
      id: 'capture-triage', kind: 'triage',
      title: inputs.oldestCapturePending ?? 'Captures waiting on triage',
      detail: `${inputs.capturePending} item${inputs.capturePending === 1 ? '' : 's'} waiting.`,
      href: '/capture-workbench', actionLabel: 'Review',
    });
  }

  if ((inputs.evolutionPendingCount ?? 0) > 0) {
    items.push({
      id: 'hq-evolution', kind: 'review',
      title: inputs.evolutionHighestValueTitle ?? 'HQ Evolution has opportunities worth considering',
      detail: `${inputs.evolutionPendingCount} opportunit${inputs.evolutionPendingCount === 1 ? 'y' : 'ies'} from overnight research ${inputs.evolutionPendingCount === 1 ? 'needs' : 'need'} your decision.`,
      href: '/self-improvement-findings', actionLabel: 'Review',
    });
  }

  for (const alert of inputs.criticalAlerts.slice(0, 2)) {
    items.push({
      id: `alert-${alert.id}`, kind: 'time_critical',
      title: alert.title, detail: alert.detail, href: alert.href, actionLabel: 'Review',
    });
  }

  return items;
}

// ── Intelligence headline — one canonical Brief-derived line ────────────────
//
// Captain's Chair and LifeOS must not independently curate a Top OSINT
// Signal / Top Health Signal / Operational Risk headline (mission §9.3).
// This composes only already-assessed signals (Brief stats, Emergency,
// Operational Risk) into the one line both surfaces show — full detail
// stays behind "Open briefing →".

export interface IntelligenceHeadlineInputs {
  briefingError: boolean;
  briefingWarningsCount: number;
  operationalRisk: 'GREEN' | 'AMBER' | 'RED' | null;
  operationalRiskUnknown: boolean;
  emergencyWorstTier: 'emergency_warning' | 'watch_and_act' | null;
  emergencyHeadline: string | null;
}

export interface IntelligenceHeadlineResult {
  headline: string;
  detail: string;
  /** True when this is a degraded/unknown read, never "confirmed no
   *  material change" (mission §14: "unavailable coverage ≠ no material
   *  change"). */
  unknown: boolean;
}

export function deriveIntelligenceHeadline(inputs: IntelligenceHeadlineInputs): IntelligenceHeadlineResult {
  // Confirmed material conditions from independently-reliable sources
  // (Emergency Alert Hub, Operational Risk) take priority even when Brief
  // itself is unavailable — a real, confirmed emergency must never be
  // suppressed behind a generic "intelligence unavailable" notice just
  // because a different source is also down.
  if (inputs.emergencyWorstTier === 'emergency_warning' || inputs.operationalRisk === 'RED') {
    return {
      headline: 'ELEVATED EXTERNAL CONDITIONS',
      detail: inputs.emergencyHeadline ?? 'A material external condition may affect today\'s plan.',
      unknown: false,
    };
  }

  // Acceptance-audit repair: this used to require BOTH briefingError AND
  // operationalRiskUnknown (AND) before reporting unavailable — so a
  // failed Brief fetch with a merely-successful (non-RED) risk read, or an
  // unknown risk read with a successful-but-quiet Brief, fell through to
  // "NO MATERIAL CHANGE." Either source alone being unavailable is enough
  // to make "no material change" a false claim — mission §14: "unavailable
  // coverage ≠ no material change."
  if (inputs.briefingError || inputs.operationalRiskUnknown) {
    return {
      headline: 'INTELLIGENCE UNAVAILABLE',
      detail: inputs.briefingError
        ? 'Brief coverage is unavailable right now — this is not confirmation that nothing has changed.'
        : 'Operational risk assessment is unavailable right now — this is not confirmation that nothing has changed.',
      unknown: true,
    };
  }

  if (inputs.emergencyWorstTier === 'watch_and_act' || inputs.briefingWarningsCount > 0) {
    const count = inputs.emergencyWorstTier === 'watch_and_act' ? 1 : inputs.briefingWarningsCount;
    return {
      headline: `${count} ITEM${count === 1 ? '' : 'S'} ON WATCH`,
      detail: 'No active emergency conditions affect today\'s plan.',
      unknown: false,
    };
  }

  return { headline: 'NO MATERIAL CHANGE', detail: 'Nothing new since the last briefing.', unknown: false };
}
