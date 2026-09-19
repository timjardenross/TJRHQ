/**
 * Ready Room support-event writer — POST /api/ready-room/support-events
 *
 * Mission 5 (Evidence & Adaptive Support). Writes a
 * capacity_intervention_events row with domain='ready_room' (migration
 * 0218), participating in the exact same evidence model capacitybot's
 * capacity domain already uses (provenance-separated evidence,
 * causality-guarded confidence, sample-floor-gated ranking) — see
 * ../../human-systems/intervention-effectiveness.ts for the read side.
 *
 * This is the ONLY place that translates a Captain-facing HELPFUL /
 * NOT HELPFUL / NOT NOW tap into outcome/would_use_again (spec §12). NOT
 * NOW must never produce a negative-effectiveness signal — see
 * mapFeedback() below — and the whole endpoint must be safe against a
 * client-side double-click or fetch retry (spec §31): the client sends one
 * idempotency_key per feedback opportunity (generated once, reused across
 * retries — see SupportFeedback.tsx), stored in context_snapshot and
 * enforced by a partial unique index (0218's
 * capacity_intervention_events_idempotency_idx). A retried insert hits
 * that constraint (Postgres 23505) instead of writing a second row; this
 * route resolves the conflict by returning the row that already exists
 * rather than erroring the retry.
 */

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

const READY_ROOM_FEEDBACK = ['helpful', 'not_helpful', 'not_now'] as const;
type ReadyRoomFeedback = (typeof READY_ROOM_FEEDBACK)[number];

function isReadyRoomFeedback(value: unknown): value is ReadyRoomFeedback {
  return typeof value === 'string' && (READY_ROOM_FEEDBACK as readonly string[]).includes(value);
}

/** HELPFUL/NOT HELPFUL/NOT NOW → outcome/would_use_again, spec §12's exact
 *  mapping onto the existing better/same/worse/not_completed/unknown and
 *  yes/maybe/no vocab (0218's header comment) — 'not_now' resolves to
 *  'not_completed'/null, never 'worse'/'no'. A dismissed prompt (no tap at
 *  all) never reaches this function — the client simply writes nothing. */
function mapFeedback(feedback: ReadyRoomFeedback): { outcome: 'better' | 'worse' | 'not_completed'; would_use_again: 'yes' | 'no' | null } {
  switch (feedback) {
    case 'helpful':
      return { outcome: 'better', would_use_again: 'yes' };
    case 'not_helpful':
      return { outcome: 'worse', would_use_again: 'no' };
    case 'not_now':
      return { outcome: 'not_completed', would_use_again: null };
  }
}

interface SupportEventBody {
  intervention_id: string;
  feedback: ReadyRoomFeedback;
  task_ref: string | null;
  posture: string | null;
  capacity_state: string | null;
  idempotency_key: string;
}

function parseBody(raw: unknown): { body: SupportEventBody | null; error: string | null } {
  const b = raw as Record<string, unknown> | null;
  if (!b || typeof b !== 'object') return { body: null, error: 'Invalid JSON body' };
  const intervention_id = typeof b.intervention_id === 'string' ? b.intervention_id.trim() : '';
  if (!intervention_id) return { body: null, error: 'intervention_id is required' };
  if (!isReadyRoomFeedback(b.feedback)) return { body: null, error: "feedback must be one of 'helpful' | 'not_helpful' | 'not_now'" };
  const idempotency_key = typeof b.idempotency_key === 'string' ? b.idempotency_key.trim() : '';
  if (!idempotency_key) return { body: null, error: 'idempotency_key is required' };
  return {
    body: {
      intervention_id,
      feedback: b.feedback,
      task_ref: typeof b.task_ref === 'string' && b.task_ref.trim() ? b.task_ref.trim() : null,
      posture: typeof b.posture === 'string' ? b.posture : null,
      capacity_state: typeof b.capacity_state === 'string' ? b.capacity_state : null,
      idempotency_key,
    },
    error: null,
  };
}

export async function POST(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  let json: unknown;
  try {
    json = await req.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }
  const { body, error } = parseBody(json);
  if (!body) {
    return NextResponse.json({ error }, { status: 400 });
  }

  const sb = await createSupabaseServerClient();

  // Fast idempotency path: an earlier successful call with this exact key
  // already exists — return it rather than writing (or attempting to
  // write) a second row. Covers a retry that arrives after the first
  // insert has already committed and been read back once.
  const { data: existing } = await sb
    .from('capacity_intervention_events')
    .select('id')
    .eq('domain', 'ready_room')
    .contains('context_snapshot', { idempotency_key: body.idempotency_key })
    .maybeSingle();
  if (existing) {
    return NextResponse.json({ ok: true, id: existing.id, deduped: true }, { status: 200 });
  }

  const { outcome, would_use_again } = mapFeedback(body.feedback);

  const { data: inserted, error: insertError } = await sb
    .from('capacity_intervention_events')
    .insert({
      domain: 'ready_room',
      source: 'ready_room',
      intervention_id: body.intervention_id,
      task_ref: body.task_ref,
      outcome,
      would_use_again,
      context_snapshot: {
        posture: body.posture ?? 'UNKNOWN',
        capacity: body.capacity_state ?? null,
        idempotency_key: body.idempotency_key,
      },
    })
    .select('id')
    .single();

  if (insertError) {
    // 23505 = unique_violation — a concurrent duplicate (true double-click
    // race, both requests landing before either committed) hit the
    // idempotency index. Resolve it the same way as the fast path above:
    // fetch and return the row the other request just wrote, instead of
    // surfacing an error for what the Captain experiences as one action.
    if (insertError.code === '23505') {
      const { data: winner } = await sb
        .from('capacity_intervention_events')
        .select('id')
        .eq('domain', 'ready_room')
        .contains('context_snapshot', { idempotency_key: body.idempotency_key })
        .maybeSingle();
      if (winner) {
        return NextResponse.json({ ok: true, id: winner.id, deduped: true }, { status: 200 });
      }
    }
    // A bad intervention_id (no matching catalogue row) fails the events
    // table's FK constraint (23503) — surface that as a 400, not a 500,
    // it's a client input error, not a server fault.
    if (insertError.code === '23503') {
      return NextResponse.json({ error: `Unknown intervention_id: ${body.intervention_id}` }, { status: 400 });
    }
    console.error('[ready-room/support-events] insert failed:', insertError);
    return NextResponse.json({ error: 'support_event_write_failed' }, { status: 500 });
  }

  return NextResponse.json({ ok: true, id: inserted?.id, deduped: false }, { status: 200 });
}
