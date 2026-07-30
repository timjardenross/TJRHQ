import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import type { ArchiveStatus, RetentionPolicy } from '@/lib/types';

// USS-TJR-MSN-0206D: manual retention override. The policy engine
// (src/lib/retentionPolicy.ts) never assigns 'Archived' — this is the only
// path that sets it, or corrects a mis-classified document. No deletion
// capability here or anywhere else in this phase (mission requirement: no
// automatic deletion) — archiving only ever changes these two fields.
const RETENTION_POLICIES: RetentionPolicy[] = ['Permanent', 'Long-Term', 'Temporary', 'Expiring', 'Archived'];
const ARCHIVE_STATUSES: ArchiveStatus[] = ['active', 'archived'];

export async function PATCH(
  request: NextRequest,
  { params }: { params: { id: string } },
) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const id = decodeURIComponent(params.id ?? '').trim();
  if (!id) {
    return NextResponse.json({ error: 'Document ID required' }, { status: 400 });
  }

  let body: Record<string, unknown> = {};
  try { body = await request.json(); } catch {
    return NextResponse.json({ error: 'Request body required' }, { status: 400 });
  }

  const update: Record<string, unknown> = {};

  if ('retention_policy' in body) {
    if (!RETENTION_POLICIES.includes(body.retention_policy as RetentionPolicy)) {
      return NextResponse.json(
        { error: 'Invalid retention_policy', valid_values: RETENTION_POLICIES },
        { status: 400 },
      );
    }
    update.retention_policy = body.retention_policy;
  }

  if ('archive_status' in body) {
    if (!ARCHIVE_STATUSES.includes(body.archive_status as ArchiveStatus)) {
      return NextResponse.json(
        { error: 'Invalid archive_status', valid_values: ARCHIVE_STATUSES },
        { status: 400 },
      );
    }
    update.archive_status = body.archive_status;
  }

  if ('expiry_date' in body) {
    update.expiry_date = body.expiry_date === null ? null : String(body.expiry_date);
  }
  if ('review_due_date' in body) {
    update.review_due_date = String(body.review_due_date);
  }

  if (Object.keys(update).length === 0) {
    return NextResponse.json(
      { error: 'At least one of retention_policy, archive_status, expiry_date, review_due_date is required' },
      { status: 400 },
    );
  }

  try {
    const supabase = await createSupabaseServerClient();

    const { data, error } = await supabase
      .from('knowledge_documents')
      .update(update)
      .eq('id', id)
      .select('id, title, retention_policy, expiry_date, archive_status, review_due_date')
      .maybeSingle();
    if (error) throw error;
    if (!data) {
      return NextResponse.json({ error: 'Document not found', id }, { status: 404 });
    }

    return NextResponse.json({ document: data });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Failed to update retention', detail }, { status: 500 });
  }
}
