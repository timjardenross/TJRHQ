import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';
import { assignRetentionPolicy } from '@/lib/retentionPolicy';
import { assignCategory } from '@/lib/categoryPropagation';
import type { ReviewDecision, ReviewStatus } from '@/lib/types';

// USS-TJR-MSN-0205D: the ONLY write path from the processing pipeline
// (processing_documents/processing_chunks, MSN-0205C, pre-approval
// staging) into knowledge_documents/document_chunks (existing Command
// Memory / Working Memory pathway). No document enters durable memory any
// other way — every decision here is one explicit Captain-triggered call.
//
// - approve_metadata: knowledge_documents.content is a metadata-only stub
//   (filename/category/tags/source citation), not the full extracted
//   text/summary.
// - approve_summary / approve_chunks: knowledge_documents.content is the
//   reviewed summary.
// All three tiers copy the already-embedded processing_chunks rows into
// document_chunks (no re-embedding — same vector(768)/nomic-embed-text
// shape) so every approved document is retrievable via semantic search
// regardless of tier — the tier only controls what's shown as the
// document's own readable content, never whether it's searchable. (Fixed
// after review: approve_metadata/approve_summary previously skipped this
// step entirely, silently making those documents unreachable via search —
// against the whole point of Command Memory.)
// - reject: no memory write, terminal — records the decision, closes the
//   document out (review_status = 'rejected').
// - needs_review: no memory write, NOT terminal (USS-TJR-MSN-0206J-1) —
//   review_status = 'awaiting_followup', the document stays open for a
//   later decision. Before this phase, `needs_review` was permanently
//   undecidable (the old guard blocked on any non-null review_decision);
//   see migration 0047 for the real deadlock this fixed.

const MEMORY_WRITE_DECISIONS: ReviewDecision[] = ['approved_metadata', 'approved_summary', 'approved_chunks'];
const VALID_DECISIONS: ReviewDecision[] = [...MEMORY_WRITE_DECISIONS, 'rejected', 'needs_review'];
const TERMINAL_REVIEW_STATUSES: ReviewStatus[] = ['resolved', 'rejected'];

function reviewStatusFor(decision: ReviewDecision): ReviewStatus {
  if (decision === 'needs_review') return 'awaiting_followup';
  if (decision === 'rejected') return 'rejected';
  return 'resolved'; // the 3 MEMORY_WRITE_DECISIONS
}

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } },
) {
  const id = decodeURIComponent(params.id ?? '').trim();
  if (!id) {
    return NextResponse.json({ error: 'Document ID required' }, { status: 400 });
  }

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
  const decidedBy = typeof body.decided_by === 'string' && body.decided_by.trim() ? body.decided_by.trim() : 'Captain';

  try {
    const supabase = await createSupabaseServerClient();

    const { data: doc, error: fetchErr } = await supabase
      .from('processing_documents')
      .select('*')
      .eq('id', id)
      .maybeSingle();
    if (fetchErr) throw fetchErr;
    if (!doc) {
      return NextResponse.json({ error: 'Document not found', id }, { status: 404 });
    }
    if (doc.status !== 'awaiting_review') {
      return NextResponse.json(
        { error: 'Document is not awaiting review', current_status: doc.status },
        { status: 409 },
      );
    }
    // USS-TJR-MSN-0206J-1: only 'resolved' (approved into memory) and
    // 'rejected' are terminal. A document currently 'awaiting_followup'
    // (a prior 'needs_review' decision) — or one decided before this phase
    // existed and never backfilled a review_status — remains open.
    if (doc.review_status && TERMINAL_REVIEW_STATUSES.includes(doc.review_status)) {
      return NextResponse.json(
        { error: 'Document already resolved', existing_decision: doc.review_decision, review_status: doc.review_status },
        { status: 409 },
      );
    }

    const now = new Date().toISOString();
    let memoryDocumentId: string | null = null;

    if (MEMORY_WRITE_DECISIONS.includes(decision)) {
      const content = decision === 'approved_metadata'
        ? `[Metadata-only record] ${doc.filename} — category: ${doc.category ?? 'Unclassified'}` +
          `${doc.tags?.length ? `, tags: ${doc.tags.join(', ')}` : ''}. Source: ${doc.source_path}.`
        : (doc.summary ?? `[No summary available] ${doc.filename}`);

      // USS-TJR-MSN-0206D: retention policy assignment automation — every
      // document entering Command Memory gets classified at the moment of
      // approval, not left unclassified until a future backfill.
      const retention = assignRetentionPolicy('Personal Archive', doc.category ?? null, new Date());
      // USS-TJR-MSN-0206J-2: category propagation — Command Memory's own
      // 8-value taxonomy, mapped from the processing_documents classifier
      // category (mirrors migration 0048's backfill for existing rows).
      const memoryCategory = assignCategory('Personal Archive', doc.category ?? null);

      // Idempotency: a prior attempt on this exact document may already
      // have inserted into knowledge_documents and even copied its chunks,
      // then failed on a *later* step (e.g. the closing processing_documents
      // update below) — there's no single transaction wrapping this whole
      // route, so that earlier work is already durable. Without this check,
      // a retry re-attempts the insert and dies on knowledge_documents'
      // source_path unique constraint, permanently stuck. Reuse the
      // existing row instead of colliding with it.
      const { data: existingMemRow, error: existingMemErr } = await supabase
        .from('knowledge_documents')
        .select('id')
        .eq('source_path', doc.source_path)
        .maybeSingle();
      if (existingMemErr) throw existingMemErr;

      if (existingMemRow) {
        memoryDocumentId = existingMemRow.id;
      } else {
        const { data: memRow, error: memErr } = await supabase
          .from('knowledge_documents')
          .insert({
            title: doc.filename,
            source_path: doc.source_path,
            document_type: 'Personal Archive',
            category: memoryCategory,
            content,
            tags: doc.tags ?? [],
            metadata: {
              category: doc.category,
              sensitivity: doc.sensitivity,
              approved_via: decision,
              processing_document_id: doc.id,
              original_source_name: doc.source_name,
            },
            retention_policy: retention.retention_policy,
            expiry_date: retention.expiry_date,
            archive_status: retention.archive_status,
            review_due_date: retention.review_due_date,
          })
          .select('id')
          .single();
        if (memErr) throw memErr;
        memoryDocumentId = memRow.id;
      }

      // Copy chunks/embeddings for every approve tier, not just
      // approved_chunks — see the comment block above this function. Skip
      // if this memory row already has chunks (a genuine prior
      // approved_chunks run, or the row just reused above) — otherwise a
      // retry would duplicate every chunk.
      const { count: existingChunkCount, error: chunkCountErr } = await supabase
        .from('document_chunks')
        .select('id', { count: 'exact', head: true })
        .eq('document_id', memoryDocumentId);
      if (chunkCountErr) throw chunkCountErr;

      if (!existingChunkCount) {
        const { data: chunks, error: chunksErr } = await supabase
          .from('processing_chunks')
          .select('chunk_index, chunk_text, embedding, embedding_model, embedded_at')
          .eq('document_id', doc.id)
          .order('chunk_index', { ascending: true });
        if (chunksErr) throw chunksErr;

        if (chunks && chunks.length > 0) {
          const rows = chunks.map((c) => ({
            document_id: memoryDocumentId,
            chunk_index: c.chunk_index,
            chunk_text: c.chunk_text,
            embedding: c.embedding,
            embedding_model: c.embedding_model,
            embedded_at: c.embedded_at,
          }));
          const { error: insertChunksErr } = await supabase.from('document_chunks').insert(rows);
          if (insertChunksErr) throw insertChunksErr;
        }
      }
    }

    const reviewStatus = reviewStatusFor(decision);
    const historyEntry = {
      decision, decided_by: decidedBy, reason, at: now,
      memory_document_id: memoryDocumentId,
    };
    const reviewHistory = [...(Array.isArray(doc.review_history) ? doc.review_history : []), historyEntry];

    const { error: updateErr } = await supabase
      .from('processing_documents')
      .update({
        review_decision: decision,
        review_decided_at: now,
        review_decided_by: decidedBy,
        review_reason: reason,
        review_status: reviewStatus,
        review_history: reviewHistory,
        memory_document_id: memoryDocumentId,
      })
      .eq('id', id);
    if (updateErr) throw updateErr;

    return NextResponse.json({
      id,
      decision,
      decided_by: decidedBy,
      reason,
      review_status: reviewStatus,
      memory_document_id: memoryDocumentId,
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Decision failed', detail }, { status: 500 });
  }
}
