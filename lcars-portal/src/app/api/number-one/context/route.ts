import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { setNumberOneContext, type NumberOneObjectType } from '@/lib/number-one/context-store';

/**
 * POST /api/number-one/context — Mission 7 §18/§29 continuity fix.
 *
 * `lib/number-one/context-store.ts`'s `setNumberOneContext` (Mission 6B) was
 * previously only ever called from inside `dispatchIntent` — i.e. Number
 * One only knew "which task" after the Captain had already told it once
 * that session (asked "what matters?", said "remember …", etc). A Captain
 * who instead arrived at a task the ordinary way — Hub's "Do this" link,
 * Ready Room's own task list, Unstick Me's "Start here" — was looking
 * straight at a specific task with nothing recorded anywhere that Number
 * One's ambient widget could resolve "it"/"this" against. Asking "I'm
 * stuck" on exactly that screen got "Which task? I don't have one in view
 * right now." — technically true, and exactly the kind of machinery the
 * Captain shouldn't have to narrate around.
 *
 * This route lets the client (see ActiveTaskView.tsx) record "the Captain
 * is now looking at this task" the same way the dispatcher itself already
 * does — same table, same TTL, same best-effort semantics (never blocks or
 * errors the Captain-facing action it's attached to). No new state model:
 * this is the existing number_one_context row, written from one more
 * legitimate place.
 */

const VALID_OBJECT_TYPES: readonly NumberOneObjectType[] = ['personal_task', 'captured_item'];

interface ContextBody {
  object_type: NumberOneObjectType;
  object_id: string;
  object_title: string | null;
  last_intent?: string;
}

function parseBody(raw: unknown): ContextBody | null {
  const b = raw as Record<string, unknown> | null;
  if (!b || typeof b !== 'object') return null;
  const object_type = b.object_type;
  if (typeof object_type !== 'string' || !VALID_OBJECT_TYPES.includes(object_type as NumberOneObjectType)) return null;
  const object_id = typeof b.object_id === 'string' ? b.object_id.trim() : '';
  if (!object_id) return null;
  return {
    object_type: object_type as NumberOneObjectType,
    object_id,
    object_title: typeof b.object_title === 'string' ? b.object_title : null,
    last_intent: typeof b.last_intent === 'string' && b.last_intent.trim() ? b.last_intent.trim() : 'viewing',
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
  const body = parseBody(json);
  if (!body) {
    return NextResponse.json({ error: 'object_type and object_id are required' }, { status: 400 });
  }

  const sb = await createSupabaseServerClient();
  // setNumberOneContext() never throws (see its own header comment) — a
  // failed write here degrades to Number One asking "which task?" next
  // time, never an error the Captain-facing caller has to handle.
  await setNumberOneContext(sb, {
    object_type: body.object_type,
    object_id: body.object_id,
    object_title: body.object_title,
    last_intent: body.last_intent ?? 'viewing',
  });

  return NextResponse.json({ ok: true });
}
