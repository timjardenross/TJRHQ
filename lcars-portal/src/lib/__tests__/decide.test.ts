import { describe, it, expect, vi, beforeEach } from 'vitest';
import { readFileSync } from 'fs';
import { join } from 'path';

// ── Mocks ────────────────────────────────────────────────────────────────
// decide.ts must only ever call the SAME governed write paths the existing
// (pre-Decide) approve/reject UIs already use - never a new route. Mocking
// at this boundary lets us assert exactly which table/endpoint is hit.

// EOS Phase 3 Priority 2: writeLedger() now chains .insert().select('id')
// .single() (it returns the new row's id, so Communications Studio's
// Decision Brief can launch with automatic context) rather than a bare
// .insert() - insertMock still receives the exact row, so every existing
// assertion on its call args is unchanged; insertSingleMock controls what
// the chain resolves to.
const insertSingleMock = vi.fn().mockResolvedValue({ data: { id: 'ledger-1' }, error: null });
const insertMock = vi.fn((row: Record<string, unknown>) => ({ select: (_cols: string) => ({ single: insertSingleMock }) }));
const updateEqSelectMock = vi.fn().mockResolvedValue({ data: [{ id: 'x' }], error: null });
const historyLimitMock = vi.fn().mockResolvedValue({ data: [], error: null });
const fromMock = vi.fn((table: string) => ({
  insert: insertMock,
  update: (payload: Record<string, unknown>) => ({
    eq: (_col: string, _val: string) => ({
      select: (_cols: string) => updateEqSelectMock(table, payload),
    }),
  }),
  select: (_cols: string) => ({
    order: (_col: string, _opts: unknown) => ({
      limit: (n: number) => historyLimitMock(table, n),
    }),
  }),
}));

vi.mock('@/lib/supabase-browser', () => ({
  createSupabaseBrowserClient: () => ({ from: fromMock }),
}));

vi.mock('@/lib/decisions', () => ({
  fetchMissionDecisions: vi.fn(),
}));

vi.mock('@/lib/engineering-queue', async () => {
  const actual = await vi.importActual<typeof import('@/lib/engineering-queue')>('@/lib/engineering-queue');
  return {
    ...actual,
    fetchEngineeringQueue: vi.fn(),
    setQueueItemStatus: vi.fn(),
  };
});

import { fetchMissionDecisions } from '@/lib/decisions';
import { fetchEngineeringQueue, setQueueItemStatus, type QueueItem } from '@/lib/engineering-queue';
import {
  fetchDecideQueue,
  fetchDecideCount,
  approveDecideItem,
  holdDecideItem,
  undoDecideItem,
  updateDecideOutcome,
  fetchDecideHistory,
  missionReasoning,
  engineeringReasoning,
  DECIDE_EMPTY_TITLE,
  DECIDE_EMPTY_DETAIL,
  type DecideItem,
} from '@/lib/decide';

const missionItem: DecideItem = {
  id: 'mission:MSN-0123',
  source: 'mission',
  rawId: 'MSN-0123',
  question: 'Approve mission "Test Mission"?',
  reasoning: 'This mission is awaiting your decision. Awaiting Captain Approval',
  domainTag: 'Mission',
  undoAvailable: false,
  _sortRank: 80,
};

const engineeringItem: DecideItem = {
  id: 'eng:abc-123',
  source: 'engineering',
  rawId: 'abc-123',
  question: 'Approve build request "Fix bug"?',
  reasoning: 'Status: awaiting_review.',
  domainTag: 'Engineering',
  undoAvailable: true,
  priorStatus: 'awaiting_review',
  _sortRank: 60,
};

beforeEach(() => {
  vi.clearAllMocks();
  insertSingleMock.mockResolvedValue({ data: { id: 'ledger-1' }, error: null });
  updateEqSelectMock.mockResolvedValue({ data: [{ id: 'x' }], error: null });
  historyLimitMock.mockResolvedValue({ data: [], error: null });
  global.fetch = vi.fn();
});

// ── 1. Never claims Priority Engine ranking, never fakes a recommendation ──
describe('Decide never claims Priority Engine ranking or a fake recommendation', () => {
  const decideLibSource = readFileSync(join(__dirname, '../decide.ts'), 'utf-8');

  function stripComments(src: string): string {
    return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
  }

  it('no visible copy in decide.ts claims "Priority Engine" ranking', () => {
    expect(stripComments(decideLibSource)).not.toMatch(/priority\s+engine/i);
  });

  // The 2 tests that used to live here read app/decide/page.tsx — that
  // route was deliberately decommissioned 2026-07-18 (nav.ts: "/decide,
  // /ask, /recommended, /comms-studio have been decommissioned... routed
  // to /workbenches instead"). Removed 2026-08-11 rather than resurrecting
  // a retired page to satisfy a stale test — lib/decide.ts (still live,
  // still tested above and below) is what actually needs this coverage.

  it('reasoning text is fact-only - never contains a recommendation verb', () => {
    expect(missionReasoning('Awaiting Captain Approval · P1')).not.toMatch(/recommend/i);
    const engItem = { rawStatus: 'awaiting_review', blocked: false, priority: 'P1', ageDays: 3 } as QueueItem;
    expect(engineeringReasoning(engItem)).not.toMatch(/recommend/i);
  });
});

// ── 2. Empty state is honest ────────────────────────────────────────────
describe('Decide empty state', () => {
  it('states plainly that both queues are clear, not a fabricated summary', () => {
    expect(DECIDE_EMPTY_TITLE).toBe('Nothing needs your judgement right now.');
    expect(DECIDE_EMPTY_DETAIL).toMatch(/clear/i);
  });

  it('fetchDecideQueue returns an empty array when both real sources are empty', async () => {
    vi.mocked(fetchMissionDecisions).mockResolvedValue([]);
    vi.mocked(fetchEngineeringQueue).mockResolvedValue({
      items: [], counts: { pending_triage: 0, assigned: 0, in_progress: 0, awaiting_review: 0, completed: 0, rejected: 0 },
      blockers: [], nextAction: null, isLive: true,
    });
    const queue = await fetchDecideQueue();
    expect(queue).toEqual([]);
    expect(await fetchDecideCount()).toBe(0);
  });
});

// ── 3. No fake Operational Intelligence decisions ───────────────────────
describe('No fake Operational Intelligence decisions', () => {
  it('DecideSource type only ever produces mission/engineering items - no intelligence source exists in decide.ts', () => {
    const stripped = readFileSync(join(__dirname, '../decide.ts'), 'utf-8')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/\/\/.*$/gm, '');
    // The type union and every literal 'source' value used to construct a
    // DecideItem must be drawn only from mission/engineering - there is no
    // fetchIntelligenceDecisions()-style third source in this file at all.
    expect(stripped).not.toMatch(/fetchIntelligenceDecisions/);
    expect(stripped).not.toMatch(/'intelligence'/);
    expect(stripped).not.toMatch(/"intelligence"/);
  });

  it('a mixed real fetch never produces a third source in the merged queue', async () => {
    vi.mocked(fetchMissionDecisions).mockResolvedValue([
      { id: 'mission:MSN-1', source: 'mission', title: 'T', detail: 'Awaiting Captain Approval', priorityRank: 80 },
    ]);
    vi.mocked(fetchEngineeringQueue).mockResolvedValue({
      items: [
        {
          id: 'abc', title: 'Build', summary: null, rawStatus: 'awaiting_review', lifecycle: 'awaiting_review',
          blocked: false, source: 'build', priority: 'P1', prUrl: null, ageDays: 2, createdAt: null, nextAction: 'Review',
          actionType: null,
        },
      ],
      counts: { pending_triage: 0, assigned: 0, in_progress: 0, awaiting_review: 1, completed: 0, rejected: 0 },
      blockers: [], nextAction: null, isLive: true,
    });
    const queue = await fetchDecideQueue();
    expect(queue.every((i) => i.source === 'mission' || i.source === 'engineering')).toBe(true);
    expect(queue).toHaveLength(2);
  });
});

// ── 4. Actions use the existing governed routes, not a new write path ──────
describe('Decide actions route to the existing governed sources', () => {
  it('approving a mission item calls the same /api/missions/:id/approve route the legacy UI uses', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ mission_id: 'MSN-0123' }),
    });
    const res = await approveDecideItem(missionItem);
    expect(res.ok).toBe(true);
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/missions/MSN-0123/approve',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('approving an engineering item calls setQueueItemStatus (same mechanism as the legacy Engineering Queue)', async () => {
    vi.mocked(setQueueItemStatus).mockResolvedValue({ ok: true });
    const res = await approveDecideItem(engineeringItem);
    expect(res.ok).toBe(true);
    expect(setQueueItemStatus).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'abc-123', source: 'build' }),
      'approved',
    );
  });

  it('every approve/hold/undo writes one row to decide_ledger', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: true, json: async () => ({}) });
    await approveDecideItem(missionItem);
    expect(fromMock).toHaveBeenCalledWith('decide_ledger');
    expect(insertMock).toHaveBeenCalledWith(expect.objectContaining({ action: 'approve', source: 'mission' }));

    vi.clearAllMocks();
    await holdDecideItem(missionItem);
    expect(insertMock).toHaveBeenCalledWith(expect.objectContaining({ action: 'hold' }));
  });

  it('hold never calls any source mutation route - it only defers', async () => {
    await holdDecideItem(missionItem);
    expect(global.fetch).not.toHaveBeenCalled();
    expect(setQueueItemStatus).not.toHaveBeenCalled();
  });
});

// ── Undo honesty ─────────────────────────────────────────────────────────
describe('Undo is honest about what the source actually supports', () => {
  it('mission decisions never claim undo is available', () => {
    expect(missionItem.undoAvailable).toBe(false);
  });

  it('undo on a mission item fails with an honest explanation, no silent no-op success', async () => {
    const res = await undoDecideItem(missionItem);
    expect(res.ok).toBe(false);
    expect(res.error).toMatch(/not supported/i);
  });

  it('undo on an engineering item restores the captured prior status via the real table', async () => {
    const res = await undoDecideItem(engineeringItem);
    expect(res.ok).toBe(true);
    expect(fromMock).toHaveBeenCalledWith('build_request_inbox');
    expect(updateEqSelectMock).toHaveBeenCalledWith('build_request_inbox', { status: 'awaiting_review' });
  });
});

// ── Retrospective outcome capture ───────────────────────────────────────
describe('updateDecideOutcome writes to the existing decide_ledger row by id', () => {
  it('updates outcome on the ledger row and reports success', async () => {
    const res = await updateDecideOutcome('ledger-1', 'Deferral was correct; competitor exited market.');
    expect(res.ok).toBe(true);
    expect(fromMock).toHaveBeenCalledWith('decide_ledger');
    expect(updateEqSelectMock).toHaveBeenCalledWith('decide_ledger', { outcome: 'Deferral was correct; competitor exited market.' });
  });

  it('surfaces an honest error when the update fails, no silent success', async () => {
    updateEqSelectMock.mockResolvedValueOnce({ data: null, error: { message: 'row not found' } });
    const res = await updateDecideOutcome('missing-id', 'irrelevant');
    expect(res.ok).toBe(false);
    expect(res.error).toBe('row not found');
  });

  it('never inserts a new row - only updates the existing one', async () => {
    await updateDecideOutcome('ledger-1', 'Outcome text');
    expect(insertMock).not.toHaveBeenCalled();
  });
});

// ── Past decisions list ──────────────────────────────────────────────────
describe('fetchDecideHistory reads decide_ledger, most recent first', () => {
  it('returns the rows from decide_ledger', async () => {
    historyLimitMock.mockResolvedValueOnce({
      data: [{ id: 'l-2', question: 'Q2', source: 'mission', action: 'approve', decided_at: '2026-07-10T00:00:00Z', outcome: null }],
      error: null,
    });
    const rows = await fetchDecideHistory();
    expect(fromMock).toHaveBeenCalledWith('decide_ledger');
    expect(rows).toHaveLength(1);
    expect(rows[0].id).toBe('l-2');
  });

  it('degrades to an empty array on error rather than throwing', async () => {
    historyLimitMock.mockResolvedValueOnce({ data: null, error: { message: 'boom' } });
    const rows = await fetchDecideHistory();
    expect(rows).toEqual([]);
  });

  it('passes the requested limit through', async () => {
    await fetchDecideHistory(5);
    expect(historyLimitMock).toHaveBeenCalledWith('decide_ledger', 5);
  });
});

// ── MSN-0352: proposed AI actions route through Decide's real approval ────
// gate, not through the LLM conversation. These tests assert the exact
// distinction the mission requires: a proposed create_mission/log_decision
// is NOT the same as an ordinary build request - it must call the
// dedicated approve-action route (a deterministic server handler) rather
// than the plain status-flip setQueueItemStatus, and it must never be
// undo-eligible (the mutation it performs is real and not cleanly
// reversible, same principle already applied to mission approvals).
describe('MSN-0352: proposed conversational actions', () => {
  const proposedMissionQueueItem: QueueItem = {
    id: 'prop-1', title: 'AI-proposed mission', summary: 'Proposed mission: AI-proposed mission', rawStatus: 'awaiting_review',
    lifecycle: 'awaiting_review', blocked: false, source: 'build', priority: null, prUrl: null, ageDays: 0, createdAt: null,
    nextAction: 'Review — approve or reject this item.', actionType: 'create_mission',
  };
  const proposedDecisionQueueItem: QueueItem = {
    id: 'prop-2', title: 'AI-proposed decision', summary: 'Proposed decision log: AI-proposed decision', rawStatus: 'awaiting_review',
    lifecycle: 'awaiting_review', blocked: false, source: 'build', priority: null, prUrl: null, ageDays: 0, createdAt: null,
    nextAction: 'Review — approve or reject this item.', actionType: 'log_decision',
  };
  const proposedHandoffQueueItem: QueueItem = {
    id: 'prop-3', title: 'AI-proposed handoff', summary: null, rawStatus: 'awaiting_review',
    lifecycle: 'awaiting_review', blocked: false, source: 'build', priority: null, prUrl: null, ageDays: 0, createdAt: null,
    nextAction: 'Review — approve or reject this item.', actionType: 'create_handoff',
  };

  it('a proposed create_mission item gets a distinct question and reasoning, and is never undo-eligible', async () => {
    vi.mocked(fetchMissionDecisions).mockResolvedValue([]);
    vi.mocked(fetchEngineeringQueue).mockResolvedValue({
      items: [proposedMissionQueueItem], counts: { pending_triage: 0, assigned: 0, in_progress: 0, awaiting_review: 1, completed: 0, rejected: 0 },
      blockers: [], nextAction: null, isLive: true,
    });
    const [item] = await fetchDecideQueue();
    expect(item.actionType).toBe('create_mission');
    expect(item.question).toMatch(/approve mission creation/i);
    expect(item.reasoning).toMatch(/proposed by an ai advisor/i);
    expect(item.reasoning).toMatch(/approving this will create a new mission/i);
    expect(item.undoAvailable).toBe(false);
  });

  it('a proposed log_decision item gets a distinct question and is never undo-eligible', async () => {
    vi.mocked(fetchMissionDecisions).mockResolvedValue([]);
    vi.mocked(fetchEngineeringQueue).mockResolvedValue({
      items: [proposedDecisionQueueItem], counts: { pending_triage: 0, assigned: 0, in_progress: 0, awaiting_review: 1, completed: 0, rejected: 0 },
      blockers: [], nextAction: null, isLive: true,
    });
    const [item] = await fetchDecideQueue();
    expect(item.actionType).toBe('log_decision');
    expect(item.question).toMatch(/approve decision log/i);
    expect(item.undoAvailable).toBe(false);
  });

  it('a proposed create_handoff item behaves exactly like an ordinary build request (unchanged undo semantics)', async () => {
    vi.mocked(fetchMissionDecisions).mockResolvedValue([]);
    vi.mocked(fetchEngineeringQueue).mockResolvedValue({
      items: [proposedHandoffQueueItem], counts: { pending_triage: 0, assigned: 0, in_progress: 0, awaiting_review: 1, completed: 0, rejected: 0 },
      blockers: [], nextAction: null, isLive: true,
    });
    const [item] = await fetchDecideQueue();
    expect(item.question).toMatch(/approve build request/i);
    expect(item.undoAvailable).toBe(true);
  });

  it('approving a proposed create_mission item calls the deterministic approve-action route, never setQueueItemStatus', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
    const decideItem: DecideItem = {
      id: 'eng:prop-1', source: 'engineering', rawId: 'prop-1', question: 'Approve mission creation: "X"?',
      reasoning: 'Proposed by an AI advisor.', domainTag: 'Engineering', undoAvailable: false,
      priorStatus: 'awaiting_review', actionType: 'create_mission', _sortRank: 60,
    };
    const res = await approveDecideItem(decideItem);
    expect(res.ok).toBe(true);
    expect(global.fetch).toHaveBeenCalledWith('/api/build-request/prop-1/approve-action', expect.objectContaining({ method: 'POST' }));
    expect(setQueueItemStatus).not.toHaveBeenCalled();
  });

  it('approving a proposed log_decision item also calls the approve-action route', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
    const decideItem: DecideItem = {
      id: 'eng:prop-2', source: 'engineering', rawId: 'prop-2', question: 'Approve decision log: "X"?',
      reasoning: 'Proposed by an AI advisor.', domainTag: 'Engineering', undoAvailable: false,
      priorStatus: 'awaiting_review', actionType: 'log_decision', _sortRank: 60,
    };
    await approveDecideItem(decideItem);
    expect(global.fetch).toHaveBeenCalledWith('/api/build-request/prop-2/approve-action', expect.objectContaining({ method: 'POST' }));
    expect(setQueueItemStatus).not.toHaveBeenCalled();
  });

  it('approving a proposed create_handoff item still uses setQueueItemStatus, unchanged from ordinary build requests', async () => {
    vi.mocked(setQueueItemStatus).mockResolvedValue({ ok: true });
    const decideItem: DecideItem = {
      id: 'eng:prop-3', source: 'engineering', rawId: 'prop-3', question: 'Approve build request "X"?',
      reasoning: 'Proposed by an AI advisor.', domainTag: 'Engineering', undoAvailable: true,
      priorStatus: 'awaiting_review', actionType: 'create_handoff', _sortRank: 60,
    };
    await approveDecideItem(decideItem);
    expect(setQueueItemStatus).toHaveBeenCalled();
    expect(global.fetch).not.toHaveBeenCalledWith(expect.stringContaining('/approve-action'), expect.anything());
  });

  it('holding a proposed action never calls fetch, setQueueItemStatus, or the approve-action route - it only defers', async () => {
    const decideItem: DecideItem = {
      id: 'eng:prop-1', source: 'engineering', rawId: 'prop-1', question: 'Approve mission creation: "X"?',
      reasoning: 'Proposed by an AI advisor.', domainTag: 'Engineering', undoAvailable: false,
      priorStatus: 'awaiting_review', actionType: 'create_mission', _sortRank: 60,
    };
    await holdDecideItem(decideItem);
    expect(global.fetch).not.toHaveBeenCalled();
    expect(setQueueItemStatus).not.toHaveBeenCalled();
    expect(insertMock).toHaveBeenCalledWith(expect.objectContaining({ action: 'hold' }));
  });

  it('undo is refused for a proposed create_mission/log_decision item - the mutation already happened and is not reversible', async () => {
    const decideItem: DecideItem = {
      id: 'eng:prop-1', source: 'engineering', rawId: 'prop-1', question: 'Approve mission creation: "X"?',
      reasoning: 'Proposed by an AI advisor.', domainTag: 'Engineering', undoAvailable: false,
      priorStatus: 'awaiting_review', actionType: 'create_mission', _sortRank: 60,
    };
    const res = await undoDecideItem(decideItem);
    expect(res.ok).toBe(false);
  });
});
