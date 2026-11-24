import { beforeEach, describe, expect, it, vi } from 'vitest';

const captureItem = vi.fn();
const promoteCaptureToMission = vi.fn();
vi.mock('@/lib/capture', () => ({
  captureItem: (...a: unknown[]) => captureItem(...a),
  promoteCaptureToMission: (...a: unknown[]) => promoteCaptureToMission(...a),
}));

import { ASK_AVAILABLE, RESEARCH_RUNNER_CONNECTED, hqCapture, hqMission, hqResearch, withContext } from '../actions';

beforeEach(() => vi.clearAllMocks());

describe('HQ contextual actions reuse the existing capture pipeline', () => {
  it('attaches what the user was viewing, without a schema change', () => {
    expect(withContext('Idea', { label: 'Incident X', href: '/hq/intelligence/1' })).toContain('Incident X (/hq/intelligence/1)');
    expect(withContext('Idea', null)).toContain('Captured from HQ');
  });
  it('capture goes through captureItem on the shared floating-capture channel', async () => {
    captureItem.mockResolvedValue({ ok: true, id: 'c1' });
    await hqCapture('Note', { label: 'L' });
    expect(captureItem).toHaveBeenCalledWith(expect.stringContaining('Note'), 'note', undefined, 'portal-floating-capture');
  });
  it('research is a mission-backed work item created through the existing missions API, and no runner is connected', async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ mission: { mission_id: 'MSN-9' } }) });
    vi.stubGlobal('fetch', f);
    const r = await hqResearch('Who depends on X?', { label: 'Incident Y' });
    expect(r).toEqual({ ok: true, missionId: 'MSN-9' });
    const [url, init] = f.mock.calls[0];
    expect(url).toBe('/api/missions');
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body).toMatchObject({ title: 'Research: Who depends on X?', status: 'Idea' });
    expect(body.description).toContain('Incident Y');
    expect(captureItem).not.toHaveBeenCalled();
    expect(RESEARCH_RUNNER_CONNECTED).toBe(false);
    expect(ASK_AVAILABLE).toBe(true);
  });
  it('a failed research request is reported, not swallowed', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({ error: 'Failed to create' }) }));
    expect(await hqResearch('q')).toMatchObject({ ok: false, error: 'Failed to create' });
  });
  it('a mission is a captured candidate promoted through the existing route, once', async () => {
    captureItem.mockResolvedValue({ ok: true, id: 'c1' });
    promoteCaptureToMission.mockResolvedValue({ ok: true, mission_id: 'MC-1' });
    const r = await hqMission('Do it');
    expect(r).toMatchObject({ ok: true, missionId: 'MC-1' });
    expect(captureItem).toHaveBeenCalledTimes(1);
    expect(promoteCaptureToMission).toHaveBeenCalledTimes(1);
    expect(promoteCaptureToMission).toHaveBeenCalledWith('c1');
  });
  it('if promotion fails the idea stays captured and the result says so', async () => {
    captureItem.mockResolvedValue({ ok: true, id: 'c1' });
    promoteCaptureToMission.mockResolvedValue({ ok: false, error: 'Command Centre unreachable' });
    expect(await hqMission('Do it')).toMatchObject({ ok: false, partial: true, captureId: 'c1' });
  });
  it('does not promote when capture itself failed', async () => {
    captureItem.mockResolvedValue({ ok: false, error: 'nope' });
    expect((await hqMission('Do it')).ok).toBe(false);
    expect(promoteCaptureToMission).not.toHaveBeenCalled();
  });
});
