import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Mocks ────────────────────────────────────────────────────────────────
// Follows the boundary-mocking pattern already used in aiActions.test.ts
// (mock @supabase/supabase-js's createClient so the REAL createMission/
// logDecision/supabaseAdmin bodies run against a fake table) and
// decide.test.ts (mock @/lib/engineering-queue's list/mutate functions
// directly via importActual + override). Two small in-memory "tables" are
// shared across both mocks so a status flip made through one path (e.g.
// Queue Triage archiving a row via setQueueItemStatus) is visible to the
// other path (Queue Resolution reading the same row via supabaseAdmin) -
// exactly as they would be, reading/writing the same real
// build_request_inbox table in production.

let buildRequestRowsById: Record<string, Record<string, unknown>> = {};
let missionsById: Record<string, Record<string, unknown>> = {};
let decisionsById: Record<string, Record<string, unknown>> = {};
let queueState: import('@/lib/engineering-queue').QueueItem[] = [];

function applyStatusUpdate(id: string, status: 'approved' | 'rejected'): void {
  if (buildRequestRowsById[id]) buildRequestRowsById[id].status = status;
  const qi = queueState.find((i) => i.id === id);
  if (qi) {
    qi.rawStatus = status;
    qi.lifecycle = status === 'approved' ? 'assigned' : 'rejected';
  }
}

function maybeSingleImpl(table: string, value: string): { data: Record<string, unknown> | null; error: null } {
  if (table === 'build_request_inbox') return { data: buildRequestRowsById[value] ?? null, error: null };
  if (table === 'missions') return { data: missionsById[value] ?? null, error: null };
  if (table === 'commander_decisions') return { data: decisionsById[value] ?? null, error: null };
  return { data: null, error: null };
}

/** Backs updateBuildRequestRow() in queueGovernance.ts - the row-level
 * write that mirrors approve-action/route.ts's own status/record_path/
 * action_result update, which is what lets Queue Resolution's verify()
 * genuinely reuse coverageGaps.ts's verifyGovernedAction() against a
 * freshly re-read row. */
function applyRowPatch(table: string, id: string, patch: Record<string, unknown>): void {
  if (table === 'build_request_inbox' && buildRequestRowsById[id]) {
    Object.assign(buildRequestRowsById[id], patch);
  }
}

const fromCalls: string[] = [];
const fromMock = vi.fn((table: string) => {
  fromCalls.push(table);
  return {
    select: (_cols: string) => ({
      eq: (_col: string, val: string) => ({
        maybeSingle: async () => maybeSingleImpl(table, val),
      }),
    }),
    update: (patch: Record<string, unknown>) => ({
      eq: (_col: string, val: string) => {
        applyRowPatch(table, val, patch);
        return Promise.resolve({ error: null });
      },
    }),
  };
});

vi.mock('@supabase/supabase-js', () => ({
  createClient: () => ({ from: fromMock }),
}));

vi.mock('@/lib/ai-actions', async () => {
  const actual = await vi.importActual<typeof import('@/lib/ai-actions')>('@/lib/ai-actions');
  return {
    ...actual,
    createMission: vi.fn(),
    logDecision: vi.fn(),
  };
});

vi.mock('@/lib/engineering-queue', async () => {
  const actual = await vi.importActual<typeof import('@/lib/engineering-queue')>('@/lib/engineering-queue');
  return {
    ...actual,
    fetchEngineeringQueue: vi.fn(),
    setQueueItemStatus: vi.fn(),
  };
});

import { createMission, logDecision } from '@/lib/ai-actions';
import { fetchEngineeringQueue, setQueueItemStatus, type QueueItem } from '@/lib/engineering-queue';
import { openInvestigation, resolveInvestigation, type TriggerContext } from '@/lib/investigationEngine';
import { queueResolution, queueTriage, type QueueTriageDecision } from '@/lib/investigations/queueGovernance';

function trigger(originRef?: string, reason = 'unit test'): TriggerContext {
  return { investigationType: 'queue-resolution', reason, originatedAt: '2026-07-09T00:00:00.000Z', originRef };
}

function makeQueueItem(overrides: Partial<QueueItem> & { id: string; title: string }): QueueItem {
  return {
    id: overrides.id,
    title: overrides.title,
    summary: overrides.summary ?? null,
    rawStatus: overrides.rawStatus ?? 'awaiting_review',
    lifecycle: overrides.lifecycle ?? 'awaiting_review',
    blocked: overrides.blocked ?? false,
    source: overrides.source ?? 'build',
    priority: overrides.priority ?? null,
    prUrl: overrides.prUrl ?? null,
    ageDays: overrides.ageDays ?? 0,
    createdAt: overrides.createdAt ?? '2026-06-18T10:00:00.000Z',
    nextAction: overrides.nextAction ?? 'Review',
    actionType: overrides.actionType ?? null,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  fromCalls.length = 0;
  buildRequestRowsById = {};
  missionsById = {};
  decisionsById = {};
  queueState = [];
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co';
  process.env.SUPABASE_SERVICE_ROLE_KEY = 'test-key';

  vi.mocked(setQueueItemStatus).mockImplementation(async (item, decision) => {
    applyStatusUpdate(item.id, decision);
    return { ok: true };
  });
  vi.mocked(fetchEngineeringQueue).mockImplementation(async () => ({
    items: queueState,
    counts: {
      pending_triage: 0,
      assigned: queueState.filter((i) => i.lifecycle === 'assigned').length,
      in_progress: 0,
      awaiting_review: queueState.filter((i) => i.lifecycle === 'awaiting_review').length,
      completed: 0,
      rejected: queueState.filter((i) => i.lifecycle === 'rejected').length,
    },
    blockers: [],
    nextAction: null,
    isLive: true,
  }));
  vi.mocked(createMission).mockImplementation(async () => {
    const missionId = 'USS-TJR-MSN-9001';
    missionsById[missionId] = { mission_id: missionId };
    return { type: 'create_mission', success: true, detail: `Mission ${missionId} registered`, id: missionId };
  });
  vi.mocked(logDecision).mockImplementation(async () => {
    const id = 'decision-9001';
    decisionsById[id] = { id };
    return { type: 'log_decision', success: true, detail: 'Decision logged', id };
  });
});

// ── Queue Resolution ────────────────────────────────────────────────────

describe('queueResolution — declared metadata', () => {
  it('declares all nine required InvestigationDefinition fields with real values', () => {
    expect(queueResolution.type).toBe('queue-resolution');
    expect(queueResolution.owner).toBe('captain');
    expect(queueResolution.label.length).toBeGreaterThan(0);
    expect(queueResolution.triggerDescription.length).toBeGreaterThan(0);
    expect(queueResolution.requiredEvidence.length).toBeGreaterThan(0);
    expect(queueResolution.evidenceSources.length).toBeGreaterThan(0);
    expect(queueResolution.validationRules.length).toBeGreaterThan(0);
    expect(queueResolution.possibleDecisionKinds).toEqual(['approve', 'hold']);
    expect(queueResolution.completionCriteria.length).toBeGreaterThan(0);
    expect(queueResolution.auditOutputs.length).toBeGreaterThan(0);
  });

  it('never invents a literal "reject" decision - matches Decide\'s real vocabulary', () => {
    expect(queueResolution.possibleDecisionKinds).not.toContain('reject');
  });
});

describe('queueResolution — journey #10: an empty/malformed request resolves trivially', () => {
  it('blocks at evidence validation before any decision is ever offered', async () => {
    buildRequestRowsById['row-10'] = {
      id: 'row-10',
      title: '',
      summary: null,
      rationale: null,
      risks: null,
      status: 'awaiting_review',
      action_type: null,
      action_payload: null,
    };
    const state = await openInvestigation(queueResolution, trigger('row-10', 'empty build request'));
    expect(state.validation?.ok).toBe(false);
    expect(state.validation?.problems.join(' ')).toMatch(/no title/i);
    expect(state.decisionOptions).toBeUndefined();
    expect(state.completion).toEqual({ complete: false, reason: 'blocked at evidence validation — no decision was ever offered' });
  });

  it('also resolves trivially when no row exists at all for the given id', async () => {
    const state = await openInvestigation(queueResolution, trigger('does-not-exist'));
    expect(state.validation?.ok).toBe(false);
    expect(state.decisionOptions).toBeUndefined();
  });

  it('resolves trivially when no originRef is given', async () => {
    const state = await openInvestigation(queueResolution, trigger(undefined));
    expect(state.validation?.ok).toBe(false);
  });
});

describe('queueResolution — plain build request (no action_type)', () => {
  beforeEach(() => {
    buildRequestRowsById['row-7'] = {
      id: 'row-7',
      title: 'Draft ADR for MSN-0064 runtime canonical mission IDs',
      summary: 'ADR drafting request',
      rationale: 'Four independent ID-minting paths need one canonical scheme.',
      risks: 'Low - documentation only.',
      status: 'awaiting_review',
      action_type: null,
      action_payload: null,
    };
  });

  it('surfaces rationale/risks/question/reasoning/undoAvailable as evidence, and offers approve/hold', async () => {
    const state = await openInvestigation(queueResolution, trigger('row-7'));
    expect(state.validation?.ok).toBe(true);
    expect(state.evidence?.row?.rationale).toMatch(/canonical/);
    expect(state.evidence?.row?.risks).toMatch(/Low/);
    expect(state.evidence?.question).toMatch(/approve build request/i);
    expect(state.evidence?.reasoning).toMatch(/awaiting_review/i);
    expect(state.evidence?.undoAvailable).toBe(true);
    expect(state.decisionOptions?.map((o) => o.id)).toEqual(['approve', 'hold']);
  });

  it('approve calls the real setQueueItemStatus and verify confirms the row actually flipped', async () => {
    const opened = await openInvestigation(queueResolution, trigger('row-7'));
    const resolved = await resolveInvestigation(opened, 'approve');
    expect(setQueueItemStatus).toHaveBeenCalledWith(expect.objectContaining({ id: 'row-7' }), 'approved');
    expect(resolved.execution?.success).toBe(true);
    expect(resolved.verification?.status).toBe('verified');
    expect(resolved.completion?.complete).toBe(true);
    expect(buildRequestRowsById['row-7'].status).toBe('approved');
  });

  it('hold performs no mutation and does not complete', async () => {
    const opened = await openInvestigation(queueResolution, trigger('row-7'));
    const resolved = await resolveInvestigation(opened, 'hold');
    expect(setQueueItemStatus).not.toHaveBeenCalled();
    expect(resolved.execution?.attempted).toBe(false);
    expect(resolved.verification?.status).toBe('not_applicable');
    expect(resolved.completion?.complete).toBe(false);
    expect(resolved.completion?.reason).toMatch(/held/i);
    expect(buildRequestRowsById['row-7'].status).toBe('awaiting_review');
  });

  it('verify reports a mismatch if the reported status flip never actually reached the row (e.g. a silently-denied RLS write)', async () => {
    // execute() will report success, but - unlike the default mock - the
    // underlying row is deliberately left untouched, exactly the "claim vs
    // reality" gap this verify() step exists to catch.
    vi.mocked(setQueueItemStatus).mockResolvedValueOnce({ ok: true });
    const opened = await openInvestigation(queueResolution, trigger('row-7'));
    const resolved = await resolveInvestigation(opened, 'approve');
    expect(resolved.execution?.success).toBe(true);
    expect(resolved.verification?.status).toBe('mismatch');
    expect(resolved.verification?.detail).toMatch(/awaiting_review/);
    expect(resolved.completion?.complete).toBe(false);
  });
});

describe('queueResolution — MSN-0352 governed create_mission proposal (journey #11)', () => {
  beforeEach(() => {
    buildRequestRowsById['row-11'] = {
      id: 'row-11',
      title: 'Spawn XO and Chief Engineer Authority Mission',
      summary: 'Proposed mission: Spawn XO and Chief Engineer Authority Mission',
      rationale: null,
      risks: null,
      status: 'awaiting_review',
      action_type: 'create_mission',
      action_payload: { title: 'Spawn XO and Chief Engineer Authority Mission' },
    };
  });

  it('question/reasoning name the real action, and undo is never available', async () => {
    const state = await openInvestigation(queueResolution, trigger('row-11'));
    expect(state.evidence?.question).toMatch(/approve mission creation/i);
    expect(state.evidence?.reasoning).toMatch(/proposed by an ai advisor/i);
    expect(state.evidence?.undoAvailable).toBe(false);
  });

  it('approve calls the REAL createMission function (not a stub) and verify confirms the mission exists', async () => {
    const opened = await openInvestigation(queueResolution, trigger('row-11'));
    const resolved = await resolveInvestigation(opened, 'approve');
    expect(createMission).toHaveBeenCalledWith({ title: 'Spawn XO and Chief Engineer Authority Mission' });
    expect(resolved.execution?.success).toBe(true);
    expect(resolved.verification?.status).toBe('verified');
    expect(resolved.completion?.complete).toBe(true);
    expect(missionsById['USS-TJR-MSN-9001']).toBeDefined();
  });

  it('MSN-0350 journey #9 / MSN-0356 shape: execution reports success but no missions row ever materializes - verify catches the mismatch', async () => {
    vi.mocked(createMission).mockResolvedValueOnce({
      type: 'create_mission',
      success: true,
      detail: 'Mission USS-TJR-MSN-0066 registered',
      id: 'USS-TJR-MSN-0066',
      // Deliberately do NOT register it in missionsById - reproduces the
      // real ca83a08b defect: "approved" was not "happened".
    });
    const opened = await openInvestigation(queueResolution, trigger('row-11'));
    const resolved = await resolveInvestigation(opened, 'approve');
    expect(resolved.execution?.success).toBe(true);
    expect(resolved.verification?.status).toBe('mismatch');
    expect(resolved.verification?.detail).toMatch(/USS-TJR-MSN-0066/);
    expect(resolved.completion?.complete).toBe(false);
    expect(resolved.learning?.category).toBe('coverage-gap');
    expect(resolved.learning?.insight).toMatch(/Downstream Verification Gap/i);
  });

  it('a malformed action_payload is refused before any mutation, fail-closed', async () => {
    buildRequestRowsById['row-11'].action_payload = {};
    const opened = await openInvestigation(queueResolution, trigger('row-11'));
    const resolved = await resolveInvestigation(opened, 'approve');
    expect(createMission).not.toHaveBeenCalled();
    expect(resolved.execution?.success).toBe(false);
    expect(resolved.completion?.complete).toBe(false);
  });
});

describe('queueResolution — MSN-0352 governed log_decision proposal', () => {
  it('approve calls the REAL logDecision function and verify confirms the decision exists', async () => {
    buildRequestRowsById['row-12'] = {
      id: 'row-12',
      title: 'Adopt vector database for architecture search',
      summary: null,
      rationale: null,
      risks: null,
      status: 'awaiting_review',
      action_type: 'log_decision',
      action_payload: { decision: 'Adopt vector database for architecture search' },
    };
    const opened = await openInvestigation(queueResolution, trigger('row-12'));
    const resolved = await resolveInvestigation(opened, 'approve');
    expect(logDecision).toHaveBeenCalledWith({ decision: 'Adopt vector database for architecture search' });
    expect(resolved.verification?.status).toBe('verified');
    expect(resolved.completion?.complete).toBe(true);
  });
});

// ── Queue Triage / Deduplication ────────────────────────────────────────

describe('queueTriage — declared metadata', () => {
  it('declares all nine required InvestigationDefinition fields with real values, owner shared', () => {
    expect(queueTriage.type).toBe('queue-triage');
    expect(queueTriage.owner).toBe('shared');
    expect(queueTriage.label.length).toBeGreaterThan(0);
    expect(queueTriage.triggerDescription.length).toBeGreaterThan(0);
    expect(queueTriage.requiredEvidence.length).toBeGreaterThan(0);
    expect(queueTriage.evidenceSources.length).toBeGreaterThan(0);
    expect(queueTriage.validationRules.length).toBeGreaterThan(0);
    expect(queueTriage.possibleDecisionKinds).toEqual(['resolve-one-archive-rest', 'no-duplicates-found']);
    expect(queueTriage.completionCriteria.length).toBeGreaterThan(0);
    expect(queueTriage.auditOutputs.length).toBeGreaterThan(0);
  });
});

describe('queueTriage — empty queue blocks at evidence validation', () => {
  it('nothing to triage against zero awaiting_review rows', async () => {
    const state = await openInvestigation(queueTriage, trigger(undefined, 'periodic triage sweep'));
    expect(state.validation?.ok).toBe(false);
    expect(state.decisionOptions).toBeUndefined();
  });
});

describe('queueTriage — journey #8: two near-duplicate dead-code audit requests, three minutes apart', () => {
  beforeEach(() => {
    buildRequestRowsById['dup-a'] = { id: 'dup-a', title: 'Dead Code Audit and Deprecation Plan for Mission Registry', status: 'awaiting_review', action_type: null, action_payload: null };
    buildRequestRowsById['dup-b'] = { id: 'dup-b', title: 'Dead Code Audit and Deprecation Plan for the Mission Registry', status: 'awaiting_review', action_type: null, action_payload: null };
    queueState = [
      makeQueueItem({ id: 'dup-a', title: 'Dead Code Audit and Deprecation Plan for Mission Registry', createdAt: '2026-06-18T10:00:00.000Z' }),
      makeQueueItem({ id: 'dup-b', title: 'Dead Code Audit and Deprecation Plan for the Mission Registry', createdAt: '2026-06-18T10:03:00.000Z' }),
      makeQueueItem({ id: 'other', title: 'Implement Path A: Canonical Runtime Mission-ID Allocation', createdAt: '2026-06-19T09:00:00.000Z' }),
    ];
  });

  it('detects the near-duplicate pair by real title-token overlap, and leaves the unrelated third item out of it', async () => {
    const state = await openInvestigation(queueTriage, trigger(undefined, 'periodic triage sweep'));
    expect(state.validation?.ok).toBe(true);
    expect(state.evidence?.duplicatePairs).toHaveLength(1);
    expect(state.evidence?.duplicatePairs[0].aId).toBe('dup-a');
    expect(state.evidence?.duplicatePairs[0].bId).toBe('dup-b');
    expect(state.evidence?.duplicatePairs[0].overlapScore).toBeGreaterThanOrEqual(0.5);
    expect(state.decisionOptions).toHaveLength(1);
    expect(state.decisionOptions?.[0].value).toEqual({
      kind: 'resolve-one-archive-rest',
      keepId: 'dup-a',
      keepTitle: 'Dead Code Audit and Deprecation Plan for Mission Registry',
      archiveIds: ['dup-b'],
    });
  });

  it('resolving the group archives the duplicate (only one item remains approve-worthy) and verify confirms it left the queue', async () => {
    const opened = await openInvestigation(queueTriage, trigger(undefined, 'periodic triage sweep'));
    const decision = opened.decisionOptions?.[0].value as QueueTriageDecision;
    const resolved = await resolveInvestigation(opened, decision);

    expect(setQueueItemStatus).toHaveBeenCalledWith(expect.objectContaining({ id: 'dup-b' }), 'rejected');
    expect(resolved.execution?.success).toBe(true);
    expect(resolved.verification?.status).toBe('verified');
    expect(resolved.completion?.complete).toBe(true);
    expect(resolved.learning?.category).toBe('process-gap');

    // Regression assertion for journey #8's actual real-world outcome: of
    // the two near-duplicate requests, only ONE remains eligible to be
    // approved through Queue Resolution afterwards - the other was archived,
    // not independently approved a second time.
    expect(queueState.find((i) => i.id === 'dup-b')?.lifecycle).toBe('rejected');
    expect(queueState.find((i) => i.id === 'dup-a')?.lifecycle).toBe('awaiting_review');

    // The underlying build_request_inbox row Queue Resolution would read is
    // updated too (same in-memory "table"), so a subsequent Queue
    // Resolution run on the archived duplicate is correctly refused...
    buildRequestRowsById['dup-b'].status = 'rejected';
    const archivedAttempt = await openInvestigation(queueResolution, trigger('dup-b'));
    expect(archivedAttempt.validation?.ok).toBe(false);

    // ...while the kept item still resolves normally through Queue Resolution.
    const keptAttempt = await openInvestigation(queueResolution, trigger('dup-a'));
    expect(keptAttempt.validation?.ok).toBe(true);
    expect(keptAttempt.decisionOptions?.map((o) => o.id)).toEqual(['approve', 'hold']);
  });
});

describe('queueTriage — no duplicates found', () => {
  it('offers the honest no-duplicates-found option and performs no mutation', async () => {
    queueState = [
      makeQueueItem({ id: 'a', title: 'Fix the login page timeout bug' }),
      makeQueueItem({ id: 'b', title: 'Weekly ORI risk-trend brief review' }),
    ];
    const opened = await openInvestigation(queueTriage, trigger(undefined, 'periodic triage sweep'));
    expect(opened.evidence?.hasDuplicates).toBe(false);
    expect(opened.decisionOptions).toHaveLength(1);
    expect(opened.decisionOptions?.[0].id).toBe('no-duplicates-found');

    const resolved = await resolveInvestigation(opened, { kind: 'no-duplicates-found' });
    expect(setQueueItemStatus).not.toHaveBeenCalled();
    expect(resolved.execution?.attempted).toBe(false);
    expect(resolved.verification?.status).toBe('not_applicable');
    expect(resolved.completion?.complete).toBe(true);
  });
});
