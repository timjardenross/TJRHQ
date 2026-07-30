import type { SupabaseClient } from '@supabase/supabase-js';
import { assignRetentionPolicy } from '@/lib/retentionPolicy';
import { assignCategory } from '@/lib/categoryPropagation';
import { publishEventServerSide } from '@/lib/core-events';
import type { ReviewDecision, ReviewStatus } from '@/lib/types';

// MSN-0331: extracted verbatim from the single-document decide route
// (USS-TJR-MSN-0205D) so a new batch-decide endpoint can reuse the exact
// same logic — including its idempotency guard and the MSN-0206J-1
// terminal-status fix — rather than duplicating (and risking drifting
// from) carefully-reasoned, already-bug-fixed behaviour. No logic
// changed here, only moved and given a typed result instead of thrown
// HTTP responses, so both the single and batch routes can map outcomes
// to their own appropriate response shape.

const MEMORY_WRITE_DECISIONS: ReviewDecision[] = ['approved_metadata', 'approved_summary', 'approved_chunks'];
export const VALID_DECISIONS: ReviewDecision[] = [...MEMORY_WRITE_DECISIONS, 'rejected', 'needs_review'];
const TERMINAL_REVIEW_STATUSES: ReviewStatus[] = ['resolved', 'rejected'];

function reviewStatusFor(decision: ReviewDecision): ReviewStatus {
  if (decision === 'needs_review') return 'awaiting_followup';
  if (decision === 'rejected') return 'rejected';
  return 'resolved'; // the 3 MEMORY_WRITE_DECISIONS
}

export type DecideOutcome =
  | { ok: true; id: string; decision: ReviewDecision; decided_by: string; reason: string | null; review_status: ReviewStatus; memory_document_id: string | null }
  | { ok: false; id: string; error: 'not_found' | 'not_awaiting_review' | 'already_resolved' | 'invalid_decision'; detail: string };

export async function decideDocument(
  supabase: SupabaseClient,
  id: string,
  decision: ReviewDecision,
  reason: string | null,
  decidedBy: string,
): Promise<DecideOutcome> {
  if (!VALID_DECISIONS.includes(decision)) {
    return { ok: false, id, error: 'invalid_decision', detail: 'Invalid decision' };
  }

  const { data: doc, error: fetchErr } = await supabase
    .from('processing_documents')
    .select('*')
    .eq('id', id)
    .maybeSingle();
  if (fetchErr) throw fetchErr;
  if (!doc) {
    return { ok: false, id, error: 'not_found', detail: 'Document not found' };
  }
  if (doc.status !== 'awaiting_review') {
    return { ok: false, id, error: 'not_awaiting_review', detail: `Document is not awaiting review (current_status: ${doc.status})` };
  }
  // USS-TJR-MSN-0206J-1: only 'resolved' (approved into memory) and
  // 'rejected' are terminal. A document currently 'awaiting_followup'
  // (a prior 'needs_review' decision) — or one decided before this phase
  // existed and never backfilled a review_status — remains open.
  if (doc.review_status && TERMINAL_REVIEW_STATUSES.includes(doc.review_status)) {
    return { ok: false, id, error: 'already_resolved', detail: `Document already resolved (existing_decision: ${doc.review_decision}, review_status: ${doc.review_status})` };
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
            // MSN-0332: real provenance gap found by audit -- these were
            // recorded on processing_documents but never copied into the
            // memory row itself, leaving a knowledge_documents row unable
            // to answer "who approved this, when, and why" on its own
            // (only via a join back to processing_documents, which stays
            // possible via processing_document_id above, but the mission's
            // own "no orphan memory" / provenance requirement asks for
            // these to travel with the memory record directly).
            review_reason: reason,
            review_decided_by: decidedBy,
            review_decided_at: now,
            // The classifier's own recommendation that originally informed
            // this decision -- also previously discarded on approval.
            memory_recommendation: doc.memory_recommendation ?? null,
            ocr_used: doc.ocr_used ?? false,
            ocr_engine: doc.ocr_engine ?? null,
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
    // approved_chunks — see the single-document route's own comment
    // block for why. Skip if this memory row already has chunks (a
    // genuine prior approved_chunks run, or the row just reused above)
    // — otherwise a retry would duplicate every chunk.
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

  // MSN-0330: canonical Captain Brief pipeline event — moved here
  // unchanged from the single-document route so the batch route gets
  // it too, for free, without a second copy of this call.
  // Service-role wrapper: core_events RLS denies the anon/SSR `supabase`
  // client used above for the processing_documents update (silent-failure
  // bug, fixed) -- must not reuse it here.
  await publishEventServerSide({
    eventType: 'knowledge.document_review_decided',
    domain: 'knowledge',
    source: 'lcars-portal:knowledge-library-decide',
    linkedDocuments: memoryDocumentId ? [memoryDocumentId] : [],
    recommendedAction: `${decision} (${doc.filename})`,
    metrics: { review_status: reviewStatus, decision },
  });

  return {
    ok: true, id, decision, decided_by: decidedBy, reason,
    review_status: reviewStatus, memory_document_id: memoryDocumentId,
  };
}
