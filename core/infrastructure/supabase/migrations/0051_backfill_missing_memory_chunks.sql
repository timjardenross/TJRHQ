-- One-time backfill: knowledge_library/documents/[id]/decide/route.ts only
-- copied processing_chunks -> document_chunks for the approved_chunks
-- review tier until this mission's fix -- approved_metadata and
-- approved_summary decisions silently skipped it, leaving those documents
-- in Command Memory but unreachable via vector/semantic search, against
-- the actual point of the Knowledge Library. The forward-looking fix
-- (decide/route.ts) covers every future approval; this backfills the 8
-- documents already approved under the old, narrower behavior. Source rows
-- in processing_chunks are still present for all 8 (confirmed before
-- writing this), so nothing here is reconstructed or guessed -- it's the
-- same copy the decide route would have done at approval time.
--
-- Idempotent: the NOT EXISTS guard means re-running this is a no-op once
-- the backfill has applied once.

insert into document_chunks (document_id, chunk_index, chunk_text, embedding, embedding_model, embedded_at)
select
  pd.memory_document_id,
  pc.chunk_index,
  pc.chunk_text,
  pc.embedding,
  pc.embedding_model,
  pc.embedded_at
from processing_documents pd
join processing_chunks pc on pc.document_id = pd.id
where pd.review_decision in ('approved_metadata', 'approved_summary')
  and pd.memory_document_id is not null
  and not exists (
    select 1 from document_chunks dc where dc.document_id = pd.memory_document_id
  );
