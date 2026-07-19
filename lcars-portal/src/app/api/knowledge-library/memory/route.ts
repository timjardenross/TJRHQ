import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';

// USS-TJR-MSN-0206D/J-2: browse/report on Command Memory (knowledge_documents)
// by retention lifecycle and category. Read-only — the write path into
// this table stays MSN-0205D's decide route; manual retention overrides go
// through PATCH /api/knowledge-library/memory/[id].
//
// MSN-0333: this is a general LIST view, not a deliberate single-document
// lookup -- excludes sensitive/restricted by default even for a fully
// cleared identity (RLS alone can't express "general vs specific access",
// only "who is asking"; the two are separate axes). Applied as a query-
// level filter (GENERAL_ACCESS_OR below), not a client-side post-filter,
// so `total`/pagination stay accurate -- verified the null-handling
// directly against real data first (metadata->>sensitivity IS NULL must
// stay visible; a naive `not.in` filter alone silently drops nulls too,
// per the same mistake caught and fixed in tools/notion/sync_knowledge_assets.py).
const LIST_COLUMNS = [
  'id', 'title', 'document_type', 'category', 'tags', 'retention_policy', 'expiry_date',
  'archive_status', 'review_due_date', 'created_at', 'updated_at',
].join(',');

const GENERAL_ACCESS_OR = "metadata->>sensitivity.is.null,metadata->>sensitivity.not.in.(sensitive,restricted)";

const DEFAULT_LIMIT = 50;
const MAX_LIMIT = 200;

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const retentionPolicy = searchParams.get('retention_policy')?.trim();
  const archiveStatus = searchParams.get('archive_status')?.trim();
  const category = searchParams.get('category')?.trim();
  const search = searchParams.get('search')?.trim();
  const overdue = searchParams.get('overdue') === 'true';
  const limit = Math.min(MAX_LIMIT, Math.max(1, Number(searchParams.get('limit')) || DEFAULT_LIMIT));
  const offset = Math.max(0, Number(searchParams.get('offset')) || 0);

  try {
    const supabase = await createSupabaseServerClient();
    let query = supabase
      .from('knowledge_documents')
      .select(LIST_COLUMNS, { count: 'exact' })
      .or(GENERAL_ACCESS_OR)
      .order('review_due_date', { ascending: true, nullsFirst: false })
      .range(offset, offset + limit - 1);

    if (retentionPolicy) query = query.eq('retention_policy', retentionPolicy);
    if (archiveStatus) query = query.eq('archive_status', archiveStatus);
    if (category) query = query.eq('category', category);
    if (search) query = query.ilike('title', `%${search.replace(/[%_,]/g, (c) => `\\${c}`)}%`);
    if (overdue) query = query.lt('review_due_date', new Date().toISOString());

    const { data, error, count } = await query;
    if (error) throw error;

    return NextResponse.json({ documents: data ?? [], total: count ?? 0, limit, offset });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Failed to load memory documents', detail }, { status: 500 });
  }
}
