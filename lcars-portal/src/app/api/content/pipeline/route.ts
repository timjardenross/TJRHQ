// Content pipeline API — fetch and update comms_content items.
// GET  /api/content/pipeline          — list all non-archived items
// PATCH /api/content/pipeline?id=...  — update status, notes, body

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';

const VALID_STATUSES = ['opportunity', 'draft', 'review', 'approved', 'ready_to_publish', 'published', 'archived'] as const;
type ContentStatus = (typeof VALID_STATUSES)[number];

function serviceClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
  );
}

export async function GET() {
  try {
    const sb = serviceClient();
    const { data, error } = await sb
      .from('comms_content')
      .select('id, title, pillar, status, format, source_kind, source_ref, signal_source_id, classification, notes, body, sensitive, created_at, updated_at')
      .neq('status', 'archived')
      .order('created_at', { ascending: false });

    if (error) throw error;
    return NextResponse.json({ items: data ?? [] });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Internal error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function PATCH(req: NextRequest) {
  try {
    const id = req.nextUrl.searchParams.get('id');
    if (!id) return NextResponse.json({ error: 'id is required' }, { status: 400 });

    const body = await req.json();
    const patch: Record<string, unknown> = { updated_at: new Date().toISOString() };

    if (body.status !== undefined) {
      if (!VALID_STATUSES.includes(body.status as ContentStatus)) {
        return NextResponse.json({ error: `Invalid status: ${body.status}` }, { status: 400 });
      }
      patch.status = body.status;
    }
    if (body.notes !== undefined) patch.notes = body.notes;
    if (body.body !== undefined) patch.body = body.body;

    const sb = serviceClient();
    const { error } = await sb.from('comms_content').update(patch).eq('id', id);
    if (error) throw error;

    return NextResponse.json({ success: true });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Internal error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
