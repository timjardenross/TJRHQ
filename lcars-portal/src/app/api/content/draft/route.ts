// MSN-0202: Content draft request endpoint.
// POST /api/content/draft — creates a comms_content row from an intelligence signal.

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { requireSession } from '@/lib/supabase-server';

function serviceClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
  );
}

export async function POST(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = serviceClient();

    const body = await req.json();
    const { event_id, title, pillar_key, suggested_angle, source_name, canonical_url, notes: rawNotes } = body;

    if (!title) {
      return NextResponse.json({ error: 'title is required' }, { status: 400 });
    }

    const truncatedTitle = String(title).slice(0, 200);
    const notes = rawNotes ?? [
      suggested_angle ? `Signal: ${suggested_angle}` : null,
      source_name ? `Source: ${source_name}` : null,
      canonical_url ? `URL: ${canonical_url}` : null,
    ]
      .filter(Boolean)
      .join('. ');

    const { data, error } = await sb
      .from('comms_content')
      .insert({
        title: truncatedTitle,
        pillar: pillar_key ?? null,
        source_kind: event_id ? 'intelligence_signal' : 'capture',
        source_ref: event_id ?? null,
        signal_source_id: event_id ?? null,
        status: 'opportunity',
        classification: 'publishable',
        notes: notes || null,
      })
      .select('id')
      .single();

    if (error) throw error;

    return NextResponse.json({ success: true, content_id: data.id });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Internal error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
