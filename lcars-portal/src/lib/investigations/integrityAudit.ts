/**
 * MSN-0357 — Investigation type definitions: Integrity Audit (diagnose),
 * Integrity Audit (verify), and Redundancy Reconciliation.
 *
 * Per MSN-0353 §1.1-§1.3 and the journeys these types actually come from
 * (docs/MSN-0350-INVESTIGATION-JOURNEYS.md #1, #2, #3, #4, #5, #13, #14, #17):
 * every real instance of these types compared the system's *claimed*
 * behaviour against its *real* source, or compared two systems' real logic
 * against each other - never a UI surface, never invented data.
 *
 * This file deliberately does not reimplement the interrupt-coverage
 * checking logic that already exists. It reuses:
 *   - `validateCoverage()` and `INTERRUPT_COVERAGE_REGISTRY` from
 *     lib/interruptCoverageRegistry.ts (MSN-0351 Objective 3's real,
 *     working "does the registry's declared state match reality" check).
 *   - `NOMINATORS` from lib/interruptAssembly.ts (the real, live array of
 *     Interrupt Assembly evaluators - exported for this file, MSN-0357).
 *
 * All three definitions below read these two real, already-existing
 * sources structurally (function identity, declared text) - they never
 * invoke a nominator against a live Supabase client, so `assembleEvidence`
 * needs no database credentials and no mocking to run honestly in tests.
 */

import type { InvestigationDefinition, TriggerContext } from '@/lib/investigationEngine';
import {
  INTERRUPT_COVERAGE_REGISTRY,
  validateCoverage,
  type InterruptContractEntry,
  type ValidationResult as CoverageValidationResult,
} from '@/lib/interruptCoverageRegistry';
import { NOMINATORS } from '@/lib/interruptAssembly';

// ─── Shared evidence-assembly machinery (reused by diagnose + verify) ─────

/**
 * A registry entry's own declared text sometimes names the real nominator
 * function that implements it (e.g. "...wired into EOS Interrupt Assembly
 * as missionNominator (lib/interruptAssembly.ts)"). Extracting those names
 * directly from the declared text - rather than hand-maintaining a second
 * mapping table here - means this check reads the registry's own claim,
 * the same "does the system's own claimed behaviour match its real source"
 * shape every Integrity Audit journey (#1, #2, #4, #13, #14) actually is.
 */
const NOMINATOR_NAME_PATTERN = /\b[A-Za-z][A-Za-z0-9]*Nominator\b/g;

function registryEntryText(entry: InterruptContractEntry): string {
  return [entry.conditions, entry.evidenceSource, entry.falsePositiveGuard, entry.degradationBehaviour, entry.knownGap ?? ''].join(' ');
}

function referencedNominatorNames(entry: InterruptContractEntry): string[] {
  const matches = registryEntryText(entry).match(NOMINATOR_NAME_PATTERN) ?? [];
  return Array.from(new Set(matches));
}

export interface IntegrityAuditEvidence {
  /** Re-check framing (Integrity Audit — verify only): which prior fix this run is re-confirming. */
  reCheckOf?: string;
  /** Live result of the registry's own internal consistency check (MSN-0351 Objective 3). */
  coverageValidation: CoverageValidationResult;
  /** `fn.name` of every function actually wired into the live NOMINATORS array right now. */
  liveNominatorNames: string[];
  /** Every nominator function name any registry entry's own text claims to be backed by. */
  registryClaimedNominatorNames: string[];
  /** Registry text names a nominator that does not actually exist in the live array - a stale/incorrect claim. */
  claimedButMissingFromLive: string[];
  /** A live nominator exists that no registry entry's text claims coverage for - the reverse mismatch MSN-0354 found once already (health-insights-risk-flags, before its registry entry existed). */
  liveButUndeclaredInRegistry: string[];
  mismatchFound: boolean;
}

// Exported (MSN-0357) so lib/investigations/coverageGaps.ts's Upstream
// Coverage Gap definition (MSN-0353 §1.4) can reuse this exact comparison -
// registry-declared coverage vs. the live NOMINATORS array by function
// identity - rather than re-deriving a second copy of it. Both types read
// the same real evidence; they differ in trigger framing, decision
// vocabulary, and completion criteria, not in how the comparison itself is
// computed. See that file for why the two types are legitimately distinct
// despite sharing this function.
export async function assembleIntegrityEvidence(trigger: TriggerContext): Promise<IntegrityAuditEvidence> {
  const coverageValidation = validateCoverage();
  const liveNominatorNames = NOMINATORS.map((fn) => fn.name).filter((name) => name.length > 0);
  const registryClaimedNominatorNames = Array.from(
    new Set(INTERRUPT_COVERAGE_REGISTRY.flatMap((entry) => referencedNominatorNames(entry)))
  );
  const claimedButMissingFromLive = registryClaimedNominatorNames.filter((name) => !liveNominatorNames.includes(name));
  const liveButUndeclaredInRegistry = liveNominatorNames.filter((name) => !registryClaimedNominatorNames.includes(name));

  return {
    reCheckOf: trigger.originRef,
    coverageValidation,
    liveNominatorNames,
    registryClaimedNominatorNames,
    claimedButMissingFromLive,
    liveButUndeclaredInRegistry,
    mismatchFound:
      !coverageValidation.ok || claimedButMissingFromLive.length > 0 || liveButUndeclaredInRegistry.length > 0,
  };
}

// Exported alongside assembleIntegrityEvidence, same reuse rationale.
export function validateIntegrityEvidence(evidence: IntegrityAuditEvidence): { ok: boolean; problems: string[] } {
  const problems: string[] = [];
  if (INTERRUPT_COVERAGE_REGISTRY.length === 0) problems.push('the Interrupt Coverage Registry is empty - nothing to compare against');
  if (evidence.liveNominatorNames.length === 0) problems.push('lib/interruptAssembly.ts NOMINATORS resolved to zero named functions - live-side comparison is impossible');
  return { ok: problems.length === 0, problems };
}

// Exported alongside assembleIntegrityEvidence, same reuse rationale.
export function mismatchSummary(evidence: IntegrityAuditEvidence): string {
  const parts: string[] = [];
  if (!evidence.coverageValidation.ok) parts.push(`registry self-check failed: ${evidence.coverageValidation.problems.join('; ')}`);
  if (evidence.claimedButMissingFromLive.length > 0) parts.push(`registry claims nominator(s) not actually live: ${evidence.claimedButMissingFromLive.join(', ')}`);
  if (evidence.liveButUndeclaredInRegistry.length > 0) parts.push(`live nominator(s) with no registry entry claiming them: ${evidence.liveButUndeclaredInRegistry.join(', ')}`);
  return parts.join(' | ');
}

// ─── 1. Integrity Audit — diagnose ─────────────────────────────────────────
// MSN-0353 §1.1. Trigger: a systematic review, not a reported symptom -
// "is this actually working the way it claims to." Journeys #1, #2, #4,
// #13, #14 are all this shape in miniature: the system's own claimed
// behaviour (here: the registry's declared nominator coverage) checked
// directly against its real source (here: the live NOMINATORS array).

export type IntegrityAuditDiagnoseDecision = 'confirmed-defect' | 'confirmed-sound';

export const integrityAuditDiagnose: InvestigationDefinition<IntegrityAuditEvidence, IntegrityAuditDiagnoseDecision> = {
  type: 'integrity-audit-diagnose',
  label: 'Integrity Audit — diagnose',
  owner: 'engineering',
  triggerDescription:
    'A systematic review process, not a reported symptom - nobody complained; someone asked "is this actually working the way it claims to." (MSN-0353 §1.1; journeys #1, #2, #4, #13, #14.)',
  requiredEvidence: [
    'result of interruptCoverageRegistry.validateCoverage() against the live INTERRUPT_COVERAGE_REGISTRY',
    'the real, live NOMINATORS array from lib/interruptAssembly.ts, read by function identity (fn.name)',
    'every nominator function name each registry entry\'s own declared text claims to be backed by',
  ],
  evidenceSources: [
    'lcars-portal/src/lib/interruptCoverageRegistry.ts (INTERRUPT_COVERAGE_REGISTRY, validateCoverage)',
    'lcars-portal/src/lib/interruptAssembly.ts (NOMINATORS)',
  ],
  validationRules: [
    'the registry must be non-empty - an empty registry cannot be diagnosed against',
    'the live NOMINATORS array must resolve to at least one named function - identity-based comparison requires named function declarations, not anonymous closures',
  ],
  possibleDecisionKinds: ['confirmed-defect', 'confirmed-sound'],
  completionCriteria:
    'A decision (confirmed-defect or confirmed-sound) has been recorded against the assembled evidence. Per MSN-0353 §1.1 there is no execute/verify stage on this type - see the comment on `execute` below.',
  auditOutputs: [
    'registry self-check pass/fail and any problems reported by validateCoverage()',
    'the list of any registry-claimed nominator names not actually present in the live array',
    'the list of any live nominator names no registry entry claims to cover',
    'the chosen decision id',
    'a learning insight when a mismatch was found, otherwise none',
  ],
  assembleEvidence: assembleIntegrityEvidence,
  validateEvidence: (evidence) => validateIntegrityEvidence(evidence),
  decisionOptions: (evidence) => {
    if (evidence.mismatchFound) {
      return [
        {
          id: 'confirmed-defect',
          label: `Confirmed defect - ${mismatchSummary(evidence)} - file as a mission for engineering follow-up`,
          value: 'confirmed-defect',
          isReversible: true,
        },
        {
          id: 'confirmed-sound',
          label: 'Reviewed the mismatch and judged it not a real defect (e.g. an in-flight rename) - no action',
          value: 'confirmed-sound',
          isReversible: true,
        },
      ];
    }
    return [
      {
        id: 'confirmed-sound',
        label: 'Confirmed sound - the registry\'s declared coverage and the live nominator wiring agree',
        value: 'confirmed-sound',
        isReversible: true,
      },
    ];
  },
  // No execute/verify: per MSN-0353 §1.1, the actual fix for a confirmed
  // defect (correcting a stale registry claim, wiring a missing nominator,
  // updating drifted text) is out-of-band engineering work done in a real
  // code change and PR - not something an investigation definition performs
  // on its own. The engine records this honestly (`attempted: false`,
  // `not_applicable`) rather than this file inventing a fake execution.
  isComplete: (state) => {
    if (state.chosenDecision === undefined) {
      return { complete: false, reason: 'awaiting a decision - evidence was assembled but nothing has been decided yet' };
    }
    return { complete: true, reason: `resolved as "${state.chosenDecision}"` };
  },
  learn: (state) => {
    const evidence = state.evidence;
    if (!evidence || !evidence.mismatchFound || state.chosenDecision !== 'confirmed-defect') {
      return { insight: null, category: 'none' };
    }
    const category = evidence.coverageValidation.ok ? 'process-gap' : 'coverage-gap';
    return {
      insight: `Integrity Audit found a real claim/reality mismatch between the Interrupt Coverage Registry and the live Interrupt Assembly wiring: ${mismatchSummary(evidence)}`,
      category,
    };
  },
};

// ─── 2. Integrity Audit — verify ───────────────────────────────────────────
// MSN-0353 §1.2. Trigger: "I changed X - does it actually do what I
// intended now." Journey #17's shape. Reuses the exact same evidence
// assembly as diagnose - re-confirmation is the same comparison run again,
// not a different check - but is framed around `trigger.originRef` naming
// which prior fix is being re-checked.

export type IntegrityAuditVerifyDecision = 'confirmed-sound' | 'reopen-as-diagnose';

export const integrityAuditVerify: InvestigationDefinition<IntegrityAuditEvidence, IntegrityAuditVerifyDecision> = {
  type: 'integrity-audit-verify',
  label: 'Integrity Audit — verify',
  owner: 'engineering',
  triggerDescription:
    '"I changed X - does it actually do what I intended now." A re-confirmation of a specific prior fix, not first discovery. (MSN-0353 §1.2; journey #17, confirming the intelligence risk-filter fix.)',
  requiredEvidence: [
    'the same comparison as Integrity Audit — diagnose, re-run post-change',
    'trigger.originRef naming which prior fix (mission id, commit, or registry capability id) is being re-checked',
  ],
  evidenceSources: [
    'lcars-portal/src/lib/interruptCoverageRegistry.ts (INTERRUPT_COVERAGE_REGISTRY, validateCoverage)',
    'lcars-portal/src/lib/interruptAssembly.ts (NOMINATORS)',
  ],
  validationRules: [
    'a re-check must name what it is re-checking - trigger.originRef should be present, though its absence blocks nothing structurally (see validateEvidence problems vs. a hard failure)',
    'the registry must be non-empty and the live NOMINATORS array must resolve to at least one named function, same structural requirement as diagnose',
  ],
  possibleDecisionKinds: ['confirmed-sound', 'reopen-as-diagnose'],
  completionCriteria:
    'The specific claim the original fix made - that the registry\'s declared coverage and the live nominator wiring cannot disagree - is checked directly against current state, not inferred from the original fix having merged.',
  auditOutputs: [
    'which prior fix this run re-checked (trigger.originRef)',
    'registry self-check pass/fail on this run',
    'any claim/reality mismatch found on this run',
    'the chosen decision id',
  ],
  assembleEvidence: assembleIntegrityEvidence,
  validateEvidence: (evidence, trigger) => {
    const base = validateIntegrityEvidence(evidence);
    // Not naming what's being re-checked is a real quality problem worth
    // surfacing, but per MSN-0353 §1.2 the comparison itself is still
    // meaningful without it - this is reported as a problem only when the
    // base structural check already failed, so it never blocks a run on
    // its own the way a missing NOMINATORS array does.
    if (!trigger.originRef && !base.ok) {
      return { ok: false, problems: [...base.problems, 'no originRef given - this verify run cannot say which prior fix it is re-confirming'] };
    }
    return base;
  },
  decisionOptions: (evidence) => {
    if (evidence.mismatchFound) {
      return [
        {
          id: 'reopen-as-diagnose',
          label: `Reopen as diagnose - the re-check found a live mismatch: ${mismatchSummary(evidence)}`,
          value: 'reopen-as-diagnose',
          isReversible: true,
        },
        {
          id: 'confirmed-sound',
          label: 'Reviewed the mismatch and judged the prior fix still sound enough to leave closed',
          value: 'confirmed-sound',
          isReversible: true,
        },
      ];
    }
    return [
      {
        id: 'confirmed-sound',
        label: 'Confirmed sound - the prior fix still holds under the current live comparison',
        value: 'confirmed-sound',
        isReversible: true,
      },
    ];
  },
  // No execute/verify, same reasoning as diagnose: reopening as a new
  // diagnose is itself the outcome of this decision, not an execution this
  // definition performs.
  isComplete: (state) => {
    if (state.chosenDecision === undefined) {
      return { complete: false, reason: 'awaiting a decision - re-check evidence was assembled but nothing has been decided yet' };
    }
    return { complete: true, reason: `resolved as "${state.chosenDecision}"` };
  },
  learn: (state) => {
    const evidence = state.evidence;
    if (!evidence) return { insight: null, category: 'none' };
    if (state.chosenDecision === 'reopen-as-diagnose') {
      return {
        insight: `Re-check of ${evidence.reCheckOf ?? 'an unnamed prior fix'} found the original fix incomplete: ${mismatchSummary(evidence)}`,
        category: evidence.coverageValidation.ok ? 'process-gap' : 'coverage-gap',
      };
    }
    return { insight: null, category: 'none' };
  },
};

// ─── 3. Redundancy Reconciliation ──────────────────────────────────────────
// MSN-0353 §1.3. Trigger: a review surfaces two or more independently-built
// systems doing overlapping work that can silently disagree. Journeys #3
// (two blocked-mission alert engines with different thresholds) and #5
// (four independent mission-ID minting paths) are this shape: "the two
// systems' actual check-lists or logic, compared line-by-line - not their
// surrounding UI." The real, generalizable target used here: every pair of
// interrupt-capable entries in INTERRUPT_COVERAGE_REGISTRY, compared by the
// real database tables/columns named in their own `evidenceSource` field -
// not by name, not by domain, by the actual data each one reads.

export interface RedundancyCandidatePair {
  a: string;
  b: string;
  sharedEvidenceTokens: string[];
  /** Whether each side of the pair is currently a live Interrupt Assembly nominator (higher-risk overlap) vs. only registry-declared (lower-risk but still a real duplication candidate per MSN-0353 §1.3). */
  aIsLiveNominator: boolean;
  bIsLiveNominator: boolean;
}

export interface RedundancyEvidence {
  /** 'full-registry', or a single capability id when trigger.originRef scopes the comparison to just that capability's overlaps. */
  scope: string;
  candidatePairs: RedundancyCandidatePair[];
  redundancyFound: boolean;
}

// Timestamp/audit columns are real snake_case identifiers but appear on
// nearly every table in this codebase - including them would make almost
// every pair "overlap" on created_at/generated_at alone, which is exactly
// the kind of noise MSN-0350's journeys named as never actually diagnostic.
// Excluding them is a disclosed, deliberate choice, not a hidden filter.
const GENERIC_TIMESTAMP_TOKENS = new Set(['created_at', 'updated_at', 'generated_at', 'published_at']);

/** Extracts real snake_case table/column identifiers directly out of a registry entry's own declared evidenceSource text - no hand-maintained second list to drift from the registry. */
function evidenceTokens(entry: InterruptContractEntry): string[] {
  const matches = entry.evidenceSource.match(/\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/g) ?? [];
  return Array.from(new Set(matches)).filter((token) => !GENERIC_TIMESTAMP_TOKENS.has(token));
}

function intersect(a: string[], b: string[]): string[] {
  const setB = new Set(b);
  return a.filter((token) => setB.has(token));
}

export type RedundancyReconciliationDecision = 'merge' | 'keep-separate-relabel' | 'no-redundancy-found';

export const redundancyReconciliation: InvestigationDefinition<RedundancyEvidence, RedundancyReconciliationDecision> = {
  type: 'redundancy-reconciliation',
  label: 'Redundancy Reconciliation',
  owner: 'engineering',
  triggerDescription:
    'A review surfaces two or more independently-built systems doing overlapping work that can silently disagree. (MSN-0353 §1.3; journey #3 - two blocked-mission alert engines with different thresholds; journey #5 - four independent mission-ID minting code paths.)',
  requiredEvidence: [
    'every interrupt-capable entry in INTERRUPT_COVERAGE_REGISTRY (canInterrupt !== \'no\'), compared pairwise',
    'the real snake_case table/column tokens named in each entry\'s own evidenceSource field',
    'whether each side of a shared-evidence pair is currently wired into the live NOMINATORS array (lib/interruptAssembly.ts)',
  ],
  evidenceSources: [
    'lcars-portal/src/lib/interruptCoverageRegistry.ts (INTERRUPT_COVERAGE_REGISTRY)',
    'lcars-portal/src/lib/interruptAssembly.ts (NOMINATORS)',
  ],
  validationRules: [
    'the registry must contain at least one interrupt-capable entry (canInterrupt !== \'no\') - there is nothing to reconcile against zero capabilities',
    'a scoped run (trigger.originRef set to a capability id) must name a capability id that actually exists in the registry',
  ],
  possibleDecisionKinds: ['merge', 'keep-separate-relabel', 'no-redundancy-found'],
  completionCriteria:
    'A decision has been recorded on every candidate pair found. Per MSN-0353 §1.3, completion means the two systems can no longer produce contradictory output for the same real condition - which for "keep-separate-relabel" means the honest relabelling, and for "merge" means the merge, are the out-of-band engineering follow-up, not something this definition performs itself (see the comment on `execute` below).',
  auditOutputs: [
    'the comparison scope (full registry, or a single capability id)',
    'every candidate pair found, with the real shared evidence tokens that produced the match',
    'whether either or both sides of each candidate pair are live Interrupt Assembly nominators',
    'the chosen decision id',
  ],
  assembleEvidence: async (trigger) => {
    const scope = trigger.originRef;
    const entries = INTERRUPT_COVERAGE_REGISTRY.filter((e) => e.canInterrupt !== 'no');
    const liveNames = new Set(NOMINATORS.map((fn) => fn.name));
    const isLive = (entry: InterruptContractEntry) => referencedNominatorNames(entry).some((name) => liveNames.has(name));
    const tokensByCapability = new Map(entries.map((e) => [e.capability, evidenceTokens(e)]));

    const candidatePairs: RedundancyCandidatePair[] = [];
    for (let i = 0; i < entries.length; i += 1) {
      for (let j = i + 1; j < entries.length; j += 1) {
        const a = entries[i];
        const b = entries[j];
        if (scope && a.capability !== scope && b.capability !== scope) continue;
        const shared = intersect(tokensByCapability.get(a.capability) ?? [], tokensByCapability.get(b.capability) ?? []);
        if (shared.length === 0) continue;
        candidatePairs.push({
          a: a.capability,
          b: b.capability,
          sharedEvidenceTokens: shared,
          aIsLiveNominator: isLive(a),
          bIsLiveNominator: isLive(b),
        });
      }
    }

    return { scope: scope ?? 'full-registry', candidatePairs, redundancyFound: candidatePairs.length > 0 };
  },
  validateEvidence: (evidence) => {
    const problems: string[] = [];
    if (INTERRUPT_COVERAGE_REGISTRY.filter((e) => e.canInterrupt !== 'no').length === 0) {
      problems.push('no interrupt-capable registry entries exist to reconcile');
    }
    if (evidence.scope !== 'full-registry' && !INTERRUPT_COVERAGE_REGISTRY.some((e) => e.capability === evidence.scope)) {
      problems.push(`scoped capability "${evidence.scope}" does not exist in the registry`);
    }
    return { ok: problems.length === 0, problems };
  },
  decisionOptions: (evidence) => {
    if (!evidence.redundancyFound) {
      return [
        {
          id: 'no-redundancy-found',
          label: `No overlapping evidence sources found in scope (${evidence.scope})`,
          value: 'no-redundancy-found',
          isReversible: true,
        },
      ];
    }
    return [
      {
        id: 'merge',
        label: `Merge into one authoritative evaluator - genuine duplicates sharing: ${evidence.candidatePairs.map((p) => p.sharedEvidenceTokens.join('/')).join('; ')}`,
        value: 'merge',
        isReversible: true,
      },
      {
        id: 'keep-separate-relabel',
        label: 'Genuinely different signals reading overlapping data - keep both, but relabel honestly so they stop looking like disagreement',
        value: 'keep-separate-relabel',
        isReversible: true,
      },
    ];
  },
  // No execute/verify: per MSN-0353 §1.3, the actual merge or relabel is
  // out-of-band engineering work (a real code/schema change), not something
  // this definition performs. The engine records that honestly rather than
  // this file inventing a fake merge.
  isComplete: (state) => {
    if (state.chosenDecision === undefined) {
      return { complete: false, reason: 'awaiting a decision - candidate pairs were assembled but nothing has been decided yet' };
    }
    return { complete: true, reason: `resolved as "${state.chosenDecision}"` };
  },
  learn: (state) => {
    const evidence = state.evidence;
    if (!evidence || !evidence.redundancyFound || state.chosenDecision === 'no-redundancy-found') {
      return { insight: null, category: 'none' };
    }
    const pairs = evidence.candidatePairs.map((p) => `${p.a}↔${p.b} (${p.sharedEvidenceTokens.join(', ')})`).join('; ');
    return {
      insight: `Redundancy Reconciliation found independently-built capabilities reading overlapping evidence that could silently disagree: ${pairs}`,
      category: 'process-gap',
    };
  },
};
