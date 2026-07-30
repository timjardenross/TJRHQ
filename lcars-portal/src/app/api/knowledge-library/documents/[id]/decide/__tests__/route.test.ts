import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NextRequest } from 'next/server';

// WORKBENCH-REVIEW.md Medium finding (2026-07-18): decided_by must come
// from the real session, not a client-supplied body field. Locks in the
// 401 gate and that decidedBy is bound to session.user.email regardless
// of what the request body claims.

const requireSessionMock = vi.fn();
const decideDocumentMock = vi.fn();

vi.mock('@/lib/supabase-server', () => ({
  requireSession: () => requireSessionMock(),
  createSupabaseServerClient: async () => ({}),
}));

vi.mock('@/lib/knowledgeLibraryDecide', () => ({
  decideDocument: (...args: unknown[]) => decideDocumentMock(...args),
  VALID_DECISIONS: ['approved_chunks', 'approved_metadata', 'needs_review', 'rejected'],
}));

import { POST } from '../route';

function makeRequest(body: Record<string, unknown>) {
  return new NextRequest('http://localhost/api/knowledge-library/documents/doc-1/decide', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

describe('POST /api/knowledge-library/documents/[id]/decide', () => {
  beforeEach(() => {
    requireSessionMock.mockReset();
    decideDocumentMock.mockReset();
  });

  it('rejects with 401 when there is no session', async () => {
    requireSessionMock.mockResolvedValue(null);
    const res = await POST(makeRequest({ decision: 'approved_chunks' }), { params: { id: 'doc-1' } });
    expect(res.status).toBe(401);
    expect(decideDocumentMock).not.toHaveBeenCalled();
  });

  it('rejects with 400 for an invalid decision', async () => {
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    const res = await POST(makeRequest({ decision: 'not-a-real-decision' }), { params: { id: 'doc-1' } });
    expect(res.status).toBe(400);
    expect(decideDocumentMock).not.toHaveBeenCalled();
  });

  it('binds decided_by to session.user.email, not a body field', async () => {
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    decideDocumentMock.mockResolvedValue({
      ok: true,
      id: 'doc-1',
      decision: 'approved_chunks',
      decided_by: 'captain@example.com',
      reason: null,
      review_status: 'resolved',
      memory_document_id: 'mem-1',
    });

    const res = await POST(
      makeRequest({ decision: 'approved_chunks', decided_by: 'someone-else@example.com' }),
      { params: { id: 'doc-1' } },
    );

    expect(res.status).toBe(200);
    expect(decideDocumentMock).toHaveBeenCalledWith(
      expect.anything(),
      'doc-1',
      'approved_chunks',
      null,
      'captain@example.com',
    );
    const json = await res.json();
    expect(json.decided_by).toBe('captain@example.com');
  });

  it('returns 404 when decideDocument reports not_found', async () => {
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    decideDocumentMock.mockResolvedValue({ ok: false, error: 'not_found', detail: 'no such document' });
    const res = await POST(makeRequest({ decision: 'rejected' }), { params: { id: 'missing' } });
    expect(res.status).toBe(404);
  });

  it('returns 409 when decideDocument reports already_resolved', async () => {
    requireSessionMock.mockResolvedValue({ user: { email: 'captain@example.com' } });
    decideDocumentMock.mockResolvedValue({ ok: false, error: 'already_resolved', detail: 'already decided' });
    const res = await POST(makeRequest({ decision: 'rejected' }), { params: { id: 'doc-1' } });
    expect(res.status).toBe(409);
  });
});
