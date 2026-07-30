import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

// USS-TJR-MSN-0205D: filtered document list for the Knowledge Library.
// extracted_text is deliberately excluded (large field, not needed for a
// list view) — GET /api/knowledge-library/documents/[id] returns it.
const LIST_COLUMNS = [
  'id', 'source_name', 'source_path', 'filename', 'file_type', 'size_bytes',
  'status', 'ocr_used', 'ocr_engine', 'category', 'tags', 'summary',
  'sensitivity', 'memory_recommendation', 'chunk_count', 'failure_reason',
  'exclusion_reason', 'memory_document_id', 'review_decision', 'review_decided_at',
  'review_decided_by', 'review_reason', 'review_status', 'review_history',
  'created_at', 'updated_at',
].join(',');

const DEFAULT_LIMIT = 50;
const MAX_LIMIT = 200;

function escapeIlike(term: string): string {
  return term.replace(/[%_,]/g, (c) => `\\${c}`);
}

export async function GET(request: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const { searchParams } = new URL(request.url);
  const search = searchParams.get('search')?.trim();
  const category = searchParams.get('category')?.trim();
  const sensitivity = searchParams.get('sensitivity')?.trim();
  const status = searchParams.get('status')?.trim();
  const reviewDecision = searchParams.get('review_decision')?.trim();
  const reviewStatus = searchParams.get('review_status')?.trim();
  const limit = Math.min(MAX_LIMIT, Math.max(1, Number(searchParams.get('limit')) || DEFAULT_LIMIT));
  const offset = Math.max(0, Number(searchParams.get('offset')) || 0);

  try {
    const supabase = await createSupabaseServerClient();
    let query = supabase
      .from('processing_documents')
      .select(LIST_COLUMNS, { count: 'exact' })
      .order('created_at', { ascending: false })
      .range(offset, offset + limit - 1);

    if (category) query = query.eq('category', category);
    if (sensitivity) query = query.eq('sensitivity', sensitivity);
    if (status) query = query.eq('status', status);
    if (reviewDecision === 'none') {
      query = query.is('review_decision', null);
    } else if (reviewDecision) {
      query = query.eq('review_decision', reviewDecision);
    }
    if (reviewStatus) query = query.eq('review_status', reviewStatus);
    if (search) {
      const term = `%${escapeIlike(search)}%`;
      query = query.or(`filename.ilike.${term},summary.ilike.${term},source_name.ilike.${term}`);
    }

    const { data, error, count } = await query;
    if (error) throw error;

    return NextResponse.json({ documents: data ?? [], total: count ?? 0, limit, offset });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Failed to load documents', detail }, { status: 500 });
  }
}
