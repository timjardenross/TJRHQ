import { describe, it, expect, vi, beforeEach } from 'vitest';
import { readFileSync } from 'fs';
import { join } from 'path';

// ── Mocks ────────────────────────────────────────────────────────────────
// decide.ts must only ever call the SAME governed write paths the existing
// (pre-Decide) approve/reject UIs already use - never a new route. Mocking
// at this boundary lets us assert exactly which table/endpoint is hit.

const insertMock = vi.fn().mockResolvedValue({ data: null, error: null });
const updateEqSelectMock = vi.fn().mockResolvedValue({ data: [{ id: 'x' }], error: null });
const fromMock = vi.fn((table: string) => ({
  insert: insertMock,
  update: (payload: Record<string, unknown>) => ({
    eq: (_col: string, _val: string) => ({
      select: (_cols: string) => updateEqSelectMock(table, payload),
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
  insertMock.mockResolvedValue({ data: null, error: null });
  updateEqSelectMock.mockResolvedValue({ data: [{ id: 'x' }], error: null });
  global.fetch = vi.fn();
});

// ── 1. Never claims Priority Engine ranking, never fakes a recommendation ──
describe('Decide never claims Priority Engine ranking or a fake recommendation', () => {
  const decideLibSource = readFileSync(join(__dirname, '../decide.ts'), 'utf-8');
  const decidePageSource = readFileSync(join(__dirname, '../../app/decide/page.tsx'), 'utf-8');

  function stripComments(src: string): string {
    return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
  }

  it('no visible copy in decide.ts claims "Priority Engine" ranking', () => {
    expect(stripComments(decideLibSource)).not.toMatch(/priority\s+engine/i);
  });

  it('no visible copy in /decide claims "Priority Engine" ranking', () => {
    expect(stripComments(decidePageSource)).not.toMatch(/priority\s+engine/i);
  });

  it('no visible copy claims a ranked list ("ranked", "top priority", "recommended")', () => {
    const stripped = stripComments(decidePageSource);
    expect(stripped).not.toMatch(/ranked\s+list/i);
    expect(stripped).not.toMatch(/recommend/i);
    expect(stripped).not.toMatch(/we recommend/i);
  });

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
