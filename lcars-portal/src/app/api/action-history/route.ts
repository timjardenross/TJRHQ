import { NextRequest, NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import { supabaseAdmin } from '@/lib/ai-actions';
import { stableStringify } from '@/lib/actionHistoryServer';

// A retried call whose action+outcome+details are byte-identical to the
// most recent event for the same actor within this window is treated as
// the same idempotent attempt and collapsed onto the existing row instead
// of inserted again — so an idempotent mutation retried by a flaky network
// or a double-tap doesn't spam duplicate success events. A genuinely new
// attempt (different details — e.g. a fresh record_id from a non-idempotent
// create, or a different outcome) always gets its own row.
const DEDUPE_WINDOW_MS = 60_000;

/** Append-only server history for consequential user actions. */
export async function POST(req: NextRequest) {
  if (!(await requireSession())) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  const body = await req.json().catch(() => ({}));
  if (typeof body.action !== 'string' || typeof body.outcome !== 'string') return NextResponse.json({ error: 'action and outcome are required' }, { status: 400 });
  const details = body.details ?? {};
  const admin = supabaseAdmin();

  const since = new Date(Date.now() - DEDUPE_WINDOW_MS).toISOString();
  const { data: recent } = await admin
    .from('audit_events')
    .select('id,created_at,outcome,details')
    .eq('category', 'user_action')
    .eq('actor', 'captain')
    .eq('action', body.action)
    .gte('created_at', since)
    .order('created_at', { ascending: false })
    .limit(1);
  const last = recent?.[0];
  if (last && last.outcome === body.outcome && stableStringify(last.details ?? {}) === stableStringify(details)) {
    return NextResponse.json({ event: { id: last.id, created_at: last.created_at }, deduped: true });
  }

  const { data, error } = await admin.from('audit_events').insert({
    category: 'user_action', actor: 'captain', action: body.action, outcome: body.outcome,
    details, mission_id: body.mission_id ?? null,
  }).select('id,created_at').single();
  if (error) return NextResponse.json({ error: 'history_write_failed' }, { status: 500 });
  return NextResponse.json({ event: data });
}
