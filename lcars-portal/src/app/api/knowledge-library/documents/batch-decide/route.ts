import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { decideDocument, VALID_DECISIONS } from '@/lib/knowledgeLibraryDecide';
import type { ReviewDecision } from '@/lib/types';

// MSN-0331 — Knowledge Review Backlog Activation. 795 documents sitting
// at awaiting_review one-at-a-time was the real throughput bottleneck
// this mission names; this route is the fix. Reuses decideDocument()
// (lib/knowledgeLibraryDecide.ts) exactly, sequentially per id — same
// idempotency/terminal-status guards as the single-document route, just
// applied to many documents in one Captain action instead of one.
//
// Sequential, not Promise.all: each decideDocument() call does a real
// multi-step write (processing_documents update, possibly a
// knowledge_documents insert + document_chunks copy + an event emit) —
// running many of those concurrently against the same Supabase project
// has no benefit here (this isn't a slow external call, it's already-fast
// DB writes) and avoids any risk of interleaved writes on shared tables.
// A batch of a few hundred completes in a few seconds either way.
//
// No reasoning/confidence logic touched — this endpoint is a Captain
// applying ONE decision they already made to MANY documents, not an
// automated decision of any kind.

const MAX_BATCH = 200;

export async function POST(request: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  let body: Record<string, unknown> = {};
  try { body = await request.json(); } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }

  const ids = Array.isArray(body.ids) ? body.ids.filter((v): v is string => typeof v === 'string' && v.trim().length > 0) : [];
  if (ids.length === 0) {
    return NextResponse.json({ error: 'ids (non-empty array of document IDs) is required' }, { status: 400 });
  }
  if (ids.length > MAX_BATCH) {
    return NextResponse.json({ error: `Batch too large — max ${MAX_BATCH} documents per call, got ${ids.length}` }, { status: 400 });
  }

  const decision = body.decision as ReviewDecision;
  if (!VALID_DECISIONS.includes(decision)) {
    return NextResponse.json({ error: 'Invalid decision', valid_decisions: VALID_DECISIONS }, { status: 400 });
  }
  const reason = typeof body.reason === 'string' ? body.reason.trim() : null;
  const decidedBy = typeof body.decided_by === 'string' && body.decided_by.trim() ? body.decided_by.trim() : 'Captain';

  const supabase = await createSupabaseServerClient();

  const succeeded: string[] = [];
  const failed: { id: string; error: string; detail: string }[] = [];

  for (const id of ids) {
    try {
      const outcome = await decideDocument(supabase, id, decision, reason, decidedBy);
      if (outcome.ok) {
        succeeded.push(id);
      } else {
        failed.push({ id, error: outcome.error, detail: outcome.detail });
      }
    } catch (err) {
      failed.push({ id, error: 'exception', detail: err instanceof Error ? err.message : String(err) });
    }
  }

  return NextResponse.json({
    decision,
    requested: ids.length,
    succeeded: succeeded.length,
    failed: failed.length,
    succeeded_ids: succeeded,
    failures: failed,
  });
}
