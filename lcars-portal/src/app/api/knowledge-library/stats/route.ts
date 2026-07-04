import { NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';
import type { KnowledgeLibraryStats } from '@/lib/types';

// USS-TJR-MSN-0205D: dashboard card counts for the Knowledge Library.
// `status` is the processing pipeline's own lifecycle (0205C, unchanged);
// `review_decision` is the Captain's separate approval-queue outcome.
//
// Two independent groupings, not one flat list (fixed after the original
// single-row layout read as "Awaiting Review" being on the Captain when it
// wasn't, and "Processed" being ambiguous — it counted every
// status='awaiting_review' row regardless of review_decision, which reads
// like "done" when it may still need a decision):
//   - Pipeline Health: is the system working (nothing here is the
//     Captain's to act on).
//   - Your Review Queue: what actually needs a Captain decision.
// TERMINAL_STATUSES mirrors the processing_documents_status_check
// constraint (migration 0049) — anything not in it is still moving
// through the pipeline or queued for retry.
const TERMINAL_STATUSES = ['awaiting_review', 'excluded', 'failed', 'permanently_failed'];

export async function GET() {
  try {
    const supabase = await createSupabaseServerClient();

    const [total, inProgress, ocrRequired, failed, needsYourReview, memoryApproved, needsFollowup, rejected] =
      await Promise.all([
        supabase.from('processing_documents').select('id', { count: 'exact', head: true }),
        supabase.from('processing_documents').select('id', { count: 'exact', head: true })
          .not('status', 'in', `(${TERMINAL_STATUSES.join(',')})`),
        supabase.from('processing_documents').select('id', { count: 'exact', head: true })
          .eq('status', 'ocr_required'),
        // Both retriable and given-up failures count toward pipeline
        // health — a permanently_failed document shouldn't just vanish
        // from every tile.
        supabase.from('processing_documents').select('id', { count: 'exact', head: true })
          .in('status', ['failed', 'permanently_failed']),
        supabase.from('processing_documents').select('id', { count: 'exact', head: true })
          .eq('status', 'awaiting_review').is('review_decision', null),
        supabase.from('processing_documents').select('id', { count: 'exact', head: true })
          .in('review_decision', ['approved_metadata', 'approved_summary', 'approved_chunks']),
        // USS-TJR-MSN-0206J-1: documents marked 'needs_review' that are
        // still open (review_status = 'awaiting_followup') — the queue
        // that was previously invisible/unresolvable.
        supabase.from('processing_documents').select('id', { count: 'exact', head: true })
          .eq('review_status', 'awaiting_followup'),
        supabase.from('processing_documents').select('id', { count: 'exact', head: true })
          .eq('review_decision', 'rejected'),
      ]);

    for (const r of [total, inProgress, ocrRequired, failed, needsYourReview, memoryApproved, needsFollowup, rejected]) {
      if (r.error) throw r.error;
    }

    const stats: KnowledgeLibraryStats = {
      total_documents: total.count ?? 0,
      in_progress: inProgress.count ?? 0,
      ocr_required: ocrRequired.count ?? 0,
      failed_documents: failed.count ?? 0,
      needs_your_review: needsYourReview.count ?? 0,
      memory_approved: memoryApproved.count ?? 0,
      needs_followup: needsFollowup.count ?? 0,
      rejected: rejected.count ?? 0,
    };

    return NextResponse.json(stats);
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Failed to load knowledge library stats', detail }, { status: 500 });
  }
}
