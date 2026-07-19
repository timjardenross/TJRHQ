import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { decideDocument, VALID_DECISIONS } from '@/lib/knowledgeLibraryDecide';
import type { ReviewDecision } from '@/lib/types';

// USS-TJR-MSN-0205D: the ONLY write path from the processing pipeline
// (processing_documents/processing_chunks, MSN-0205C, pre-approval
// staging) into knowledge_documents/document_chunks (existing Command
// Memory / Working Memory pathway). No document enters durable memory any
// other way — every decision here is one explicit Captain-triggered call.
//
// MSN-0331: the actual decision logic now lives in
// lib/knowledgeLibraryDecide.ts (moved verbatim, unchanged), shared with
// the new batch-decide route — this file is now a thin HTTP wrapper that
// maps the shared function's typed outcome onto the exact same response
// shapes/status codes this route already returned, so no existing caller
// (the page's own `decide()` callback) sees any behaviour change.
//
// - approve_metadata: knowledge_documents.content is a metadata-only stub
//   (filename/category/tags/source citation), not the full extracted
//   text/summary.
// - approve_summary / approve_chunks: knowledge_documents.content is the
//   reviewed summary.
// All three tiers copy the already-embedded processing_chunks rows into
// document_chunks so every approved document is retrievable via semantic
// search regardless of tier.
// - reject: no memory write, terminal.
// - needs_review: no memory write, NOT terminal (USS-TJR-MSN-0206J-1).

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } },
) {
  const id = decodeURIComponent(params.id ?? '').trim();
  if (!id) {
    return NextResponse.json({ error: 'Document ID required' }, { status: 400 });
  }

  // decided_by must come from the real session, not a client-supplied body
  // field (WORKBENCH-REVIEW.md Medium finding, 2026-07-18: any bot-secret
  // holder could set it). RLS on processing_documents.UPDATE already
  // requires `authenticated`, so this doesn't newly restrict who can
  // decide - it makes the record of who did trustworthy.
  const session = await requireSession();
  if (!session?.user?.email) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const decidedBy = session.user.email;

  let body: Record<string, unknown> = {};
  try { body = await request.json(); } catch { /* empty body — decision is still required below */ }

  const decision = body.decision as ReviewDecision;
  if (!VALID_DECISIONS.includes(decision)) {
    return NextResponse.json(
      { error: 'Invalid decision', valid_decisions: VALID_DECISIONS },
      { status: 400 },
    );
  }
  const reason = typeof body.reason === 'string' ? body.reason.trim() : null;

  try {
    const supabase = await createSupabaseServerClient();
    const outcome = await decideDocument(supabase, id, decision, reason, decidedBy);

    if (!outcome.ok) {
      if (outcome.error === 'not_found') {
        return NextResponse.json({ error: 'Document not found', id }, { status: 404 });
      }
      if (outcome.error === 'not_awaiting_review' || outcome.error === 'already_resolved') {
        return NextResponse.json({ error: outcome.detail }, { status: 409 });
      }
      return NextResponse.json({ error: outcome.detail, valid_decisions: VALID_DECISIONS }, { status: 400 });
    }

    return NextResponse.json({
      id: outcome.id,
      decision: outcome.decision,
      decided_by: outcome.decided_by,
      reason: outcome.reason,
      review_status: outcome.review_status,
      memory_document_id: outcome.memory_document_id,
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Decision failed', detail }, { status: 500 });
  }
}
