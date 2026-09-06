// HQ Status interpreter — the "HQ HEALTH INTERPRETER" layer described in
// the HQ Status mission (spec §29-§31): turns raw job-level telemetry
// (domain_heartbeats via lib/agentStatusJobs.ts, plus optional source/
// pipeline signals) into one honest HQ-level posture and a small set of
// capability verdicts, so the workbench answers "is HQ working properly,
// and does anything actually need me?" instead of listing every job row.
//
// Deliberately pure and framework-free (no Supabase, no fetch) so the core
// truth rules are unit-testable without a DB — see
// lib/__tests__/hqStatusInterpreter.test.ts. Callers (the overview API
// route) do the I/O and pass in AgentStatusEntry[] plus optional signal
// overrides.
//
// Non-negotiable rules encoded here (spec §10, §30):
//  - missing data is never healthy: a capability with no live telemetry at
//    all is 'unknown', never 'healthy'.
//  - retired/disabled jobs cannot degrade HQ: buildAgentStatusEntries already
//    marks them 'retired'/'disabled'; this module excludes them entirely
//    from capability evaluation (they're not "live jobs" for this purpose).
//  - failure severity is weighed by criticality, not counted: one failed
//    'supporting'/'background' job never changes a capability's tone above
//    what its capability's remaining live jobs show, and even a fully
//    unhealthy 'supporting' capability cannot push HQ posture past NORMAL.
//  - a known failure on a CRITICAL capability outranks "unknown" (it's more
//    actionable), and "unknown" on a material (critical/important)
//    capability outranks a mere "degraded" — because not knowing whether
//    something works is treated at least as seriously as knowing it's
//    partially broken.

import type { AgentStatusEntry, Criticality } from './agentStatusJobs';

export type CapabilityTone = 'healthy' | 'degraded' | 'unavailable' | 'unknown';
export type HQPosture = 'normal' | 'degraded' | 'attention' | 'unknown';

export interface CapabilityMeta {
  key: string;
  label: string;
  /** What a human loses if this capability is not healthy — used verbatim
   *  in the impact narrative, so keep it a short, plain sentence. */
  impact: string;
  /** Display order in progressive-disclosure lists (lower = shown first). */
  order: number;
}

/** The capability groups HQ Status reports on (spec §28). Every job in
 *  SCHEDULER_JOBS declares which of these it feeds via its `capability`
 *  field; a capability's own criticality is the MAX criticality among its
 *  live (non-retired/disabled) jobs, computed in computeCapabilities below
 *  rather than duplicated here. */
export const CAPABILITIES: ReadonlyArray<CapabilityMeta> = [
  { key: 'morning_intelligence', label: 'Morning Intelligence', impact: "Today's Brief and morning Telegram push may be missing or incomplete.", order: 0 },
  { key: 'emergency_monitoring', label: 'Emergency Monitoring', impact: 'Emergency feed coverage may be incomplete for one or more jurisdictions.', order: 1 },
  { key: 'technical_intelligence', label: 'Technical Intelligence', impact: 'Technical intelligence coverage may be delayed or incomplete.', order: 2 },
  { key: 'health_intelligence', label: 'Health Intelligence', impact: "Today's health intelligence may be incomplete.", order: 3 },
  { key: 'platform_core', label: 'Platform Core', impact: 'Underlying platform services (event bus, command centre, verification) may be degraded, which can affect several capabilities at once.', order: 4 },
  { key: 'hq_evolution', label: 'HQ Evolution', impact: "Last night's self-improvement cycle may not have completed.", order: 5 },
  { key: 'weekly_review', label: 'Weekly & Periodic Review', impact: 'Weekly or periodic synthesis (reviews, digests, reminders) may be delayed.', order: 6 },
  { key: 'ready_room', label: 'Ready Room Sync', impact: 'Google Tasks sync may be delayed, so Ready Room may not reflect the latest tasks.', order: 7 },
  { key: 'human_systems', label: 'Human Systems', impact: 'Human-systems nudges/check-ins may be delayed. This capability is background/best-effort by design.', order: 8 },
];

const CAPABILITY_META_BY_KEY: ReadonlyMap<string, CapabilityMeta> = new Map(
  CAPABILITIES.map((c) => [c.key, c]),
);

const CRITICALITY_RANK: Record<Criticality, number> = {
  critical: 3,
  important: 2,
  supporting: 1,
  background: 0,
};

const TONE_SEVERITY: Record<CapabilityTone, number> = {
  healthy: 0,
  degraded: 1,
  unknown: 2,
  unavailable: 3,
};

/** Combines two tones for the same capability, keeping the more severe one
 *  (and its reason). Used to fold in non-job signals (pipeline stage /
 *  source health) without a second, parallel posture calculation. */
export function worsenTone(
  current: { tone: CapabilityTone; reason: string },
  incoming: { tone: CapabilityTone; reason: string },
): { tone: CapabilityTone; reason: string } {
  return TONE_SEVERITY[incoming.tone] > TONE_SEVERITY[current.tone] ? incoming : current;
}

export interface CapabilityResult {
  key: string;
  label: string;
  criticality: Criticality;
  tone: CapabilityTone;
  reason: string;
  impact: string;
  order: number;
  failingJobs: Array<{ label: string; detail: string | null }>;
}

/** Groups live (non-retired/disabled) AgentStatusEntry rows by capability
 *  and computes each capability's tone. A capability with zero live jobs
 *  in the current registry is omitted (nothing to report — this differs
 *  from "no telemetry for jobs that exist", which is 'unknown'). */
export function computeCapabilities(jobs: AgentStatusEntry[]): CapabilityResult[] {
  const byCapability = new Map<string, AgentStatusEntry[]>();
  for (const job of jobs) {
    if (job.status === 'retired' || job.status === 'disabled') continue;
    const existing = byCapability.get(job.capability);
    if (existing) existing.push(job);
    else byCapability.set(job.capability, [job]);
  }

  const results: CapabilityResult[] = [];
  for (const [key, capJobs] of byCapability.entries()) {
    const meta = CAPABILITY_META_BY_KEY.get(key);
    const label = meta?.label ?? key;
    const impact = meta?.impact ?? 'Impact not documented for this capability.';
    const order = meta?.order ?? 999;

    const criticality = capJobs.reduce<Criticality>(
      (max, j) => (CRITICALITY_RANK[j.criticality] > CRITICALITY_RANK[max] ? j.criticality : max),
      'background',
    );

    const known = capJobs.filter((j) => j.status !== 'unknown');
    const failed = known.filter((j) => j.status === 'failed');

    let tone: CapabilityTone;
    let reason: string;

    if (known.length === 0) {
      tone = 'unknown';
      reason = `No recent telemetry for any job feeding ${label}.`;
    } else if (failed.length > 0) {
      // A known failure on a critical capability is treated as materially
      // unavailable (spec §30: "critical capability unavailable ... may
      // make HQ ATTENTION"); on a lesser capability it's simply degraded —
      // HQ stays usable, this is a system issue, not a human task.
      tone = criticality === 'critical' ? 'unavailable' : 'degraded';
      reason = failed.length === 1
        ? `${failed[0].label} is failing: ${failed[0].lastAction ?? 'no detail recorded'}.`
        : `${failed.length} jobs feeding ${label} are failing.`;
    } else if (known.length < capJobs.length) {
      // Some jobs ok, some never reported — honest partial-unknown rather
      // than papering over the gap as healthy.
      tone = 'unknown';
      reason = `${capJobs.length - known.length} of ${capJobs.length} jobs feeding ${label} have no recent telemetry.`;
    } else {
      tone = 'healthy';
      reason = `All ${capJobs.length} job${capJobs.length === 1 ? '' : 's'} feeding ${label} reported OK.`;
    }

    results.push({
      key,
      label,
      criticality,
      tone,
      reason,
      impact,
      order,
      failingJobs: failed.map((j) => ({ label: j.label, detail: j.lastAction })),
    });
  }

  return results.sort((a, b) => a.order - b.order);
}

/** Applies an external signal (e.g. a pipeline-stage or source-health
 *  reading not visible in job heartbeats) to a specific capability, taking
 *  whichever of the existing vs. incoming tone is more severe. No-op if the
 *  capability isn't present (e.g. its jobs are all retired/disabled). */
export function applyCapabilitySignal(
  capabilities: CapabilityResult[],
  capabilityKey: string,
  signal: { tone: CapabilityTone; reason: string },
): CapabilityResult[] {
  return capabilities.map((c) => {
    if (c.key !== capabilityKey) return c;
    const worsened = worsenTone({ tone: c.tone, reason: c.reason }, signal);
    return worsened.tone === c.tone ? c : { ...c, tone: worsened.tone, reason: worsened.reason };
  });
}

export interface HQNarrative {
  impact: string | null;
  stillWorking: string[];
  next: string | null;
  actionRequired: boolean;
  actionNote: string;
}

export interface HQInterpretation {
  posture: HQPosture;
  headline: string;
  narrative: HQNarrative;
  capabilities: CapabilityResult[];
  materialDegradations: string[];
  unknownMaterialAreas: string[];
  attentionItems: Array<{ title: string; detail: string }>;
  needsAttentionCount: number;
  unknownMaterialCount: number;
}

const MATERIAL: ReadonlySet<Criticality> = new Set(['critical', 'important']);

/** Deterministic HQ-level posture from capability tones — never a raw
 *  failed-job count (spec §8, §26, §30). Precedence, most severe first:
 *   1. ATTENTION — a critical capability is unavailable (known failure that
 *      materially affects HQ; domain_registry.critical-equivalent).
 *   2. UNKNOWN   — a material (critical/important) capability's health
 *      cannot be established at all. Ranked above DEGRADED deliberately:
 *      not knowing is treated at least as seriously as a partial, known
 *      problem (spec §40).
 *   3. DEGRADED  — a material capability is degraded (or unavailable but
 *      non-critical, which this module never actually produces — kept for
 *      defensiveness) while HQ remains substantially usable.
 *   4. NORMAL    — every material capability is healthy. Supporting/
 *      background capability failures never appear in this calculation. */
export function computePosture(capabilities: CapabilityResult[]): HQPosture {
  const material = capabilities.filter((c) => MATERIAL.has(c.criticality));
  if (material.some((c) => c.criticality === 'critical' && c.tone === 'unavailable')) return 'attention';
  if (material.some((c) => c.tone === 'unknown')) return 'unknown';
  if (material.some((c) => c.tone === 'degraded' || c.tone === 'unavailable')) return 'degraded';
  return 'normal';
}

function headlineFor(posture: HQPosture): string {
  switch (posture) {
    case 'normal': return 'HQ is operating normally';
    case 'degraded': return 'HQ is degraded';
    case 'attention': return 'HQ needs your attention';
    case 'unknown': return 'Status partially unknown';
  }
}

/** Builds the full interpreted payload from capability results. Pure
 *  string templating — no LLM (spec §31): core truth must not depend on a
 *  model call that can fail or hallucinate. */
export function interpretHQStatus(capabilities: CapabilityResult[]): HQInterpretation {
  const posture = computePosture(capabilities);
  const material = capabilities.filter((c) => MATERIAL.has(c.criticality));

  const materialDegradations = material.filter((c) => c.tone !== 'healthy').map((c) => c.label);
  const unknownMaterialAreas = material.filter((c) => c.tone === 'unknown').map((c) => c.label);
  const attentionCapabilities = material.filter((c) => c.criticality === 'critical' && c.tone === 'unavailable');

  const attentionItems = attentionCapabilities.map((c) => ({ title: c.label, detail: c.reason }));

  const stillWorking = material
    .filter((c) => c.tone === 'healthy')
    .map((c) => c.label);

  const impactSentences = material
    .filter((c) => c.tone !== 'healthy')
    .slice(0, 3)
    .map((c) => c.impact);

  const narrative: HQNarrative = {
    impact: posture === 'normal' ? null : (impactSentences.join(' ') || null),
    stillWorking,
    next: posture === 'normal'
      ? null
      : 'Automatic retry follows each affected job\'s normal schedule — see Automations for exact cadence.',
    actionRequired: posture === 'attention',
    actionNote: posture === 'attention'
      ? 'See the automations listed below — this needs a look.'
      : 'Nothing needs your action right now.',
  };

  return {
    posture,
    headline: headlineFor(posture),
    narrative,
    capabilities,
    materialDegradations,
    unknownMaterialAreas,
    attentionItems,
    needsAttentionCount: attentionItems.length,
    unknownMaterialCount: unknownMaterialAreas.length,
  };
}

export interface CaptainChairSummary {
  hq_posture: 'NORMAL' | 'DEGRADED' | 'ATTENTION' | 'UNKNOWN';
  summary: string;
  material_degradations: string[];
  needs_attention_count: number;
  unknown_material_count: number;
  last_updated: string;
  freshness: 'live' | 'unavailable';
}

/** Small, stable summary shape for Captain's Chair / LifeOS (spec §32-33).
 *  Deliberately tiny and posture-first — those surfaces must never render
 *  a wall of job health, only this. */
export function buildCaptainChairSummary(
  interpretation: HQInterpretation,
  fetchedAtIso: string,
): CaptainChairSummary {
  const postureUpper = interpretation.posture.toUpperCase() as CaptainChairSummary['hq_posture'];
  const summary = interpretation.narrative.impact
    ? `${interpretation.headline} — ${interpretation.narrative.impact}`
    : interpretation.headline;

  return {
    hq_posture: postureUpper,
    summary,
    material_degradations: interpretation.materialDegradations,
    needs_attention_count: interpretation.needsAttentionCount,
    unknown_material_count: interpretation.unknownMaterialCount,
    last_updated: fetchedAtIso,
    freshness: 'live',
  };
}
