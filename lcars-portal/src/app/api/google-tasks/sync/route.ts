// Two-way sync: personal_tasks <-> Google Tasks. Design doc: this session's
// conversation, 2026-09-05 — "Design first" ask, "Casual" answer on default
// follow_through_mode for Google-Tasks-originated rows.
//
// Callable two ways: a logged-in Captain session (manual trigger), or the
// VM's Python scheduler carrying X-Bot-Secret (periodic trigger) — same
// server-to-server pattern XO's Telegram bot already uses against this
// portal (middleware.ts's bot-secret bypass). Checked explicitly here too
// (not just relying on middleware) since a bot-secret caller has no
// session for requireSession() to find.
//
// Push (local -> Google): rows never linked (google_task_id IS NULL, not
// completed/abandoned) get created in Google Tasks; rows already linked
// whose updated_at is newer than google_synced_at get patched. Pull
// (Google -> local): Google tasks with no matching google_task_id become
// new personal_tasks rows (follow_through_mode='gentle' — a casually
// phone-added task shouldn't immediately get persistent-nagged); already-
// linked tasks whose Google `updated` is newer than our google_synced_at
// sync their completion status back. Conflict rule: last-write-wins by
// timestamp, no merge — the simplest thing that won't corrupt data for a
// single-user app.

import { NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import { createSupabaseServiceRoleClient } from '@/lib/supabase-service-role';
import { listGoogleTasks, createGoogleTask, updateGoogleTask, type GoogleTask } from '@/lib/google-tasks';
import { GoogleCalendarDisconnectedError } from '@/lib/google-calendar';

const DEFAULT_TASK_LIST = '@default';

interface PersonalTaskRow {
  id: string;
  title: string;
  context: string | null;
  due_date: string | null;
  work_state: string;
  updated_at: string;
  google_task_id: string | null;
  google_task_list_id: string | null;
  google_synced_at: string | null;
}

function isAuthorized(request: Request): boolean {
  const botSecret = request.headers.get('x-bot-secret');
  return !!botSecret && !!process.env.BOT_API_SECRET && botSecret === process.env.BOT_API_SECRET;
}

export async function POST(request: Request) {
  const session = await requireSession();
  if (!session && !isAuthorized(request)) {
    return NextResponse.json({ error: 'Not authenticated.' }, { status: 401 });
  }

  const supabase = createSupabaseServiceRoleClient();
  const now = new Date().toISOString();
  let pushed = 0;
  let pulled = 0;
  let completionsSynced = 0;
  const errors: string[] = [];

  try {
    // ── Push: local -> Google ──────────────────────────────────────────
    const { data: toPush, error: pushSelectError } = await supabase
      .from('personal_tasks')
      .select('id, title, context, due_date, work_state, updated_at, google_task_id, google_task_list_id, google_synced_at')
      .not('work_state', 'in', '(completed,abandoned)')
      .or('google_task_id.is.null,google_synced_at.is.null');

    if (pushSelectError) throw new Error(`Push select failed: ${pushSelectError.message}`);

    for (const row of (toPush ?? []) as PersonalTaskRow[]) {
      // Re-check locally: only push if genuinely unlinked, or linked but
      // edited since last sync (avoids re-pushing a row whose
      // google_synced_at is null only because it was just pulled in this
      // same run — see pull loop below, which sets synced_at on insert).
      if (row.google_task_id && row.google_synced_at && new Date(row.updated_at) <= new Date(row.google_synced_at)) {
        continue;
      }
      try {
        const listId = row.google_task_list_id ?? DEFAULT_TASK_LIST;
        if (!row.google_task_id) {
          const created = await createGoogleTask(
            { title: row.title, notes: row.context ?? undefined, due: row.due_date ?? undefined },
            listId
          );
          await supabase
            .from('personal_tasks')
            .update({ google_task_id: created.id, google_task_list_id: listId, google_synced_at: now })
            .eq('id', row.id);
        } else {
          await updateGoogleTask(
            row.google_task_id,
            { title: row.title, notes: row.context ?? undefined, due: row.due_date ?? undefined },
            listId
          );
          await supabase.from('personal_tasks').update({ google_synced_at: now }).eq('id', row.id);
        }
        pushed++;
      } catch (err) {
        errors.push(`push ${row.id}: ${err instanceof Error ? err.message : String(err)}`);
      }
    }

    // ── Pull: Google -> local ───────────────────────────────────────────
    const googleTasks = await listGoogleTasks(DEFAULT_TASK_LIST);
    const googleIds = googleTasks.map((t) => t.id);

    const { data: linkedRows, error: linkedError } = googleIds.length
      ? await supabase
          .from('personal_tasks')
          .select('id, work_state, google_task_id, google_synced_at')
          .in('google_task_id', googleIds)
      : { data: [], error: null };
    if (linkedError) throw new Error(`Linked select failed: ${linkedError.message}`);

    // Deletion: a task removed in the Google Tasks app (not completed —
    // completion is handled separately below, this is "swiped away as not
    // relevant") stops appearing in listGoogleTasks entirely, there's no
    // tombstone to detect. So instead of diffing against what Google
    // returned, check every still-open row this app has ever linked — any
    // whose google_task_id is no longer in the current list was deleted on
    // Google's side. Marked 'abandoned', not 'completed' (that would
    // misrepresent it as done) — this also stops the follow-through engine
    // nudging about it, since task_nudge_scheduler/follow_through_engine
    // both exclude completed/abandoned work_state.
    let deleted = 0;
    const { data: allLinkedOpen, error: allLinkedError } = await supabase
      .from('personal_tasks')
      .select('id, google_task_id')
      .not('google_task_id', 'is', null)
      .not('work_state', 'in', '(completed,abandoned)');
    if (allLinkedError) throw new Error(`All-linked select failed: ${allLinkedError.message}`);

    const googleIdSet = new Set(googleIds);
    for (const row of (allLinkedOpen ?? []) as { id: string; google_task_id: string }[]) {
      if (!googleIdSet.has(row.google_task_id)) {
        try {
          await supabase
            .from('personal_tasks')
            .update({ work_state: 'abandoned', google_synced_at: now })
            .eq('id', row.id);
          deleted++;
        } catch (err) {
          errors.push(`deleted-detect ${row.id}: ${err instanceof Error ? err.message : String(err)}`);
        }
      }
    }

    const linkedByGoogleId = new Map((linkedRows ?? []).map((r: { google_task_id: string | null }) => [r.google_task_id, r]));

    for (const gtask of googleTasks) {
      const linked = linkedByGoogleId.get(gtask.id) as
        | { id: string; work_state: string; google_task_id: string | null; google_synced_at: string | null }
        | undefined;

      if (!linked) {
        // New task added directly in the Google Tasks app — bring it in.
        try {
          const isDone = gtask.status === 'completed';
          await supabase.from('personal_tasks').insert({
            title: gtask.title || '(untitled)',
            context: gtask.notes ?? null,
            due_date: gtask.due ? gtask.due.slice(0, 10) : null,
            category: 'task',
            urgency: 3,
            importance: 3,
            follow_through_mode: 'gentle',
            work_state: isDone ? 'completed' : 'captured',
            completed_at: isDone ? now : null,
            google_task_id: gtask.id,
            google_task_list_id: DEFAULT_TASK_LIST,
            google_synced_at: now,
          });
          pulled++;
        } catch (err) {
          errors.push(`pull ${gtask.id}: ${err instanceof Error ? err.message : String(err)}`);
        }
        continue;
      }

      // Already linked — sync completion status if Google's side changed
      // since our last sync (last-write-wins by Google's own `updated`).
      const googleIsDone = gtask.status === 'completed';
      const localIsDone = linked.work_state === 'completed' || linked.work_state === 'abandoned';
      const googleChangedSinceSync =
        !linked.google_synced_at || new Date(gtask.updated) > new Date(linked.google_synced_at);

      if (googleIsDone !== localIsDone && googleChangedSinceSync) {
        try {
          await supabase
            .from('personal_tasks')
            .update({
              work_state: googleIsDone ? 'completed' : 'captured',
              completed_at: googleIsDone ? now : null,
              google_synced_at: now,
            })
            .eq('id', linked.id);
          completionsSynced++;
        } catch (err) {
          errors.push(`sync-completion ${linked.id}: ${err instanceof Error ? err.message : String(err)}`);
        }
      }
    }

    return NextResponse.json({ status: 'ok', pushed, pulled, completionsSynced, deleted, errors });
  } catch (err) {
    if (err instanceof GoogleCalendarDisconnectedError) {
      return NextResponse.json({ status: 'disconnected', message: err.message }, { status: 409 });
    }
    console.error('[google-tasks/sync] failed:', err);
    return NextResponse.json(
      { status: 'error', message: err instanceof Error ? err.message : 'Sync failed.' },
      { status: 502 }
    );
  }
}
