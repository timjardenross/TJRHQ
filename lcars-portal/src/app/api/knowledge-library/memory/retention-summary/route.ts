import { NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';
import type { RetentionSummary } from '@/lib/types';

// USS-TJR-MSN-0206D/J-2: reporting surface for Command Memory — counts by
// retention_policy, archive_status, and category (MSN-0206J-2), plus how
// many approved documents are past their review_due_date. Purely
// informational: nothing here deletes or auto-archives anything.
//
// MSN-0333: an aggregate report over knowledge_documents is still
// "general access" (not a deliberate single-document lookup) — excludes
// sensitive/restricted from the counts, same rule as the list/search
// routes, for consistency rather than treating aggregation as a loophole.
export async function GET() {
  try {
    const supabase = await createSupabaseServerClient();

    const { data: rows, error } = await supabase
      .from('knowledge_documents')
      .select('retention_policy, archive_status, review_due_date, category, metadata')
      .or("metadata->>sensitivity.is.null,metadata->>sensitivity.not.in.(sensitive,restricted)");
    if (error) throw error;

    const nowIso = new Date().toISOString();
    const summary: RetentionSummary = { by_policy: {}, by_archive_status: {}, overdue_for_review: 0, by_category: {} };

    for (const row of rows ?? []) {
      const policyKey = row.retention_policy ?? 'Unclassified';
      summary.by_policy[policyKey] = (summary.by_policy[policyKey] ?? 0) + 1;
      summary.by_archive_status[row.archive_status] = (summary.by_archive_status[row.archive_status] ?? 0) + 1;
      const categoryKey = row.category ?? 'Unclassified';
      summary.by_category[categoryKey] = (summary.by_category[categoryKey] ?? 0) + 1;
      if (row.review_due_date && row.review_due_date < nowIso) summary.overdue_for_review += 1;
    }

    return NextResponse.json(summary);
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Failed to load retention summary', detail }, { status: 500 });
  }
}
