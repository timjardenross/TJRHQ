import { beforeEach, describe, expect, it, vi } from 'vitest';

const approveDecideItem = vi.fn();
const holdDecideItem = vi.fn();
const undoDecideItem = vi.fn();
vi.mock('@/lib/decide', () => ({
  approveDecideItem: (...a: unknown[]) => approveDecideItem(...a),
  holdDecideItem: (...a: unknown[]) => holdDecideItem(...a),
  undoDecideItem: (...a: unknown[]) => undoDecideItem(...a),
  fetchDecideQueue: vi.fn(),
}));

import { approveHqDecision, buildPackage, declineHqDecision, deferHqDecision, mapDecideItem } from '../decisions';
import { actOnBrief, actOnDoc, actOnImprovement, briefDecision } from '../decisionSources';
import type { DecideItem } from '@/lib/decide';
import type { HqDecision } from '../model';

const eng = (over: Partial<DecideItem> = {}): DecideItem => ({
  id: 'eng:1', source: 'engineering', rawId: '1', question: 'Approve build request "Fix link"?', reasoning: 'Status: awaiting_review.',
  domainTag: 'Engineering', undoAvailable: true, priorStatus: 'awaiting_review', actionType: null, _sortRank: 60, ...over,
});

beforeEach(() => { vi.clearAllMocks(); vi.unstubAllGlobals(); });

describe('mapping onto HQ explanation fields', () => {
  it('states what approval does, and never invents consequences for a build request', () => {
    const d = mapDecideItem(eng());
    expect(d.source).toBe('engineering');
    expect(d.ifApprove).toMatch(/undo/i);
    expect(d.need).toMatch(/policy/i);
    expect(d.routine).toBe(true);
  });
  it('AI proposals are never routine and say they cannot be undone', () => {
    const d = mapDecideItem(eng({ actionType: 'create_mission', undoAvailable: false }));
    expect(d.source).toBe('ai-action');
    expect(d.routine).toBe(false);
    expect(d.undoable).toBe(false);
  });
  it('blocked items are not routine', () => {
    expect(mapDecideItem(eng({ _sortRank: 95 })).routine).toBe(false);
  });
});

describe('routine package', () => {
  const lines = (n: number) => Array.from({ length: n }, (_, i) => mapDecideItem(eng({ id: `eng:${i}`, rawId: String(i) })));
  it('needs at least three routine lines', () => {
    expect(buildPackage(lines(2)).pkg).toBeNull();
    expect(buildPackage(lines(3)).pkg?.lines).toHaveLength(3);
  });
  it('never packages judgement calls or irreversible items', () => {
    const mixed = [...lines(3), mapDecideItem(eng({ id: 'eng:x', actionType: 'publish_content', undoAvailable: false }))];
    const { pkg, rest } = buildPackage(mixed);
    expect(pkg?.lines).toHaveLength(3);
    expect(rest.map((d) => d.source)).toEqual(['ai-action']);
  });
});

describe('approvals cannot run twice', () => {
  const reply = (status: number, body: unknown) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
  const lastCall = (fetchMock: ReturnType<typeof vi.fn>) => {
    const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
    return { url: url as string, body: JSON.parse((init as RequestInit).body as string) };
  };

  it('a build request is approved by the SERVER route with the status it was loaded with', async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(200, { ok: true }));
    vi.stubGlobal('fetch', fetchMock);
    const r = await approveHqDecision(mapDecideItem(eng()));
    expect(r.ok).toBe(true);
    const c = lastCall(fetchMock);
    expect(c.url).toBe('/api/hq/decisions/build-request/1');
    expect(c.body).toMatchObject({ action: 'approve', expectedStatus: 'awaiting_review' });
    expect(approveDecideItem).not.toHaveBeenCalled(); // no client-side write path
  });
  it('a decision already made elsewhere is reported, not repeated', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(409, { error: 'already_decided', currentStatus: 'approved' })));
    const r = await approveHqDecision(mapDecideItem(eng()));
    expect(r).toMatchObject({ ok: false, alreadyDecided: true });
    expect(r.error).toMatch(/already decided/i);
  });
  it('undo goes through the server route and restores the loaded status', async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(200, { ok: true }));
    vi.stubGlobal('fetch', fetchMock);
    const r = await approveHqDecision(mapDecideItem(eng()));
    expect(r.undo).toBeTypeOf('function');
    await r.undo!();
    expect(lastCall(fetchMock).body).toMatchObject({ action: 'undo', restoreStatus: 'awaiting_review' });
  });
  it('an AI-proposed action is executed by the existing approve-action route, with the guard', async () => {
    approveDecideItem.mockResolvedValue({ ok: false, alreadyDecided: true, error: 'Not eligible' });
    const r = await approveHqDecision(mapDecideItem(eng({ actionType: 'create_mission', undoAvailable: false })));
    expect(approveDecideItem).toHaveBeenCalledWith(expect.objectContaining({ rawId: '1' }), { guardStatus: true });
    expect(r).toMatchObject({ ok: false, alreadyDecided: true });
  });
  it('a double click while the first is in flight is ignored', async () => {
    let release: (v: unknown) => void = () => {};
    const fetchMock = vi.fn().mockReturnValue(new Promise((res) => { release = res; }));
    vi.stubGlobal('fetch', fetchMock);
    const d = mapDecideItem(eng());
    const first = approveHqDecision(d);
    const second = await approveHqDecision(d);
    expect(second).toMatchObject({ ok: false, error: 'Already in progress.' });
    release(reply(200, { ok: true }));
    await first;
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it('decline is applied by the server route against the loaded status', async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(409, { error: 'already_decided' }));
    vi.stubGlobal('fetch', fetchMock);
    const r = await declineHqDecision(mapDecideItem(eng()));
    expect(lastCall(fetchMock).body).toMatchObject({ action: 'decline', expectedStatus: 'awaiting_review' });
    expect(r.alreadyDecided).toBe(true);
  });
  it('defer writes nothing to a source system other than the existing ledger for build requests', async () => {
    holdDecideItem.mockResolvedValue({ ok: true });
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    await deferHqDecision(mapDecideItem(eng()));
    expect(holdDecideItem).toHaveBeenCalledTimes(1);
    expect(fetchMock).not.toHaveBeenCalled();
    const brief = briefDecision({ brief_id: 'B1', generated_at: new Date().toISOString(), approval_status: 'QA_PASSED', executive_snapshot: 's', overall_risk: 'AMBER' }) as HqDecision;
    holdDecideItem.mockClear();
    expect((await deferHqDecision(brief)).ok).toBe(true);
    expect(holdDecideItem).not.toHaveBeenCalled();
  });
});

describe('other approval sources', () => {
  const jsonResp = (status: number, body: unknown) => ({ ok: status >= 200 && status < 300, status, json: async () => body });

  it('brief gate: only recent briefs in an actionable state become decisions', () => {
    const now = new Date().toISOString();
    const old = new Date(Date.now() - 10 * 86_400_000).toISOString();
    expect(briefDecision({ brief_id: 'a', generated_at: now, approval_status: 'QA_PASSED', executive_snapshot: null, overall_risk: null })?.undoable).toBe(false);
    expect(briefDecision({ brief_id: 'b', generated_at: old, approval_status: 'IN_REVIEW', executive_snapshot: null, overall_risk: null })).toBeNull();
    expect(briefDecision({ brief_id: 'c', generated_at: now, approval_status: 'PUBLISHED', executive_snapshot: null, overall_risk: null })).toBeNull();
  });
  it('brief gate: never publishes if the brief changed since it was loaded', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResp(200, { brief: { approval_status: 'PUBLISHED' } }));
    vi.stubGlobal('fetch', fetchMock);
    const r = await actOnBrief({ kind: 'brief', briefId: 'B1', status: 'QA_PASSED' });
    expect(r).toMatchObject({ ok: false, alreadyDecided: true });
    expect(fetchMock).toHaveBeenCalledTimes(1); // the status read only, no POST
  });
  it('brief gate: publishes through the existing governed action when status still matches', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResp(200, { brief: { approval_status: 'QA_PASSED' } }))
      .mockResolvedValueOnce(jsonResp(200, { ok: true }));
    vi.stubGlobal('fetch', fetchMock);
    const r = await actOnBrief({ kind: 'brief', briefId: 'B1', status: 'QA_PASSED' });
    expect(r.ok).toBe(true);
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe('/api/intelligence-workbench/action');
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ action: 'brief.publish', payload: { brief_id: 'B1' } });
  });
  it('knowledge review: a 409 from the server means already decided', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResp(409, { error: 'Document is not awaiting review' })));
    expect(await actOnDoc({ kind: 'doc', docId: 'd1' }, 'approved_summary')).toMatchObject({ ok: false, alreadyDecided: true });
  });
  it('improvements: re-checks state first and refuses to decide twice', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResp(200, { opportunities: [] }));
    vi.stubGlobal('fetch', fetchMock);
    const r = await actOnImprovement({ kind: 'improvement', opportunityId: 'o1', mayApproveHere: true }, 'approve_improvement');
    expect(r).toMatchObject({ ok: false, alreadyDecided: true });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it('improvements: mission-only classes are never approved from HQ', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const r = await actOnImprovement({ kind: 'improvement', opportunityId: 'o1', mayApproveHere: false }, 'approve_improvement');
    expect(r.ok).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('a brief cannot be declined from HQ', async () => {
    const d = briefDecision({ brief_id: 'B1', generated_at: new Date().toISOString(), approval_status: 'QA_PASSED', executive_snapshot: null, overall_risk: null }) as HqDecision;
    expect((await declineHqDecision(d)).ok).toBe(false);
  });
});

describe('readable decision titles', () => {
  it('uses the real title, not the question wrapper', () => {
    expect(mapDecideItem(eng({ question: 'Approve build request "Fix link"?' })).title).toBe('Fix link');
    expect(mapDecideItem(eng({ question: 'Approve mission creation: "Review contracts"?', actionType: 'create_mission' })).title).toBe('Create mission: Review contracts');
    expect(mapDecideItem(eng({ question: 'Approve decision log: "Choose X"?', actionType: 'log_decision' })).title).toBe('Log decision: Choose X');
  });
});

describe('title prefix is not doubled', () => {
  it('keeps a title that already carries the action prefix', () => {
    expect(mapDecideItem(eng({ question: 'Approve mission creation: "Create mission: Review"?', actionType: 'create_mission' })).title).toBe('Create mission: Review');
  });
});
