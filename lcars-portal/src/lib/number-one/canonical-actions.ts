// Mission 6B (§4 Number One's Final Role) — server-side ports of the
// canonical mutations Number One's dispatcher needs to call directly
// (capture, defer, complete). These mirror lib/capture.ts and
// lib/personalTasks.ts EXACTLY (same tables, same columns, same payload
// shapes) — the only difference is a server Supabase client (this runs in
// a Next.js API route, which has no browser client available) instead of
// the browser client those two files use. No new schema, no second write
// path — Number One orchestrates the same canonical capabilities the
// Capture Workbench and Ready Room already use (brief §4: "Number One
// orchestrates, not reimplements").

export interface CanonicalActionResult {
  ok: boolean;
  id?: string;
  title?: string;
  error?: string;
}

/** Mirrors lib/capture.ts's captureItem() for the 'note' type — Number One
 * only ever files a plain note via "remember this"; anything requiring
 * mission/decision review-gating stays the Capture Workbench's job. */
export async function captureNote(sb: any, text: string): Promise<CanonicalActionResult> {
  const body = text.trim();
  if (!body) return { ok: false, error: 'Nothing to capture.' };

  const now = new Date();
  const id = crypto.randomUUID();
  const firstLine = body.split('\n')[0].trim();
  const title = (firstLine.length > 90 ? `${firstLine.slice(0, 87)}…` : firstLine).slice(0, 200) || 'Untitled capture';

  const payload = {
    captured_by: 'captain-tjr',
    captured_at: now.toISOString(),
    source_type: 'channel_message',
    source_channel_id: 'portal-floating-capture',
    source_message_id: id,
    source_message_ts: String(now.getTime()),
    item_type: 'text_note',
    title,
    raw_text: body.slice(0, 10240),
    classification: 'reference',
    importance: 'low',
    processing_status: 'pending',
    review_status: 'unreviewed',
    requires_review: false,
    ai_enrichment_status: 'not_enriched',
  };

  try {
    const { data, error } = await sb.from('captured_items').insert(payload).select('id').maybeSingle();
    if (error) return { ok: false, error: error.message };
    return { ok: true, id: data?.id, title };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Capture failed.' };
  }
}

/** Mirrors lib/personalTasks.ts's deferNotToday() — canonical non-lossy
 * defer (spec §8.3/§19 "not now"): sets snoozed_until, never deletes or
 * abandons the task. */
export async function deferTask(sb: any, id: string): Promise<CanonicalActionResult> {
  const end = new Date();
  end.setHours(23, 59, 59, 999);
  try {
    const { error } = await sb
      .from('personal_tasks')
      .update({ snoozed_until: end.toISOString(), updated_at: new Date().toISOString() })
      .eq('id', id);
    if (error) return { ok: false, error: error.message };
    return { ok: true, id };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Defer failed.' };
  }
}

/** Mirrors lib/personalTasks.ts's updateTaskState('completed') — canonical
 * completion of the underlying object (spec §19: "complete the canonical
 * underlying object" — never a Number One-local "done" marker). */
export async function completeTask(sb: any, id: string): Promise<CanonicalActionResult> {
  try {
    const { error } = await sb
      .from('personal_tasks')
      .update({ work_state: 'completed', completed_at: new Date().toISOString(), updated_at: new Date().toISOString() })
      .eq('id', id);
    if (error) return { ok: false, error: error.message };
    return { ok: true, id };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Complete failed.' };
  }
}

/** Same shape lib/personalTasks.ts's fetchTasks()+pickUpItems() computes
 * client-side — server-side port for "where was I?" (interruption
 * recovery). paused work with a restart_cue, not snoozed. */
export async function fetchPickUpCandidate(sb: any): Promise<{ id: string; title: string; restart_cue: string | null } | null> {
  try {
    const { data, error } = await sb
      .from('personal_tasks')
      .select('id,title,restart_cue,snoozed_until,updated_at')
      .eq('work_state', 'paused')
      .not('restart_cue', 'is', null)
      .order('updated_at', { ascending: false })
      .limit(5);
    if (error || !data) return null;
    const now = Date.now();
    const candidate = (data as any[]).find(
      (t) => !t.snoozed_until || new Date(t.snoozed_until).getTime() <= now,
    );
    return candidate ? { id: candidate.id, title: candidate.title, restart_cue: candidate.restart_cue } : null;
  } catch {
    return null;
  }
}

/** Fetches a single task by id — used to resolve context pointers before
 * acting on them (defer/complete), so a stale/expired context row never
 * silently mutates the wrong record. */
export async function getTaskById(sb: any, id: string): Promise<{ id: string; title: string; work_state: string } | null> {
  try {
    const { data, error } = await sb.from('personal_tasks').select('id,title,work_state').eq('id', id).maybeSingle();
    if (error || !data) return null;
    return data;
  } catch {
    return null;
  }
}

/** Mission 6B §8.8 — Captain preference gate. Reads capacity_preferences
 * the same way api/ready-room/support-effectiveness/route.ts already does
 * (never a second preference store) and returns true when the given
 * item_code has been explicitly marked 'do_not_suggest' in that domain.
 * Number One must call this before including ANY intervention/support
 * suggestion in a reply — a suggestion the Captain has excluded must never
 * resurface through a different surface (spec §8.8). */
export async function isDoNotSuggest(sb: any, domain: string, itemCode: string): Promise<boolean> {
  try {
    const { data } = await sb
      .from('capacity_preferences')
      .select('preference_state')
      .eq('domain', domain)
      .eq('item_code', itemCode)
      .maybeSingle();
    return data?.preference_state === 'do_not_suggest';
  } catch {
    // Fail safe toward NOT suggesting is wrong here (spec has no
    // "assume excluded" default) — fail open to "not excluded" so a
    // transient read error never silently blocks useful support; the
    // exclusion is only ever set by explicit Captain action, so an
    // occasional missed check on error is a smaller harm than a support
    // surface that mysteriously stops offering help.
    return false;
  }
}
