import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Mocks ────────────────────────────────────────────────────────────────
// MSN-0352: the entire point of this file is to prove parseAndProposeActions
// NEVER writes to missions/build_request_inbox(approved)/commander_decisions
// directly - it only ever inserts an awaiting_review row. Mocking at the
// createClient boundary lets us assert exactly which table gets which write.

const insertMock = vi.fn();
const singleMock = vi.fn();
const selectAfterInsertMock = vi.fn(() => ({ single: singleMock }));
const fromCalls: string[] = [];

const fromMock = vi.fn((table: string) => {
  fromCalls.push(table);
  return {
    insert: (row: Record<string, unknown>) => {
      insertMock(table, row);
      return { select: selectAfterInsertMock };
    },
  };
});

vi.mock('@supabase/supabase-js', () => ({
  createClient: () => ({ from: fromMock }),
}));

vi.mock('@/lib/id-registry', () => ({
  nextId: vi.fn().mockResolvedValue('USS-TJR-MSN-0999'),
  appendToRegistry: vi.fn(),
}));

import { parseAndProposeActions, validateActionPayload, createMission, logDecision, createHandoff } from '@/lib/ai-actions';

beforeEach(() => {
  vi.clearAllMocks();
  fromCalls.length = 0;
  singleMock.mockResolvedValue({ data: { id: 'row-1' }, error: null });
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co';
  process.env.SUPABASE_SERVICE_ROLE_KEY = 'test-key';
});

// ── validateActionPayload: fail-closed validation ──────────────────────────
describe('validateActionPayload', () => {
  it('rejects an unsupported action type', () => {
    const r = validateActionPayload('delete_mission', { title: 'x' });
    expect(r.ok).toBe(false);
  });

  it('rejects a non-object payload', () => {
    expect(validateActionPayload('create_mission', 'not an object').ok).toBe(false);
    expect(validateActionPayload('create_mission', null).ok).toBe(false);
    expect(validateActionPayload('create_mission', ['a']).ok).toBe(false);
  });

  it('rejects create_mission with no title', () => {
    expect(validateActionPayload('create_mission', {}).ok).toBe(false);
    expect(validateActionPayload('create_mission', { title: '  ' }).ok).toBe(false);
  });

  it('accepts a valid create_mission payload', () => {
    expect(validateActionPayload('create_mission', { title: 'Fix the thing' }).ok).toBe(true);
  });

  it('rejects create_handoff with no title', () => {
    expect(validateActionPayload('create_handoff', {}).ok).toBe(false);
  });

  it('rejects log_decision with neither decision nor title', () => {
    expect(validateActionPayload('log_decision', { rationale: 'because' }).ok).toBe(false);
  });

  it('accepts log_decision with just a decision string', () => {
    expect(validateActionPayload('log_decision', { decision: 'Ship it' }).ok).toBe(true);
  });
});

// ── parseAndProposeActions: never executes, only proposes ─────────────────
describe('parseAndProposeActions never mutates operational state directly', () => {
  it('queues a create_mission proposal into build_request_inbox with status=awaiting_review, never touches missions', async () => {
    const text = `I'll set that up. <starfleet-action type="create_mission">{"title": "New mission", "priority": "P1"}</starfleet-action>`;
    const results = await parseAndProposeActions(text);

    expect(results).toHaveLength(1);
    expect(results[0].success).toBe(true);
    expect(fromCalls).toEqual(['build_request_inbox']);
    expect(fromCalls).not.toContain('missions');

    const [, row] = insertMock.mock.calls[0];
    expect(row.status).toBe('awaiting_review');
    expect(row.action_type).toBe('create_mission');
    expect(row.action_payload).toEqual({ title: 'New mission', priority: 'P1' });
  });

  it('queues a log_decision proposal into build_request_inbox, never touches commander_decisions', async () => {
    const text = `<starfleet-action type="log_decision">{"decision": "Adopt X", "rationale": "because Y"}</starfleet-action>`;
    const results = await parseAndProposeActions(text);

    expect(results[0].success).toBe(true);
    expect(fromCalls).toEqual(['build_request_inbox']);
    expect(fromCalls).not.toContain('commander_decisions');
    const [, row] = insertMock.mock.calls[0];
    expect(row.status).toBe('awaiting_review');
    expect(row.action_type).toBe('log_decision');
  });

  it('queues a create_handoff proposal with status=awaiting_review, NOT approved', async () => {
    const text = `<starfleet-action type="create_handoff">{"title": "Ship the thing", "priority": "P0"}</starfleet-action>`;
    const results = await parseAndProposeActions(text);

    expect(results[0].success).toBe(true);
    const [, row] = insertMock.mock.calls[0];
    expect(row.status).toBe('awaiting_review');
    expect(row.status).not.toBe('approved');
  });

  it('fails closed on malformed JSON - never queues, never inserts anywhere', async () => {
    const text = `<starfleet-action type="create_mission">{not valid json</starfleet-action>`;
    const results = await parseAndProposeActions(text);
    expect(results[0].success).toBe(false);
    expect(insertMock).not.toHaveBeenCalled();
  });

  it('fails closed on an unsupported action type - never queues it', async () => {
    const text = `<starfleet-action type="delete_everything">{"title": "oops"}</starfleet-action>`;
    const results = await parseAndProposeActions(text);
    expect(results[0].success).toBe(false);
    expect(insertMock).not.toHaveBeenCalled();
  });

  it('fails closed on a payload missing its required field - never queues it', async () => {
    const text = `<starfleet-action type="create_mission">{"priority": "P0"}</starfleet-action>`;
    const results = await parseAndProposeActions(text);
    expect(results[0].success).toBe(false);
    expect(insertMock).not.toHaveBeenCalled();
  });

  it('the success detail text never claims the action was performed', async () => {
    const text = `<starfleet-action type="create_mission">{"title": "New mission"}</starfleet-action>`;
    const [result] = await parseAndProposeActions(text);
    expect(result.detail.toLowerCase()).not.toMatch(/\b(created|registered|logged|dispatched)\b/);
    expect(result.detail).toMatch(/proposed/i);
  });

  it('returns no results for text with no action blocks', async () => {
    const results = await parseAndProposeActions('Just a normal reply, no actions here.');
    expect(results).toEqual([]);
    expect(insertMock).not.toHaveBeenCalled();
  });
});

// ── The execution functions themselves - only ever called from the ────────
// ── approve-action route, verified here in isolation ───────────────────────
describe('execution functions (called only from the approve-action route)', () => {
  it('createMission writes to missions', async () => {
    const result = await createMission({ title: 'Real mission' });
    expect(result.success).toBe(true);
    expect(fromCalls).toContain('missions');
  });

  it('logDecision writes to commander_decisions', async () => {
    const result = await logDecision({ decision: 'Real decision' });
    expect(result.success).toBe(true);
    expect(fromCalls).toContain('commander_decisions');
  });

  it('createHandoff performs no additional write - the queued row already is the handoff', async () => {
    const result = await createHandoff();
    expect(result.success).toBe(true);
    expect(fromCalls).toEqual([]);
  });
});
