// Mission 6B (§6 Conversational Continuity) — thin read/write wrapper
// around number_one_context (migration 0219). Single-row, short-lived
// pointer to the last canonical object Number One's dispatcher surfaced or
// acted on, so "I'm stuck" / "still can't start" / "not now" / "where was
// I?" / "done" can resolve "this"/"it" across turns without the client
// replaying full chat history.
//
// Deliberately NOT a chat-turn log (that's conversation_turns, migration
// 0208, XO/Telegram-specific) — just one row, upserted in place.

export type NumberOneObjectType = 'personal_task' | 'captured_item';

export interface NumberOneContext {
  object_type: NumberOneObjectType;
  object_id: string;
  object_title: string | null;
  last_intent: string;
  updated_at: string;
}

// Short-lived by design (brief §6's own language) — a context older than
// this is treated as expired on read, not deleted, so the write path stays
// a single upsert with no cleanup job.
const CONTEXT_TTL_MINUTES = 120;

/** Returns the last canonical object Number One referenced, or null if
 * there isn't one or it's aged out. Never throws — a read failure here
 * must not break intent dispatch; the caller falls back to asking the
 * Captain which task they mean (brief §16). */
export async function getNumberOneContext(sb: any): Promise<NumberOneContext | null> {
  try {
    const { data, error } = await sb
      .from('number_one_context')
      .select('object_type,object_id,object_title,last_intent,updated_at')
      .eq('id', 'default')
      .maybeSingle();
    if (error || !data) return null;
    const ageMinutes = (Date.now() - new Date(data.updated_at).getTime()) / 60_000;
    if (ageMinutes > CONTEXT_TTL_MINUTES) return null;
    return data as NumberOneContext;
  } catch {
    return null;
  }
}

export async function setNumberOneContext(
  sb: any,
  ctx: { object_type: NumberOneObjectType; object_id: string; object_title: string | null; last_intent: string },
): Promise<void> {
  try {
    await sb.from('number_one_context').upsert({
      id: 'default',
      object_type: ctx.object_type,
      object_id: ctx.object_id,
      object_title: ctx.object_title,
      last_intent: ctx.last_intent,
      updated_at: new Date().toISOString(),
    });
  } catch {
    // Best-effort — losing continuity is a degraded experience, not a
    // failure the Captain's message should surface as an error.
  }
}
