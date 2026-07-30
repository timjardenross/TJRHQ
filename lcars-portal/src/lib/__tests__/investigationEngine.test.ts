import { describe, it, expect } from 'vitest';
import {
  openInvestigation,
  resolveInvestigation,
  runInvestigationSync,
  type InvestigationDefinition,
  type TriggerContext,
} from '@/lib/investigationEngine';

interface FakeEvidence {
  value: number;
}
type FakeDecision = 'act' | 'defer';

function makeDefinition(overrides: Partial<InvestigationDefinition<FakeEvidence, FakeDecision>> = {}): InvestigationDefinition<FakeEvidence, FakeDecision> {
  return {
    type: 'fake-type',
    label: 'Fake Investigation',
    owner: 'engineering',
    triggerDescription: 'a test trigger',
    requiredEvidence: ['value'],
    evidenceSources: ['test-fixture'],
    validationRules: ['value must be non-negative'],
    possibleDecisionKinds: ['act', 'defer'],
    completionCriteria: 'a decision was recorded',
    auditOutputs: ['a completion record'],
    assembleEvidence: async () => ({ value: 5 }),
    validateEvidence: (evidence) => (evidence.value >= 0 ? { ok: true, problems: [] } : { ok: false, problems: ['negative value'] }),
    decisionOptions: () => [
      { id: 'act', label: 'Act', value: 'act', isReversible: true },
      { id: 'defer', label: 'Defer', value: 'defer', isReversible: true },
    ],
    isComplete: (state) => ({ complete: state.chosenDecision !== undefined, reason: state.chosenDecision ? 'decision recorded' : 'no decision yet' }),
    learn: () => ({ insight: null, category: 'none' }),
    ...overrides,
  };
}

function trigger(originRef = 'test-row-1'): TriggerContext {
  return { investigationType: 'fake-type', reason: 'unit test', originatedAt: '2026-01-01T00:00:00.000Z', originRef };
}

describe('openInvestigation', () => {
  it('runs trigger -> evidence_assembly -> evidence_validation -> decision_options in order', async () => {
    const state = await openInvestigation(makeDefinition(), trigger());
    expect(state.stagesReached).toEqual(['trigger', 'evidence_assembly', 'evidence_validation', 'decision_options']);
    expect(state.evidence).toEqual({ value: 5 });
    expect(state.validation?.ok).toBe(true);
    expect(state.decisionOptions?.map((o) => o.id)).toEqual(['act', 'defer']);
  });

  it('fails closed: invalid evidence stops before decision_options is ever reached', async () => {
    const def = makeDefinition({ assembleEvidence: async () => ({ value: -1 }) });
    const state = await openInvestigation(def, trigger());
    expect(state.stagesReached).toEqual(['trigger', 'evidence_assembly', 'evidence_validation']);
    expect(state.decisionOptions).toBeUndefined();
    expect(state.completion).toEqual({ complete: false, reason: 'blocked at evidence validation — no decision was ever offered' });
  });
});

describe('resolveInvestigation', () => {
  it('a type with execute+verify runs execution -> verification -> completion -> learning', async () => {
    const def = makeDefinition({
      execute: async (decision) => ({ attempted: true, success: decision === 'act', detail: `executed ${decision}` }),
      verify: async (execution) => ({ status: execution.success ? 'verified' : 'failed', detail: 'checked' }),
    });
    const opened = await openInvestigation(def, trigger());
    const resolved = await resolveInvestigation(opened, 'act');
    expect(resolved.stagesReached).toEqual([
      'trigger', 'evidence_assembly', 'evidence_validation', 'decision_options',
      'execution', 'verification', 'completion', 'learning',
    ]);
    expect(resolved.execution?.detail).toBe('executed act');
    expect(resolved.verification?.status).toBe('verified');
    expect(resolved.completion?.complete).toBe(true);
  });

  it('a type with NO execute/verify (per MSN-0353, e.g. Trend Scan) honestly records not_applicable instead of skipping the stage', async () => {
    const def = makeDefinition(); // no execute, no verify
    const opened = await openInvestigation(def, trigger());
    const resolved = await resolveInvestigation(opened, 'act');
    expect(resolved.execution).toEqual({ attempted: false, success: null, detail: 'this investigation type has no execution stage — the decision itself is the outcome' });
    expect(resolved.verification).toEqual({ status: 'not_applicable', detail: 'no execution to verify' });
    expect(resolved.stagesReached).toContain('execution');
    expect(resolved.stagesReached).toContain('verification');
  });

  it('undefined decision (hold) skips execution/verification but still reaches completion and learning', async () => {
    const def = makeDefinition({
      execute: async () => ({ attempted: true, success: true, detail: 'should not run' }),
    });
    const opened = await openInvestigation(def, trigger());
    const resolved = await resolveInvestigation(opened, undefined);
    expect(resolved.execution).toBeUndefined();
    expect(resolved.verification).toBeUndefined();
    expect(resolved.completion?.reason).toBe('no decision yet');
    expect(resolved.stagesReached).toEqual(['trigger', 'evidence_assembly', 'evidence_validation', 'decision_options', 'completion', 'learning']);
  });

  it('resolving an already-blocked (invalid) state is a no-op', async () => {
    const def = makeDefinition({ assembleEvidence: async () => ({ value: -1 }) });
    const opened = await openInvestigation(def, trigger());
    const resolved = await resolveInvestigation(opened, 'act');
    expect(resolved).toBe(opened);
  });
});

describe('runInvestigationSync', () => {
  it('runs all eight stages in one call for synchronous investigation types', async () => {
    const def = makeDefinition({
      execute: async () => ({ attempted: true, success: true, detail: 'ok' }),
      verify: async () => ({ status: 'verified', detail: 'ok' }),
    });
    const state = await runInvestigationSync(def, trigger(), (options) => options[0]?.value);
    expect(state.stagesReached).toEqual([
      'trigger', 'evidence_assembly', 'evidence_validation', 'decision_options',
      'execution', 'verification', 'completion', 'learning',
    ]);
  });
});

describe('the audit trail', () => {
  it('records one entry per stage actually reached, citing declared evidence sources', async () => {
    const state = await openInvestigation(makeDefinition(), trigger('row-42'));
    expect(state.audit[0]).toEqual({ stage: 'trigger', summary: 'unit test', evidenceRefs: ['row-42'] });
    expect(state.audit[1].stage).toBe('evidence_assembly');
    expect(state.audit[1].evidenceRefs).toEqual(['test-fixture']);
  });
});
