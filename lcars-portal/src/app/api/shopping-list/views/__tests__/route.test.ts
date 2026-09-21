import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NextRequest } from 'next/server';

const requireSessionMock = vi.fn();
const listSavedViewsMock = vi.fn();
const createSavedViewMock = vi.fn();

vi.mock('@/lib/supabase-server', () => ({
  requireSession: () => requireSessionMock(),
  createSupabaseServerClient: async () => ({}),
}));

vi.mock('@/lib/shoppingListViewsServer', () => ({
  listSavedViews: (...args: unknown[]) => listSavedViewsMock(...args),
  createSavedView: (...args: unknown[]) => createSavedViewMock(...args),
}));

import { GET, POST } from '../route';

function makeRequest(body?: Record<string, unknown>) {
  return new NextRequest('http://localhost/api/shopping-list/views', {
    method: 'POST',
    body: body ? JSON.stringify(body) : undefined,
  });
}

describe('GET /api/shopping-list/views', () => {
  beforeEach(() => {
    requireSessionMock.mockReset();
    listSavedViewsMock.mockReset();
  });

  it('rejects with 401 when there is no session', async () => {
    requireSessionMock.mockResolvedValue(null);
    const res = await GET();
    expect(res.status).toBe(401);
    expect(listSavedViewsMock).not.toHaveBeenCalled();
  });

  it('returns an explicit empty result, not a bare success with no signal', async () => {
    requireSessionMock.mockResolvedValue({ user: { id: 'captain-1' } });
    listSavedViewsMock.mockResolvedValue({ ok: true, data: [] });
    const res = await GET();
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json).toEqual({ ok: true, data: [], empty: true });
  });

  it('returns populated data with empty: false', async () => {
    requireSessionMock.mockResolvedValue({ user: { id: 'captain-1' } });
    const views = [{ id: 'v1', name: 'Gifts', filters: {}, sort: { field: null, direction: 'asc' }, is_default: false, created_at: 't', updated_at: 't' }];
    listSavedViewsMock.mockResolvedValue({ ok: true, data: views });
    const res = await GET();
    const json = await res.json();
    expect(json).toEqual({ ok: true, data: views, empty: false });
  });

  it('surfaces a backend failure as unavailable, never a fabricated result', async () => {
    requireSessionMock.mockResolvedValue({ user: { id: 'captain-1' } });
    listSavedViewsMock.mockResolvedValue({ ok: false, error: 'unavailable', detail: 'connection refused' });
    const res = await GET();
    expect(res.status).toBe(503);
    const json = await res.json();
    expect(json.ok).toBe(false);
    expect(json.unavailable).toBe(true);
  });

  it('converts a thrown failure into an honest unavailable response, not a raw 500', async () => {
    requireSessionMock.mockResolvedValue({ user: { id: 'captain-1' } });
    listSavedViewsMock.mockRejectedValue(new Error('client is not initialised'));
    const res = await GET();
    expect(res.status).toBe(503);
    const json = await res.json();
    expect(json.unavailable).toBe(true);
  });
});

describe('POST /api/shopping-list/views', () => {
  beforeEach(() => {
    requireSessionMock.mockReset();
    createSavedViewMock.mockReset();
  });

  it('rejects with 401 when there is no session', async () => {
    requireSessionMock.mockResolvedValue(null);
    const res = await POST(makeRequest({ name: 'x' }));
    expect(res.status).toBe(401);
    expect(createSavedViewMock).not.toHaveBeenCalled();
  });

  it('rejects invalid JSON with 400 before touching the DB', async () => {
    requireSessionMock.mockResolvedValue({ user: { id: 'captain-1' } });
    const badReq = new NextRequest('http://localhost/api/shopping-list/views', { method: 'POST', body: '{not json' });
    const res = await POST(badReq);
    expect(res.status).toBe(400);
    expect(createSavedViewMock).not.toHaveBeenCalled();
  });

  it('creates a view and returns 201', async () => {
    requireSessionMock.mockResolvedValue({ user: { id: 'captain-1' } });
    const view = { id: 'v1', name: 'Gifts', filters: {}, sort: { field: null, direction: 'asc' }, is_default: false, created_at: 't', updated_at: 't' };
    createSavedViewMock.mockResolvedValue({ ok: true, data: view });
    const res = await POST(makeRequest({ name: 'Gifts' }));
    expect(res.status).toBe(201);
    const json = await res.json();
    expect(json).toEqual({ ok: true, data: view });
  });

  it('maps duplicate_name to 409', async () => {
    requireSessionMock.mockResolvedValue({ user: { id: 'captain-1' } });
    createSavedViewMock.mockResolvedValue({ ok: false, error: 'duplicate_name', detail: 'already exists' });
    const res = await POST(makeRequest({ name: 'Gifts' }));
    expect(res.status).toBe(409);
  });

  it('maps invalid_input to 400', async () => {
    requireSessionMock.mockResolvedValue({ user: { id: 'captain-1' } });
    createSavedViewMock.mockResolvedValue({ ok: false, error: 'invalid_input', detail: 'name is required' });
    const res = await POST(makeRequest({}));
    expect(res.status).toBe(400);
  });
});
