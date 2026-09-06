'use client';

/**
 * Personal Tasks library — Ready Room workbench data layer.
 *
 * Backs `personal_tasks` (migration 0090, extended by 0163 with life-admin
 * fields). Mirrors lib/capture.ts's shape (types + fetch/create/update
 * functions, no class). Single-user app — no owner/user_id filtering beyond
 * RLS's own authenticated policy.
 */

import { createSupabaseBrowserClient } from './supabase-browser';

// ── Types ─────────────────────────────────────────────────────────────────────

export type TaskCategory =
  | 'task'
  | 'bill'
  | 'appointment'
  | 'renewal'
  | 'subscription'
  | 'form'
  | 'follow_up'
  | 'errand'
  | 'waiting_on';

export type WorkState = 'captured' | 'in_progress' | 'blocked' | 'paused' | 'completed' | 'abandoned';

export interface CategoryMeta {
  key: TaskCategory;
  label: string;
  glyph: string;
}

export const CATEGORIES: CategoryMeta[] = [
  { key: 'task', label: 'Task', glyph: '✦' },
  { key: 'bill', label: 'Bill', glyph: '¤' },
  { key: 'appointment', label: 'Appointment', glyph: '◆' },
  { key: 'renewal', label: 'Renewal', glyph: '↻' },
  { key: 'subscription', label: 'Subscription', glyph: '⇄' },
  { key: 'form', label: 'Form', glyph: '☷' },
  { key: 'follow_up', label: 'Follow-up', glyph: '↪' },
  { key: 'errand', label: 'Errand', glyph: '✇' },
  { key: 'waiting_on', label: 'Waiting on', glyph: '…' },
];

export function categoryMeta(key: TaskCategory | null | undefined): CategoryMeta {
  return CATEGORIES.find((c) => c.key === key) ?? CATEGORIES[0];
}

export type FollowThroughMode = 'gentle' | 'normal' | 'persistent' | 'deadline' | 'waiting';

export interface FollowThroughModeMeta {
  key: FollowThroughMode;
  label: string;
  hint: string;
}

export const FOLLOW_THROUGH_MODES: FollowThroughModeMeta[] = [
  { key: 'gentle', label: 'Gentle', hint: 'one nudge, then quiet' },
  { key: 'normal', label: 'Normal', hint: 'a reminder and one follow-up' },
  { key: 'persistent', label: 'Persistent', hint: 'keeps coming back until resolved' },
  { key: 'deadline', label: 'Deadline', hint: 'gets louder as the date approaches' },
  { key: 'waiting', label: 'Waiting', hint: "checks in, doesn't nag" },
];

export function followThroughModeMeta(key: FollowThroughMode | null | undefined): FollowThroughModeMeta {
  return FOLLOW_THROUGH_MODES.find((m) => m.key === key) ?? FOLLOW_THROUGH_MODES[1];
}

export interface PersonalTask {
  id: string;
  title: string;
  context: string | null;
  category: TaskCategory;
  urgency: number;
  importance: number;
  effort_minutes: number;
  work_state: WorkState;
  due_date: string | null;
  waiting_on: string | null;
  micro_action: string | null;
  mvp_note: string | null;
  stop_point: string | null;
  restart_cue: string | null;
  source_capture_id: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
  follow_through_mode: FollowThroughMode;
  next_review_at: string | null;
  snoozed_until: string | null;
  nudge_count: number;
  deferral_count: number;
  blocker_category: string | null;
  follow_through_paused: boolean;
}

const TASK_SELECT = [
  'id', 'title', 'context', 'category', 'urgency', 'importance', 'effort_minutes',
  'work_state', 'due_date', 'waiting_on', 'micro_action', 'mvp_note', 'stop_point',
  'restart_cue', 'source_capture_id', 'created_at', 'started_at', 'completed_at', 'updated_at',
  'follow_through_mode', 'next_review_at', 'snoozed_until', 'nudge_count', 'deferral_count',
  'blocker_category', 'follow_through_paused',
].join(', ');

// ── Read ──────────────────────────────────────────────────────────────────────

export async function fetchTasks(opts?: { includeCompleted?: boolean; limit?: number }): Promise<PersonalTask[]> {
  try {
    const supabase = createSupabaseBrowserClient();
    let query = supabase
      .from('personal_tasks')
      .select(TASK_SELECT)
      .order('due_date', { ascending: true, nullsFirst: false })
      .order('urgency', { ascending: false })
      .limit(opts?.limit ?? 100);

    if (!opts?.includeCompleted) {
      query = query.not('work_state', 'in', '(completed,abandoned)');
    } else {
      query = query.in('work_state', ['completed', 'abandoned']).order('completed_at', { ascending: false });
    }

    const { data, error } = await query;
    if (error || !data) return [];
    return (data as unknown) as PersonalTask[];
  } catch {
    return [];
  }
}

export async function getTask(id: string): Promise<PersonalTask | null> {
  try {
    const supabase = createSupabaseBrowserClient();
    const { data, error } = await supabase.from('personal_tasks').select(TASK_SELECT).eq('id', id).maybeSingle();
    if (error || !data) return null;
    return (data as unknown) as PersonalTask;
  } catch {
    return null;
  }
}

export interface TaskCounts {
  now: number;
  upcoming: number;
  waiting: number;
}

/** Buckets an open task into the Attend view's three columns. Now = urgent
 * or due within 2 days and not blocked; Waiting = blocked; else Upcoming. */
export function attendBucket(task: PersonalTask): 'now' | 'upcoming' | 'waiting' {
  if (task.work_state === 'blocked') return 'waiting';
  if (task.urgency >= 4) return 'now';
  if (task.due_date) {
    const daysOut = (new Date(task.due_date).getTime() - Date.now()) / 86_400_000;
    if (daysOut <= 2) return 'now';
  }
  return 'upcoming';
}

export function countByBucket(tasks: PersonalTask[]): TaskCounts {
  const counts: TaskCounts = { now: 0, upcoming: 0, waiting: 0 };
  for (const t of tasks) counts[attendBucket(t)]++;
  return counts;
}

/** True if a task is deferred out of Today via "Not today" — reuses
 * snoozed_until (already exists for follow-through snoozing) rather than a
 * new column; a task is only "not snoozed" once the date has passed. */
export function isSnoozedToday(task: PersonalTask): boolean {
  return !!task.snoozed_until && new Date(task.snoozed_until).getTime() > Date.now();
}

/** Deterministic Today ranking (spec §7) — overdue/due-soon, then urgent,
 * then in-progress/restartable, then oldest open, capped at 3 (or a lower
 * capacityLimit). Deliberately simple/inspectable — no opaque AI ranking. */
export function rankToday(tasks: PersonalTask[], opts?: { capacityLimit?: number }): PersonalTask[] {
  const cap = opts?.capacityLimit ?? 3;
  const eligible = tasks.filter((t) => t.work_state !== 'blocked' && !isSnoozedToday(t));

  const score = (t: PersonalTask): number => {
    if (t.due_date) {
      const daysOut = (new Date(t.due_date).getTime() - Date.now()) / 86_400_000;
      if (daysOut <= 0) return 0; // overdue
      if (daysOut <= 2) return 1; // due soon
    }
    if (t.urgency >= 4) return 2; // urgent
    if ((t.work_state === 'paused' || t.work_state === 'in_progress') && t.restart_cue) return 3; // restartable
    return 4; // everything else, oldest first
  };

  return [...eligible]
    .sort((a, b) => {
      const diff = score(a) - score(b);
      if (diff !== 0) return diff;
      return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
    })
    .slice(0, Math.max(0, cap));
}

/** "Pick up where you left off" candidates — paused/blocked-with-restart-cue
 * items, surfaced separately from (and ahead of) the ranked Today list. */
export function pickUpItems(tasks: PersonalTask[]): PersonalTask[] {
  return tasks.filter((t) => t.work_state === 'paused' && t.restart_cue && !isSnoozedToday(t));
}

/** Sets snoozed_until to the end of today (local) — "Not today": keeps the
 * task open and valid, just off today's attention set until it's reconsidered. */
export async function deferNotToday(id: string): Promise<TaskResult> {
  const end = new Date();
  end.setHours(23, 59, 59, 999);
  try {
    const supabase = createSupabaseBrowserClient();
    const { error } = await supabase
      .from('personal_tasks')
      .update({ snoozed_until: end.toISOString(), updated_at: new Date().toISOString() })
      .eq('id', id);
    if (error) return { ok: false, error: error.message };
    return { ok: true, id };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Failed to update task.' };
  }
}

/** Behavioural status sentence (spec §8) — machine workload ≠ human
 * workload, so this never just echoes raw counts. */
export function buildStatusSentence(opts: { todayCount: number; waitingCount: number; capacityLow?: boolean }): string {
  const { todayCount, waitingCount, capacityLow } = opts;
  if (capacityLow && todayCount > 0) {
    return `Capacity looks limited today. Let's keep today small. ${todayCount} thing${todayCount === 1 ? '' : 's'} worth doing.`;
  }
  if (todayCount === 0) {
    return waitingCount > 0
      ? `Nothing needs you right now. ${waitingCount} thing${waitingCount === 1 ? ' is' : 's are'} waiting on someone else.`
      : 'Nothing needs you right now.';
  }
  if (todayCount === 1) return 'One thing needs you today. Everything else can wait.';
  return `Nothing urgent. ${todayCount} things are worth doing today.`;
}

/** "Turn into a Mission" (spec §26) — calls the canonical, already-live
 * mission creation gate. Never automatic — only invoked on explicit user
 * click, per spec's "do not automatically create a Mission". */
export async function promoteToMission(task: Pick<PersonalTask, 'title' | 'context'>): Promise<TaskResult & { mission_id?: string }> {
  try {
    const resp = await fetch('/api/missions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: task.title, description: task.context ?? undefined }),
    });
    const json = await resp.json();
    if (!resp.ok) return { ok: false, error: json?.error ?? 'Failed to create mission.' };
    return { ok: true, mission_id: json?.mission?.mission_id ?? json?.mission_id };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Failed to create mission.' };
  }
}

/** Thin capacity read for the optional Human Systems hook (spec §27) — a
 * light-touch signal only ("keep today small"), never a diagnosis. Fails
 * safe to { low: false } so a read error never hides urgent items or
 * blocks the page — Ready Room does not make medical decisions. */
export async function getCapacityLevel(): Promise<{ low: boolean }> {
  try {
    const resp = await fetch('/api/human-systems?domain=recovery');
    if (!resp.ok) return { low: false };
    const json = await resp.json();
    const band = json?.capacity_band ?? json?.kpis?.capacity_band;
    return { low: band === 'limited' || band === 'rest' };
  } catch {
    return { low: false };
  }
}

// ── Write ─────────────────────────────────────────────────────────────────────

export interface TaskResult {
  ok: boolean;
  id?: string;
  error?: string;
}

export interface NewTaskInput {
  title: string;
  context?: string;
  category?: TaskCategory;
  urgency?: number;
  importance?: number;
  effort_minutes?: number;
  due_date?: string | null;
  micro_action?: string | null;
  mvp_note?: string | null;
  source_capture_id?: string | null;
  follow_through_mode?: FollowThroughMode;
}

export async function createTask(input: NewTaskInput): Promise<TaskResult> {
  const title = input.title.trim();
  if (!title) return { ok: false, error: 'Title is required.' };

  const payload = {
    title,
    context: input.context?.trim() || null,
    category: input.category ?? 'task',
    urgency: input.urgency ?? 3,
    importance: input.importance ?? 3,
    effort_minutes: input.effort_minutes ?? 30,
    work_state: 'captured' as WorkState,
    due_date: input.due_date ?? null,
    micro_action: input.micro_action ?? null,
    mvp_note: input.mvp_note ?? null,
    source_capture_id: input.source_capture_id ?? null,
    follow_through_mode: input.follow_through_mode ?? 'normal',
  };

  try {
    const supabase = createSupabaseBrowserClient();
    const { data, error } = await supabase
      .from('personal_tasks')
      .insert(payload)
      .select('id')
      .maybeSingle<{ id: string }>();
    if (error) return { ok: false, error: error.message };
    return { ok: true, id: data?.id };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Failed to create task.' };
  }
}

/** Create a Ready Room task from a Capture Workbench inbox item — mirrors
 * lib/capture.ts's promoteCaptureToMission, but writes directly to
 * personal_tasks (no Command Centre proxy needed; this is a plain insert). */
export async function promoteCaptureToTask(captureId: string, title: string): Promise<TaskResult> {
  return createTask({ title, source_capture_id: captureId });
}

export async function updateTaskState(
  id: string,
  work_state: WorkState,
  extra?: {
    waiting_on?: string | null;
    stop_point?: string | null;
    restart_cue?: string | null;
    follow_through_mode?: FollowThroughMode;
  },
): Promise<TaskResult> {
  const patch: Record<string, unknown> = { work_state, updated_at: new Date().toISOString() };
  if (work_state === 'in_progress') patch.started_at = new Date().toISOString();
  if (work_state === 'completed') patch.completed_at = new Date().toISOString();
  if (extra?.waiting_on !== undefined) patch.waiting_on = extra.waiting_on;
  if (extra?.stop_point !== undefined) patch.stop_point = extra.stop_point;
  if (extra?.restart_cue !== undefined) patch.restart_cue = extra.restart_cue;
  if (extra?.follow_through_mode !== undefined) patch.follow_through_mode = extra.follow_through_mode;

  try {
    const supabase = createSupabaseBrowserClient();
    const { error } = await supabase.from('personal_tasks').update(patch).eq('id', id);
    if (error) return { ok: false, error: error.message };
    return { ok: true, id };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Failed to update task.' };
  }
}

/** Mutes/unmutes the Telegram follow-through bot for one task without
 * changing its mode — a quick escape hatch distinct from picking 'gentle'. */
export async function toggleFollowThroughPause(id: string, paused: boolean): Promise<TaskResult> {
  try {
    const supabase = createSupabaseBrowserClient();
    const { error } = await supabase
      .from('personal_tasks')
      .update({ follow_through_paused: paused, updated_at: new Date().toISOString() })
      .eq('id', id);
    if (error) return { ok: false, error: error.message };
    return { ok: true, id };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Failed to update task.' };
  }
}

export async function updateTaskFields(id: string, patch: Partial<PersonalTask>): Promise<TaskResult> {
  try {
    const supabase = createSupabaseBrowserClient();
    const { error } = await supabase
      .from('personal_tasks')
      .update({ ...patch, updated_at: new Date().toISOString() })
      .eq('id', id);
    if (error) return { ok: false, error: error.message };
    return { ok: true, id };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Failed to update task.' };
  }
}

// ── Decomposition ─────────────────────────────────────────────────────────────

export interface DecomposeResult {
  action: string | null;
  error?: string;
}

export type DecomposeMode = 'first' | 'smaller' | 'another';

/** Calls /api/ready-room/decompose (proxies Model Router). Never throws —
 * a failed/unreachable provider chain returns { action: null } so the UI
 * can fall back to "write your own first step" rather than block.
 * `mode` drives "Make it smaller" / "Try another" without creating a new
 * task or losing the original goal — see spec §17/§18. `previousAction` is
 * passed along so the router can vary its answer instead of repeating it. */
export async function decomposeTask(
  taskText: string,
  opts?: { mode?: DecomposeMode; previousAction?: string },
): Promise<DecomposeResult> {
  try {
    const resp = await fetch('/api/ready-room/decompose', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task: taskText,
        mode: opts?.mode ?? 'first',
        previous_action: opts?.previousAction,
      }),
    });
    const json = await resp.json();
    return { action: json?.action ?? null, error: json?.error };
  } catch (err) {
    return { action: null, error: err instanceof Error ? err.message : 'Decompose failed.' };
  }
}
