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
  it('research is a filed request, and the UI knows no runner is connected', async () => {
    captureItem.mockResolvedValue({ ok: true, id: 'c1' });
    await hqResearch('Who depends on X?');
    expect(captureItem.mock.calls[0][0]).toMatch(/^Research request:/);
    expect(RESEARCH_RUNNER_CONNECTED).toBe(false);
    expect(ASK_AVAILABLE).toBe(false);
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
