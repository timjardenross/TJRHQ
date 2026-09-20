import { NextRequest, NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import { supabaseAdmin } from '@/lib/ai-actions';

/** Append-only server history for consequential user actions. */
export async function POST(req: NextRequest) {
  if (!(await requireSession())) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  const body = await req.json().catch(() => ({}));
  if (typeof body.action !== 'string' || typeof body.outcome !== 'string') return NextResponse.json({ error: 'action and outcome are required' }, { status: 400 });
  const { data, error } = await supabaseAdmin().from('audit_events').insert({
    category: 'user_action', actor: 'captain', action: body.action, outcome: body.outcome,
    details: body.details ?? {}, mission_id: body.mission_id ?? null,
  }).select('id,created_at').single();
  if (error) return NextResponse.json({ error: 'history_write_failed' }, { status: 500 });
  return NextResponse.json({ event: data });
}
