import { describe, it, expect, vi, beforeEach } from 'vitest';
import { openInvestigation, resolveInvestigation, type TriggerContext } from '@/lib/investigationEngine';

// ── Mocks ────────────────────────────────────────────────────────────────
// downstreamVerificationGap reads Supabase via lib/supabase-service-role.ts's
// createSupabaseServiceRoleClient() (the same server-only client-creation
// pattern already used by lib/ai-actions.ts's supabaseAdmin()). Mocking at
// that boundary lets each test control exactly what build_request_inbox /
// missions / commander_decisions return, without any network access - same
// approach as __tests__/aiActions.test.ts and __tests__/interruptAssembly.test.ts.

const createServiceRoleClientMock = vi.fn();
vi.mock('@/lib/supabase-service-role', () => ({
  createSupabaseServiceRoleClient: () => createServiceRoleClientMock(),
}));

import {
  upstreamCoverageGap,
  downstreamVerificationGap,
  classifyLegacyShape,
  verifyLegacyCreateMission,
  verifyGovernedAction,
  verifyRequest,
  type UpstreamCoverageEvidence,
} from '@/lib/investigations/coverageGaps';

// ── Fake Supabase query builder ─────────────────────────────────────────
// Supports the .select().eq().limit() chain shape used by coverageGaps.ts,
// applying accumulated .eq() filters at resolution time - close enough to
// the real PostgREST builder for these tests without depending on the
// network. A table entry can be a plain row array or a function (so tests
// can mutate state between an initial check and a later re-check, e.g. to
// simulate a mission being created between the first read and `execute`'s
// re-run) or a rejected Promise (to simulate a fetch failure).

type Row = Record<string, unknown>;
type TableSource = Row[] | (() => Row[]) | Promise<never>;

function queryable(source: TableSource) {
  const filters: Array<(rows: Row[]) => Row[]> = [];
  const obj: Record<string, unknown> = {
    select: () => obj,
    eq: (col: string, val: unknown) => {
      filters.push((rows) => rows.filter((r) => r[col] === val));
      return obj;
    },
    limit: () => obj,
    then: (resolve: (v: unknown) => void, reject: (e: unknown) => void) => {
      if (source instanceof Promise) return source.then(resolve, reject);
      let rows = typeof source === 'function' ? source() : source;
      for (const f of filters) rows = f(rows);
      return Promise.resolve({ data: rows, error: null }).then(resolve, reject);
    },
  };
  return obj;
}

function fakeSupabase(byTable: Record<string, TableSource>) {
  return { from: (table: string) => queryable(byTable[table] ?? []) } as never;
}

function trigger(originRef?: string): TriggerContext {
  return { investigationType: 'test', reason: 'unit test', originatedAt: '2026-07-09T00:00:00.000Z', originRef };
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ═══════════════════════════════════════════════════════════════════════
// Upstream Coverage Gap
// ═══════════════════════════════════════════════════════════════════════

describe('upstreamCoverageGap', () => {
  it('declares all nine required metadata fields with real, specific values', () => {
    expect(upstreamCoverageGap.type).toBe('upstream-coverage-gap');
    expect(upstreamCoverageGap.owner).toBe('engineering');
    for (const field of [
      'label', 'triggerDescription', 'completionCriteria',
    ] as const) {
      expect(typeof upstreamCoverageGap[field]).toBe('string');
      expect((upstreamCoverageGap[field] as string).length).toBeGreaterThan(20);
    }
    for (const field of ['requiredEvidence', 'evidenceSources', 'validationRules', 'possibleDecisionKinds', 'auditOutputs'] as const) {
      expect(Array.isArray(upstreamCoverageGap[field])).toBe(true);
      expect((upstreamCoverageGap[field] as string[]).length).toBeGreaterThan(0);
    }
  });

  // Journey #22 regression, against REAL live production code (no mocks):
  // the real P0 mission that sat invisible to Home for 17 days was fixed by
  // MSN-0354 wiring missionNominator into NOMINATORS and adding the
  // 'missions' registry entry. This proves that fix - and the equivalent
  // MSN-0355 fix for journey #15 - both still hold today.
  it('journey #22/#15 regression: the real, live registry and NOMINATORS wiring agree today (no upstream coverage gap)', async () => {
    const opened = await openInvestigation(upstreamCoverageGap, trigger());
    expect(opened.validation?.ok).toBe(true);
    const evidence = opened.evidence as UpstreamCoverageEvidence;
    expect(evidence.mismatchFound).toBe(false);
    expect(evidence.liveButUndeclaredInRegistry).toEqual([]);
    expect(evidence.claimedButMissingFromLive).toEqual([]);
    // The real fix this regression guards: missionNominator is both live
    // and declared, closing journey #22.
    expect(evidence.liveNominatorNames).toContain('missionNominator');
    expect(opened.decisionOptions?.map((o) => o.id)).toEqual(['registry-current-no-gap']);

    const resolved = await resolveInvestigation(opened, 'registry-current-no-gap');
    expect(resolved.completion?.complete).toBe(true);
    expect(resolved.learning).toEqual({ insight: null, category: 'none' });
    // No execute/verify stage for this type (documented in coverageGaps.ts).
    expect(resolved.execution?.detail).toContain('no execution stage');
  });

  // Reproduces the PRE-MSN-0354 shape of journey #22 synthetically (a live
  // nominator with no registry entry claiming it) to prove the check logic
  // itself - not just today's already-fixed data - would actually catch a
  // regression if this class of gap reappeared.
  it('would flag a re-introduced gap: a live nominator with no registry entry claiming it offers only "wire-missing-nominator", never a "leave it" option', () => {
    const preFixShapeEvidence: UpstreamCoverageEvidence = {
      reCheckOf: undefined,
      coverageValidation: { ok: true, problems: [] },
      liveNominatorNames: ['healthRiskNominator', 'intelligenceEventNominator', 'intelligenceBriefNominator', 'missionNominator'],
      registryClaimedNominatorNames: ['healthRiskNominator', 'intelligenceEventNominator', 'intelligenceBriefNominator'],
      claimedButMissingFromLive: [],
      liveButUndeclaredInRegistry: ['missionNominator'],
      mismatchFound: true,
    };
    const options = upstreamCoverageGap.decisionOptions(preFixShapeEvidence, trigger());
    expect(options).toHaveLength(1);
    expect(options[0].id).toBe('wire-missing-nominator');
    expect(options[0].label).toContain('missionNominator');

    const learning = upstreamCoverageGap.learn({
      definition: upstreamCoverageGap,
      trigger: trigger(),
      evidence: preFixShapeEvidence,
      chosenDecision: 'wire-missing-nominator',
      audit: [],
      stagesReached: [],
    });
    expect(learning.category).toBe('coverage-gap');
    expect(learning.insight).toContain('missionNominator');
  });

  it('a registry entry claiming a nominator that does not actually exist live is also flagged (the reverse mismatch direction)', () => {
    const staleRegistryClaim: UpstreamCoverageEvidence = {
      reCheckOf: undefined,
      coverageValidation: { ok: true, problems: [] },
      liveNominatorNames: ['healthRiskNominator'],
      registryClaimedNominatorNames: ['healthRiskNominator', 'retiredNominator'],
      claimedButMissingFromLive: ['retiredNominator'],
      liveButUndeclaredInRegistry: [],
      mismatchFound: true,
    };
    const options = upstreamCoverageGap.decisionOptions(staleRegistryClaim, trigger());
    expect(options.map((o) => o.id)).toEqual(['wire-missing-nominator']);
    expect(options[0].label).toContain('retiredNominator');
  });

  it('validateEvidence fails closed when the live NOMINATORS array is empty', () => {
    const emptyEvidence: UpstreamCoverageEvidence = {
      reCheckOf: undefined,
      coverageValidation: { ok: true, problems: [] },
      liveNominatorNames: [],
      registryClaimedNominatorNames: [],
      claimedButMissingFromLive: [],
      liveButUndeclaredInRegistry: [],
      mismatchFound: false,
    };
    const result = upstreamCoverageGap.validateEvidence(emptyEvidence, trigger());
    expect(result.ok).toBe(false);
    expect(result.problems.join(' ')).toContain('NOMINATORS');
  });
});

// ═══════════════════════════════════════════════════════════════════════
// Downstream Verification Gap
// ═══════════════════════════════════════════════════════════════════════

// Frozen fixtures translated directly from
// core/coordination/tests/test_build_request_verifier.py, so this suite
// doubles as the same regression guard the Python tests are for the same
// real rows, confirmed live in Supabase (project cjvrpjwewsrumnbdydgg).

const CA83A08B_ROW = {
  id: 'ca83a08b-cab5-4adf-8e33-f68713e31aa5',
  request_id: 'BREQ-20260618-111042-spawn-xo-and-chief-engineer-authority-and-person',
  source: 'telegram',
  requested_by: '@tjr1986',
  title: 'Spawn XO and Chief Engineer Authority and Persona System Mission',
  summary:
    'Adopt the XO and Chief Engineer persona charters as ship doctrine by creating a new mission (working title USS-TJR-MSN-0066) that defines authority tiers, audit rules, rollback requirements, and safe-action boundaries.',
  rationale:
    "MSN-0065's read-only/PENDING_TRIAGE/approve-tap guardrails intentionally prevent action orchestration, reducing the Telegram operator to a passive summarizer.",
  status: 'approved',
  action_type: null,
  action_payload: null,
  action_result: null,
  record_path: null,
  created_at: '2026-06-18T09:10:42.911195+00:00',
};

const DEAD_CODE_AUDIT_ROW = {
  id: '9c51fecc-799e-451c-beed-e76696154b03',
  request_id: 'BREQ-20260618-100438-dead-code-audit-and-deprecation-plan-for-mission',
  source: 'telegram',
  requested_by: '@tjr1986',
  title: 'Dead-Code Audit and Deprecation Plan for Mission Registry and Runtime ID Minting',
  summary:
    'Perform a read-only grep-and-classify pass across the codebase to identify dead or deprecated code, including references to deprecated registry files (Missions/Mission-Index.md), the M-YYYYMMDD-HHMMSS runtime ID minting path, and old alias-resolution fallbacks.',
  rationale: 'Deprecated dual registries and identity schemes create drift, risk collisions with the canonical registry.',
  status: 'approved',
  action_type: null,
  action_payload: null,
  action_result: null,
  record_path: null,
  created_at: '2026-06-18T08:04:38.782892+00:00',
};

const REAL_MISSIONS_SNAPSHOT = [
  { mission_id: 'USS-TJR-MSN-0058', title: 'Number One & XO Capability Assessment', status: 'Closed' },
  { mission_id: 'USS-TJR-MSN-0064', title: 'Runtime Mission-ID Repoint to Canonical Mission Control IDs', status: 'Designed' },
];

function governedRow(overrides: Partial<Row> = {}) {
  return {
    id: 'gov-1',
    request_id: 'AI-CREATE_MISSION-20260701-ABCDEF',
    source: 'lcars-ai-console-proposed',
    title: 'Proposed Mission',
    summary: null,
    rationale: null,
    requested_by: null,
    status: 'approved',
    action_type: 'create_mission',
    action_payload: { title: 'Proposed Mission' },
    action_result: { success: true, detail: 'Mission USS-TJR-MSN-0200 registered', executed_at: '2026-07-01T00:00:00Z' },
    record_path: '/missions/USS-TJR-MSN-0200',
    created_at: '2026-07-01T00:00:00Z',
    ...overrides,
  };
}

// ── Pure-function parity tests (direct port of the Python unit tests) ────

describe('classifyLegacyShape (port of build_request_verifier.classify_legacy_shape)', () => {
  it('flags the real defect row as mission-creation shaped', () => {
    const [shape, evidence] = classifyLegacyShape(CA83A08B_ROW as never);
    expect(shape).toBe('create_mission');
    expect(evidence.toLowerCase()).toContain('mission');
  });

  it('does not false-positive on unrelated mission/create mentions (the dead-code-audit row)', () => {
    const [shape] = classifyLegacyShape(DEAD_CODE_AUDIT_ROW as never);
    expect(shape).toBe('other');
  });
});

describe('verifyLegacyCreateMission (port of verify_legacy_create_mission)', () => {
  it('journey #9 regression: the real defect row is not_found_downstream against real missions data', () => {
    const [status, evidence] = verifyLegacyCreateMission(CA83A08B_ROW as never, REAL_MISSIONS_SNAPSHOT);
    expect(status).toBe('not_found_downstream');
    expect(evidence).toContain('0066');
    expect(evidence).toContain('cannot distinguish never-attempted from silently-failed');
  });

  it('verifies when the working-title id now matches a real mission', () => {
    const missions = [...REAL_MISSIONS_SNAPSHOT, { mission_id: 'USS-TJR-MSN-0066', title: 'XO and CE Authority', status: 'Idea' }];
    const [status, evidence] = verifyLegacyCreateMission(CA83A08B_ROW as never, missions);
    expect(status).toBe('verified');
    expect(evidence).toContain('USS-TJR-MSN-0066');
  });

  it('never returns failed for a legacy row - no attempt record exists to distinguish never-attempted from silently-failed', () => {
    const [status] = verifyLegacyCreateMission(CA83A08B_ROW as never, []);
    expect(status).not.toBe('failed');
    expect(status).toBe('not_found_downstream');
  });
});

describe('verifyGovernedAction (port of verify_governed_action)', () => {
  it('create_mission is verified when the missions row exists', () => {
    const [status] = verifyGovernedAction(governedRow() as never, [{ mission_id: 'USS-TJR-MSN-0200', title: 'Proposed Mission', status: 'Idea' }], []);
    expect(status).toBe('verified');
  });

  it('create_mission is a mismatch when action_result claims success but no row exists', () => {
    const [status, evidence] = verifyGovernedAction(governedRow() as never, [], []);
    expect(status).toBe('mismatch');
    expect(evidence).toContain('claims success');
  });

  it('distinguishes failed from not_attempted', () => {
    const failed = verifyGovernedAction(governedRow({ action_result: { success: false, detail: 'duplicate key' } }) as never, [], []);
    expect(failed[0]).toBe('failed');
    const notAttempted = verifyGovernedAction(governedRow({ action_result: null }) as never, [], []);
    expect(notAttempted[0]).toBe('not_attempted');
  });

  it('create_handoff rows are always self-fulfilling', () => {
    const [status, evidence] = verifyGovernedAction({ action_type: 'create_handoff', action_result: null } as never, [], []);
    expect(status).toBe('verified');
    expect(evidence).toContain('self-fulfilling');
  });
});

describe('verifyRequest (port of verify_request)', () => {
  it('end-to-end flags the real journey #9 defect row', () => {
    const result = verifyRequest(CA83A08B_ROW as never, REAL_MISSIONS_SNAPSHOT, []);
    expect(result.verification).toBe('not_found_downstream');
    expect(result.id).toBe('ca83a08b-cab5-4adf-8e33-f68713e31aa5');
  });

  it('marks the unrelated dead-code-audit row out_of_scope, not flagged', () => {
    const result = verifyRequest(DEAD_CODE_AUDIT_ROW as never, REAL_MISSIONS_SNAPSHOT, []);
    expect(result.verification).toBe('out_of_scope');
  });
});

// ── Full investigation-engine runs (openInvestigation / resolveInvestigation) ──

describe('downstreamVerificationGap', () => {
  it('declares all nine required metadata fields with real, specific values', () => {
    expect(downstreamVerificationGap.type).toBe('downstream-verification-gap');
    expect(downstreamVerificationGap.owner).toBe('shared');
    for (const field of ['label', 'triggerDescription', 'completionCriteria'] as const) {
      expect(typeof downstreamVerificationGap[field]).toBe('string');
      expect((downstreamVerificationGap[field] as string).length).toBeGreaterThan(20);
    }
    for (const field of ['requiredEvidence', 'evidenceSources', 'validationRules', 'possibleDecisionKinds', 'auditOutputs'] as const) {
      expect(Array.isArray(downstreamVerificationGap[field])).toBe(true);
      expect((downstreamVerificationGap[field] as string[]).length).toBeGreaterThan(0);
    }
    expect(downstreamVerificationGap.possibleDecisionKinds).toEqual(['materialized', 'not-found-downstream', 'mismatch']);
  });

  it('journey #9 regression: systemic audit over the real defect row (no mocks-of-logic, real port) resolves as not-found-downstream and records a process-gap learning', async () => {
    createServiceRoleClientMock.mockReturnValue(
      fakeSupabase({
        build_request_inbox: [CA83A08B_ROW],
        missions: REAL_MISSIONS_SNAPSHOT,
        commander_decisions: [],
      })
    );
    const opened = await openInvestigation(downstreamVerificationGap, trigger());
    expect(opened.validation?.ok).toBe(true);
    expect(opened.evidence?.problemRows).toHaveLength(1);
    expect(opened.evidence?.problemRows[0].verification).toBe('not_found_downstream');
    expect(opened.decisionOptions?.map((o) => o.id)).toEqual(['not-found-downstream']);

    const decision = opened.decisionOptions![0].value;
    const resolved = await resolveInvestigation(opened, decision);
    expect(resolved.completion?.complete).toBe(true);
    expect(resolved.learning?.category).toBe('process-gap');
    expect(resolved.learning?.insight).toContain('ca83a08b');
    // execute re-runs the check against the same (unchanged) fixture - verdict is stable.
    expect(resolved.execution?.success).toBe(true);
    expect(resolved.verification?.status).toBe('verified');
  });

  it('systemic audit with an all-clear inbox offers only "materialized"', async () => {
    createServiceRoleClientMock.mockReturnValue(
      fakeSupabase({ build_request_inbox: [governedRow()], missions: [{ mission_id: 'USS-TJR-MSN-0200', title: 'Proposed Mission', status: 'Idea' }], commander_decisions: [] })
    );
    const opened = await openInvestigation(downstreamVerificationGap, trigger());
    expect(opened.evidence?.problemRows).toEqual([]);
    expect(opened.decisionOptions?.map((o) => o.id)).toEqual(['materialized']);
    const resolved = await resolveInvestigation(opened, opened.decisionOptions![0].value);
    expect(resolved.learning).toEqual({ insight: null, category: 'none' });
  });

  it('flags a governed mismatch (claims success but no matching mission row)', async () => {
    createServiceRoleClientMock.mockReturnValue(
      fakeSupabase({ build_request_inbox: [governedRow({ id: 'mismatch-1' })], missions: [], commander_decisions: [] })
    );
    const opened = await openInvestigation(downstreamVerificationGap, trigger());
    expect(opened.decisionOptions?.map((o) => o.id)).toEqual(['mismatch']);
  });

  it('spot-check mode: trigger.originRef scopes the check to a single row and offers exactly one decision option', async () => {
    createServiceRoleClientMock.mockReturnValue(
      fakeSupabase({ build_request_inbox: [CA83A08B_ROW, DEAD_CODE_AUDIT_ROW], missions: REAL_MISSIONS_SNAPSHOT, commander_decisions: [] })
    );
    const opened = await openInvestigation(downstreamVerificationGap, trigger(CA83A08B_ROW.id));
    expect(opened.evidence?.scope).toBe('spot-check');
    expect(opened.evidence?.checkedRows).toHaveLength(1);
    expect(opened.decisionOptions).toHaveLength(1);
    expect(opened.decisionOptions?.[0].id).toBe('not-found-downstream');
  });

  it('spot-check on an out-of-scope row (approved but not mission-creation-shaped) completes with nothing to decide, per the same scoping build_request_verifier.py declares', async () => {
    createServiceRoleClientMock.mockReturnValue(
      fakeSupabase({ build_request_inbox: [DEAD_CODE_AUDIT_ROW], missions: REAL_MISSIONS_SNAPSHOT, commander_decisions: [] })
    );
    const opened = await openInvestigation(downstreamVerificationGap, trigger(DEAD_CODE_AUDIT_ROW.id));
    expect(opened.decisionOptions).toEqual([]);
    const resolved = await resolveInvestigation(opened, undefined);
    expect(resolved.completion?.complete).toBe(true);
    expect(resolved.completion?.reason).toContain('out of this checker\'s scope');
  });

  it('spot-check for a nonexistent/unapproved row fails closed at evidence_validation', async () => {
    createServiceRoleClientMock.mockReturnValue(fakeSupabase({ build_request_inbox: [], missions: [], commander_decisions: [] }));
    const opened = await openInvestigation(downstreamVerificationGap, trigger('no-such-row'));
    expect(opened.validation?.ok).toBe(false);
    expect(opened.decisionOptions).toBeUndefined();
  });

  it('fails closed on a fetch error rather than reading an empty result as all-clear', async () => {
    createServiceRoleClientMock.mockReturnValue(
      fakeSupabase({ build_request_inbox: Promise.reject(new Error('supabase down')), missions: [], commander_decisions: [] })
    );
    const opened = await openInvestigation(downstreamVerificationGap, trigger());
    expect(opened.validation?.ok).toBe(false);
    expect(opened.validation?.problems.join(' ')).toContain('supabase down');
  });

  it('execute detects when the verdict has changed since the decision was recorded, and verify catches instability', async () => {
    // Simulate a Captain spot-check: at decision time the mission doesn't
    // exist yet (not_found_downstream); by the time `execute` re-runs
    // moments later, the mission has been created - the exact "did my
    // approval land [since I last checked]" question this spot-check exists
    // to answer.
    const missions = [...REAL_MISSIONS_SNAPSHOT];
    createServiceRoleClientMock.mockImplementation(() =>
      fakeSupabase({ build_request_inbox: [CA83A08B_ROW], missions: () => missions, commander_decisions: [] })
    );
    const opened = await openInvestigation(downstreamVerificationGap, trigger(CA83A08B_ROW.id));
    expect(opened.decisionOptions?.[0].id).toBe('not-found-downstream');
    const decision = opened.decisionOptions![0].value;

    // The mission lands after the decision was recorded but before execute runs.
    missions.push({ mission_id: 'USS-TJR-MSN-0066', title: 'XO and CE Authority', status: 'Idea' });

    const resolved = await resolveInvestigation(opened, decision);
    expect(resolved.execution?.success).toBe(false);
    expect(resolved.execution?.detail).toContain('verdict has changed');
    // verify re-runs twice more against the now-stable (mission present) state.
    expect(resolved.verification?.status).toBe('verified');
  });
});
