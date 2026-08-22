import { describe, it, expect } from 'vitest';
import { openInvestigation, resolveInvestigation, type TriggerContext } from '@/lib/investigationEngine';
import {
  integrityAuditDiagnose,
  integrityAuditVerify,
  redundancyReconciliation,
  type IntegrityAuditEvidence,
} from '@/lib/investigations/integrityAudit';

function trigger(overrides: Partial<TriggerContext> = {}): TriggerContext {
  return {
    investigationType: 'test',
    reason: 'unit test',
    originatedAt: '2026-07-09T00:00:00.000Z',
    ...overrides,
  };
}

// A realistically-simulated mismatch: a new nominator was added to
// interruptAssembly.ts's NOMINATORS array but no registry entry's text
// mentions it yet - the exact reverse-direction gap the real
// health-insights-risk-flags registry entry documents having found once
// already (MSN-0354, before that entry existed). All other fields are held
// at their real current-repo values (coverageValidation.ok stays true - the
// registry's own internal consistency is unaffected by a new nominator
// existing) so only the one fact under test changes.
const SIMULATED_ORPHAN_NOMINATOR_EVIDENCE: IntegrityAuditEvidence = {
  coverageValidation: { ok: true, problems: [] },
  liveNominatorNames: [
    'healthRiskNominator',
    'intelligenceEventNominator',
    'intelligenceBriefNominator',
    'missionNominator',
    'phantomNominator',
  ],
  registryClaimedNominatorNames: [
    'healthRiskNominator',
    'intelligenceEventNominator',
    'intelligenceBriefNominator',
    'missionNominator',
  ],
  claimedButMissingFromLive: [],
  liveButUndeclaredInRegistry: ['phantomNominator'],
  mismatchFound: true,
};

describe('integrityAuditDiagnose', () => {
  it('declares all nine required metadata fields with real, specific values', () => {
    expect(integrityAuditDiagnose.type).toBe('integrity-audit-diagnose');
    expect(integrityAuditDiagnose.owner).toBe('engineering');
    expect(integrityAuditDiagnose.label.length).toBeGreaterThan(0);
    expect(integrityAuditDiagnose.triggerDescription.length).toBeGreaterThan(0);
    expect(integrityAuditDiagnose.requiredEvidence.length).toBeGreaterThan(0);
    expect(integrityAuditDiagnose.evidenceSources).toEqual(
      expect.arrayContaining([
        expect.stringContaining('interruptCoverageRegistry.ts'),
        expect.stringContaining('interruptAssembly.ts'),
      ])
    );
    expect(integrityAuditDiagnose.validationRules.length).toBeGreaterThan(0);
    expect(integrityAuditDiagnose.possibleDecisionKinds).toEqual(['confirmed-defect', 'confirmed-sound']);
    expect(integrityAuditDiagnose.completionCriteria.length).toBeGreaterThan(0);
    expect(integrityAuditDiagnose.auditOutputs.length).toBeGreaterThan(0);
    // Per MSN-0353 §1.1 the actual fix is out-of-band engineering work.
    expect(integrityAuditDiagnose.execute).toBeUndefined();
    expect(integrityAuditDiagnose.verify).toBeUndefined();
  });

  it('all-sound path: against the real live registry + real live NOMINATORS wiring, finds no mismatch and confirms sound', async () => {
    const opened = await openInvestigation(integrityAuditDiagnose, trigger({ originRef: 'full-registry-sweep' }));
    expect(opened.validation?.ok).toBe(true);
    expect(opened.evidence?.mismatchFound).toBe(false);
    // Real, current-repo fact: every nominator wired into interruptAssembly.ts's
    // NOMINATORS array is named in the registry's own declared text, and vice
    // versa (interruptCoverageRegistry.test.ts pins the same coverage set).
    expect(opened.evidence?.liveNominatorNames.sort()).toEqual(
      [
        'healthRiskNominator',
        'intelligenceBriefNominator',
        'intelligenceEventNominator',
        'missionNominator',
        'recoveryEscalationNominator',
        'recoveryPostureNominator',
        'painTrendNominator',
        'deliveryBlockedNominator',
        'failedDispatchNominator',
        'engineeringReviewNominator',
        'capturedMissionNominator',
      ].sort()
    );
    expect(opened.evidence?.claimedButMissingFromLive).toEqual([]);
    expect(opened.evidence?.liveButUndeclaredInRegistry).toEqual([]);
    expect(opened.decisionOptions).toEqual([
      {
        id: 'confirmed-sound',
        label: "Confirmed sound - the registry's declared coverage and the live nominator wiring agree",
        value: 'confirmed-sound',
        isReversible: true,
      },
    ]);

    const resolved = await resolveInvestigation(opened, 'confirmed-sound');
    expect(resolved.completion).toEqual({ complete: true, reason: 'resolved as "confirmed-sound"' });
    expect(resolved.learning).toEqual({ insight: null, category: 'none' });
    // No execute/verify stage exists on this type - the engine records that honestly.
    expect(resolved.execution?.detail).toBe('this investigation type has no execution stage — the decision itself is the outcome');
    expect(resolved.verification?.status).toBe('not_applicable');
  });

  it('mismatch path (realistically simulated): detects a nominator with no registry coverage and offers confirmed-defect', async () => {
    const simulated: typeof integrityAuditDiagnose = {
      ...integrityAuditDiagnose,
      assembleEvidence: async () => SIMULATED_ORPHAN_NOMINATOR_EVIDENCE,
    };
    const opened = await openInvestigation(simulated, trigger({ originRef: 'phantomNominator-review' }));
    expect(opened.validation?.ok).toBe(true);
    expect(opened.decisionOptions?.map((o) => o.id)).toEqual(['confirmed-defect', 'confirmed-sound']);
    expect(opened.decisionOptions?.[0].label).toContain('phantomNominator');

    const resolved = await resolveInvestigation(opened, 'confirmed-defect');
    expect(resolved.completion).toEqual({ complete: true, reason: 'resolved as "confirmed-defect"' });
    expect(resolved.learning?.insight).toContain('phantomNominator');
    // Per the definition's own learn(): the registry's own internal
    // consistency check (validateCoverage()) still passing means this
    // mismatch is a process-gap (a real evaluator existing with no
    // registry-side documentation of it) rather than a coverage-gap (which
    // this definition reserves for validateCoverage() itself failing).
    expect(resolved.learning?.category).toBe('process-gap');
  });

  it('a reviewer can judge a detected mismatch not to be a real defect (e.g. an in-flight rename) without emitting a learning insight', async () => {
    const simulated: typeof integrityAuditDiagnose = {
      ...integrityAuditDiagnose,
      assembleEvidence: async () => SIMULATED_ORPHAN_NOMINATOR_EVIDENCE,
    };
    const opened = await openInvestigation(simulated, trigger());
    const resolved = await resolveInvestigation(opened, 'confirmed-sound');
    expect(resolved.completion?.complete).toBe(true);
    expect(resolved.learning).toEqual({ insight: null, category: 'none' });
  });

  it('blocks before a decision is ever offered if the registry has no interrupt-capable evaluators to compare (fails closed)', async () => {
    const emptyLive: typeof integrityAuditDiagnose = {
      ...integrityAuditDiagnose,
      assembleEvidence: async () => ({ ...SIMULATED_ORPHAN_NOMINATOR_EVIDENCE, liveNominatorNames: [] }),
    };
    const opened = await openInvestigation(emptyLive, trigger());
    expect(opened.validation?.ok).toBe(false);
    expect(opened.validation?.problems).toEqual(
      expect.arrayContaining(['lib/interruptAssembly.ts NOMINATORS resolved to zero named functions - live-side comparison is impossible'])
    );
    expect(opened.decisionOptions).toBeUndefined();
  });
});

describe('integrityAuditVerify', () => {
  it('declares all nine required metadata fields with real, specific values', () => {
    expect(integrityAuditVerify.type).toBe('integrity-audit-verify');
    expect(integrityAuditVerify.owner).toBe('engineering');
    expect(integrityAuditVerify.label.length).toBeGreaterThan(0);
    expect(integrityAuditVerify.triggerDescription.length).toBeGreaterThan(0);
    expect(integrityAuditVerify.requiredEvidence.length).toBeGreaterThan(0);
    expect(integrityAuditVerify.evidenceSources.length).toBeGreaterThan(0);
    expect(integrityAuditVerify.validationRules.length).toBeGreaterThan(0);
    expect(integrityAuditVerify.possibleDecisionKinds).toEqual(['confirmed-sound', 'reopen-as-diagnose']);
    expect(integrityAuditVerify.completionCriteria.length).toBeGreaterThan(0);
    expect(integrityAuditVerify.auditOutputs.length).toBeGreaterThan(0);
    expect(integrityAuditVerify.execute).toBeUndefined();
    expect(integrityAuditVerify.verify).toBeUndefined();
  });

  it('re-confirms sound (journey #17 shape) against the real live registry, framed around trigger.originRef', async () => {
    const opened = await openInvestigation(
      integrityAuditVerify,
      trigger({ reason: 'confirming MSN-0354 mission-nominator wiring still holds', originRef: 'MSN-0354' })
    );
    expect(opened.evidence?.reCheckOf).toBe('MSN-0354');
    expect(opened.evidence?.mismatchFound).toBe(false);
    expect(opened.decisionOptions).toEqual([
      {
        id: 'confirmed-sound',
        label: 'Confirmed sound - the prior fix still holds under the current live comparison',
        value: 'confirmed-sound',
        isReversible: true,
      },
    ]);

    const resolved = await resolveInvestigation(opened, 'confirmed-sound');
    expect(resolved.completion).toEqual({ complete: true, reason: 'resolved as "confirmed-sound"' });
    expect(resolved.learning).toEqual({ insight: null, category: 'none' });
  });

  it('mismatch path (realistically simulated): a re-check finds the prior fix incomplete and reopens as diagnose', async () => {
    const simulated: typeof integrityAuditVerify = {
      ...integrityAuditVerify,
      assembleEvidence: async () => ({ ...SIMULATED_ORPHAN_NOMINATOR_EVIDENCE, reCheckOf: 'MSN-0354' }),
    };
    const opened = await openInvestigation(simulated, trigger({ originRef: 'MSN-0354' }));
    expect(opened.decisionOptions?.map((o) => o.id)).toEqual(['reopen-as-diagnose', 'confirmed-sound']);

    const resolved = await resolveInvestigation(opened, 'reopen-as-diagnose');
    expect(resolved.completion).toEqual({ complete: true, reason: 'resolved as "reopen-as-diagnose"' });
    expect(resolved.learning?.insight).toContain('MSN-0354');
    expect(resolved.learning?.insight).toContain('phantomNominator');
    expect(resolved.learning?.category).toBe('process-gap');
  });

  it('a run with no chosen decision yet is honestly incomplete', async () => {
    const opened = await openInvestigation(integrityAuditVerify, trigger({ originRef: 'MSN-0354' }));
    const resolved = await resolveInvestigation(opened, undefined);
    expect(resolved.completion).toEqual({
      complete: false,
      reason: 'awaiting a decision - re-check evidence was assembled but nothing has been decided yet',
    });
  });
});

describe('redundancyReconciliation', () => {
  it('declares all nine required metadata fields with real, specific values', () => {
    expect(redundancyReconciliation.type).toBe('redundancy-reconciliation');
    expect(redundancyReconciliation.owner).toBe('engineering');
    expect(redundancyReconciliation.label.length).toBeGreaterThan(0);
    expect(redundancyReconciliation.triggerDescription.length).toBeGreaterThan(0);
    expect(redundancyReconciliation.requiredEvidence.length).toBeGreaterThan(0);
    expect(redundancyReconciliation.evidenceSources.length).toBeGreaterThan(0);
    expect(redundancyReconciliation.validationRules.length).toBeGreaterThan(0);
    expect(redundancyReconciliation.possibleDecisionKinds).toEqual(['merge', 'keep-separate-relabel', 'no-redundancy-found']);
    expect(redundancyReconciliation.completionCriteria.length).toBeGreaterThan(0);
    expect(redundancyReconciliation.auditOutputs.length).toBeGreaterThan(0);
    expect(redundancyReconciliation.execute).toBeUndefined();
    expect(redundancyReconciliation.verify).toBeUndefined();
  });

  it('finds a real redundancy candidate: three human-systems capabilities independently read overlapping evidence and could disagree (journey #3 shape)', async () => {
    const opened = await openInvestigation(redundancyReconciliation, trigger({ reason: 'periodic engineering review' }));
    expect(opened.evidence?.scope).toBe('full-registry');
    expect(opened.evidence?.redundancyFound).toBe(true);

    const pairs = opened.evidence?.candidatePairs ?? [];
    const pairKeys = pairs.map((p) => `${p.a}<->${p.b}`);
    // Real, current-repo fact: human-systems-redflag, human-systems-recovery-debt,
    // and medical-emotional-load all independently read human_systems_daily /
    // capacity_checkins / regulation_state and could produce disagreeing
    // interrupts about the same underlying daily record.
    expect(pairKeys).toEqual(
      expect.arrayContaining([
        'human-systems-redflag<->human-systems-recovery-debt',
        'human-systems-redflag<->medical-emotional-load',
        'human-systems-recovery-debt<->medical-emotional-load',
      ])
    );
    const redflagVsDebt = pairs.find((p) => p.a === 'human-systems-redflag' && p.b === 'human-systems-recovery-debt');
    expect(redflagVsDebt?.sharedEvidenceTokens).toEqual(['human_systems_daily']);

    expect(opened.decisionOptions?.map((o) => o.id)).toEqual(['merge', 'keep-separate-relabel']);

    // These three are genuinely different conditions (a red-flag text match,
    // a 3-day sustained-trend threshold, and a 3-of-7 worst-of-day count) -
    // the correct real-world call is to relabel, not merge.
    const resolved = await resolveInvestigation(opened, 'keep-separate-relabel');
    expect(resolved.completion).toEqual({ complete: true, reason: 'resolved as "keep-separate-relabel"' });
    expect(resolved.learning?.category).toBe('process-gap');
    expect(resolved.learning?.insight).toContain('human-systems-redflag');
  });

  it('all-sound path: scoped to a capability with no overlapping evidence sources, finds no redundancy', async () => {
    const opened = await openInvestigation(
      redundancyReconciliation,
      trigger({ reason: 'scoped review after adding health-insights-risk-flags', originRef: 'health-insights-risk-flags' })
    );
    expect(opened.evidence?.scope).toBe('health-insights-risk-flags');
    expect(opened.evidence?.candidatePairs).toEqual([]);
    expect(opened.evidence?.redundancyFound).toBe(false);
    expect(opened.decisionOptions).toEqual([
      {
        id: 'no-redundancy-found',
        label: 'No overlapping evidence sources found in scope (health-insights-risk-flags)',
        value: 'no-redundancy-found',
        isReversible: true,
      },
    ]);

    const resolved = await resolveInvestigation(opened, 'no-redundancy-found');
    expect(resolved.completion).toEqual({ complete: true, reason: 'resolved as "no-redundancy-found"' });
    expect(resolved.learning).toEqual({ insight: null, category: 'none' });
  });

  it('blocks before a decision is offered when scoped to a capability id that does not exist in the registry (fails closed)', async () => {
    const opened = await openInvestigation(redundancyReconciliation, trigger({ originRef: 'not-a-real-capability' }));
    expect(opened.validation?.ok).toBe(false);
    expect(opened.validation?.problems).toEqual(
      expect.arrayContaining(['scoped capability "not-a-real-capability" does not exist in the registry'])
    );
    expect(opened.decisionOptions).toBeUndefined();
  });
});
