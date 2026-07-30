/**
 * MSN-0357 — Investigation Engine.
 *
 * The operational embodiment of MSN-0353's ten-type investigation
 * architecture (docs/MSN-0353-INVESTIGATION-ARCHITECTURE.md). This is
 * deliberately NOT a general workflow/orchestration framework — it is the
 * one shared lifecycle every investigation type in this product already
 * follows in reality (docs/MSN-0350-INVESTIGATION-JOURNEYS.md's 22
 * reconstructed journeys), made explicit and machine-checkable:
 *
 *   Trigger -> Evidence Assembly -> Evidence Validation -> Decision Options
 *     -> Execution (where applicable) -> Verification -> Completion -> Learning
 *
 * The success criterion for this file (per MSN-0357) is structural, not
 * behavioral: `openInvestigation`/`resolveInvestigation` below must NEVER
 * branch on `definition.type`. Every investigation type's actual behavior
 * lives entirely in its `InvestigationDefinition` (see lib/investigations/).
 * Where a stage genuinely does not apply to a type (e.g. a Trend Scan has
 * no execution to verify), the definition simply omits `execute`/`verify` -
 * the runner records that honestly rather than inventing a fake pass.
 *
 * The engine assembles investigations, not screens. Nothing in this file
 * renders UI or knows about any route.
 */

export type InvestigationOwner = 'captain' | 'engineering' | 'shared';

export type InvestigationStage =
  | 'trigger'
  | 'evidence_assembly'
  | 'evidence_validation'
  | 'decision_options'
  | 'execution'
  | 'verification'
  | 'completion'
  | 'learning';

export const STAGE_ORDER: InvestigationStage[] = [
  'trigger',
  'evidence_assembly',
  'evidence_validation',
  'decision_options',
  'execution',
  'verification',
  'completion',
  'learning',
];

/** What set this investigation in motion. Per MSN-0353: investigations begin with a trigger, not a destination. */
export interface TriggerContext {
  investigationType: string;
  /** Why this run happened, in the Captain/engineer's own terms - not a system event name. */
  reason: string;
  originatedAt: string;
  /** The specific artifact that triggered this (a queue row id, a mission id, a table name) - real investigations never begin by browsing a menu. */
  originRef?: string;
}

export interface ValidationResult {
  ok: boolean;
  problems: string[];
}

export interface DecisionOption<TDecision> {
  id: string;
  label: string;
  value: TDecision;
  isReversible: boolean;
}

export interface ExecutionResult {
  attempted: boolean;
  /** null = not applicable / execution has no pass-fail concept for this type */
  success: boolean | null;
  detail: string;
}

export interface VerificationResult {
  status: 'verified' | 'failed' | 'not_attempted' | 'mismatch' | 'not_applicable';
  detail: string;
}

export interface CompletionState {
  complete: boolean;
  /** The completion marker, per MSN-0353: how it was actually known the investigation was finished. */
  reason: string;
}

export interface AuditRecord {
  stage: InvestigationStage;
  summary: string;
  evidenceRefs: string[];
}

export interface LearningOutput {
  insight: string | null;
  category: 'classifier-defect' | 'coverage-gap' | 'process-gap' | 'precedent' | 'none';
}

/**
 * Every investigation type must declare all nine of these fields (per
 * MSN-0357's requirement) — the first block is inspectable metadata, true
 * without running any code; the second block is the runnable behavior the
 * shared runner below invokes. `execute`/`verify` are optional: omitting
 * them is how a type honestly declares "this stage does not apply to me,"
 * not a shortcut the runner has to special-case.
 */
export interface InvestigationDefinition<TEvidence, TDecision> {
  // ── Declared metadata ──────────────────────────────────────────────
  type: string;
  label: string;
  owner: InvestigationOwner;
  triggerDescription: string;
  requiredEvidence: string[];
  evidenceSources: string[];
  validationRules: string[];
  possibleDecisionKinds: string[];
  completionCriteria: string;
  auditOutputs: string[];

  // ── Runnable behavior ──────────────────────────────────────────────
  assembleEvidence: (trigger: TriggerContext) => Promise<TEvidence>;
  validateEvidence: (evidence: TEvidence, trigger: TriggerContext) => ValidationResult;
  decisionOptions: (evidence: TEvidence, trigger: TriggerContext) => DecisionOption<TDecision>[];
  execute?: (decision: TDecision, evidence: TEvidence, trigger: TriggerContext) => Promise<ExecutionResult>;
  verify?: (execution: ExecutionResult, evidence: TEvidence, trigger: TriggerContext) => Promise<VerificationResult>;
  isComplete: (state: InvestigationRunState<TEvidence, TDecision>) => CompletionState;
  learn: (state: InvestigationRunState<TEvidence, TDecision>) => LearningOutput;
}

export interface InvestigationRunState<TEvidence, TDecision> {
  definition: InvestigationDefinition<TEvidence, TDecision>;
  trigger: TriggerContext;
  evidence?: TEvidence;
  validation?: ValidationResult;
  decisionOptions?: DecisionOption<TDecision>[];
  chosenDecision?: TDecision;
  execution?: ExecutionResult;
  verification?: VerificationResult;
  completion?: CompletionState;
  learning?: LearningOutput;
  audit: AuditRecord[];
  stagesReached: InvestigationStage[];
}

function pushAudit<TEvidence, TDecision>(
  state: InvestigationRunState<TEvidence, TDecision>,
  stage: InvestigationStage,
  summary: string,
  evidenceRefs: string[] = []
): void {
  state.stagesReached.push(stage);
  state.audit.push({ stage, summary, evidenceRefs });
}

/**
 * Stages 1-4: Trigger through Decision Options. Every investigation type
 * runs through this exact sequence — this function never reads
 * `definition.type`. Fails closed: invalid evidence stops here, before any
 * decision is ever offered.
 */
export async function openInvestigation<TEvidence, TDecision>(
  definition: InvestigationDefinition<TEvidence, TDecision>,
  trigger: TriggerContext
): Promise<InvestigationRunState<TEvidence, TDecision>> {
  const state: InvestigationRunState<TEvidence, TDecision> = {
    definition,
    trigger,
    audit: [],
    stagesReached: [],
  };
  pushAudit(state, 'trigger', trigger.reason, trigger.originRef ? [trigger.originRef] : []);

  state.evidence = await definition.assembleEvidence(trigger);
  pushAudit(state, 'evidence_assembly', `assembled: ${definition.requiredEvidence.join(', ')}`, definition.evidenceSources);

  state.validation = definition.validateEvidence(state.evidence, trigger);
  pushAudit(
    state,
    'evidence_validation',
    state.validation.ok ? 'valid' : `blocked: ${state.validation.problems.join('; ')}`
  );
  if (!state.validation.ok) {
    state.completion = { complete: false, reason: 'blocked at evidence validation — no decision was ever offered' };
    return state;
  }

  state.decisionOptions = definition.decisionOptions(state.evidence, trigger);
  pushAudit(state, 'decision_options', `${state.decisionOptions.length} option(s): ${state.decisionOptions.map((o) => o.id).join(', ') || 'none'}`);

  return state;
}

/**
 * Stages 5-8: Execution through Learning, given a decision (or `undefined`
 * for "hold — no decision made this pass", matching Decide's existing
 * hold semantics). Same guarantee: never reads `definition.type`.
 *
 * Can be called immediately after `openInvestigation` (synchronous
 * investigation types) or much later, after a human has actually reviewed
 * the decision options (Queue Resolution-shaped types) — the state object
 * carries everything needed either way, matching how a real
 * build_request_inbox row already persists between "queued" and "decided."
 */
export async function resolveInvestigation<TEvidence, TDecision>(
  state: InvestigationRunState<TEvidence, TDecision>,
  chosenDecision: TDecision | undefined
): Promise<InvestigationRunState<TEvidence, TDecision>> {
  const { definition, trigger } = state;

  if (!state.validation?.ok) {
    // Already blocked at evidence_validation — resolving further is not possible.
    return state;
  }

  if (chosenDecision !== undefined) {
    state.chosenDecision = chosenDecision;

    if (definition.execute) {
      state.execution = await definition.execute(chosenDecision, state.evidence as TEvidence, trigger);
      pushAudit(state, 'execution', state.execution.detail);

      if (definition.verify) {
        state.verification = await definition.verify(state.execution, state.evidence as TEvidence, trigger);
        pushAudit(state, 'verification', state.verification.detail);
      } else {
        state.verification = { status: 'not_applicable', detail: 'this investigation type has no separate verification stage' };
        pushAudit(state, 'verification', state.verification.detail);
      }
    } else {
      state.execution = { attempted: false, success: null, detail: 'this investigation type has no execution stage — the decision itself is the outcome' };
      state.verification = { status: 'not_applicable', detail: 'no execution to verify' };
      pushAudit(state, 'execution', state.execution.detail);
      pushAudit(state, 'verification', state.verification.detail);
    }
  }

  state.completion = definition.isComplete(state);
  pushAudit(state, 'completion', state.completion.reason);

  state.learning = definition.learn(state);
  pushAudit(state, 'learning', state.learning.insight ?? 'no new learning this run');

  return state;
}

/**
 * Convenience wrapper for investigation types with no human-decision
 * latency (Trend Scan, Noise Triage, Decision Traceback, Integrity Audit,
 * Redundancy Reconciliation, Coverage Gap detection) — runs all eight
 * stages in one call. `pickDecision` is still a real function, not a
 * shortcut: for these types it typically just returns the single option
 * `decisionOptions` produced.
 */
export async function runInvestigationSync<TEvidence, TDecision>(
  definition: InvestigationDefinition<TEvidence, TDecision>,
  trigger: TriggerContext,
  pickDecision: (options: DecisionOption<TDecision>[], evidence: TEvidence) => TDecision | undefined
): Promise<InvestigationRunState<TEvidence, TDecision>> {
  const opened = await openInvestigation(definition, trigger);
  if (!opened.validation?.ok) return opened;
  const chosen = pickDecision(opened.decisionOptions ?? [], opened.evidence as TEvidence);
  return resolveInvestigation(opened, chosen);
}
