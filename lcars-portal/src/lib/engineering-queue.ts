'use client';

/**
 * Mobile Engineering Queue (MSN-IOS-001 WP5).
 *
 * Reuse-first: reads the SAME sources the desktop Engineering deck already uses
 * — `build_request_inbox` (governance triage queue, migration 0015) and the
 * `mission_delivery` view (EDO instrumentation, migration 0023, via delivery.ts).
 * No new engineering backend.
 *
 * Normalises the various real status strings into the canonical engineering
 * lifecycle the mission mandates:
 *   Pending Triage → Assigned → In Progress → Awaiting Review → Completed
 */

import { createSupabaseBrowserClient } from './supabase-browser';
import { fetchDeliveryRows, detectBottlenecks, type DeliveryRow } from './delivery';

export type Lifecycle =
  | 'pending_triage'
  | 'assigned'
  | 'in_progress'
  | 'awaiting_review'
  | 'completed'
  | 'rejected';

export const LIFECYCLE_ORDER: Lifecycle[] = [
  'pending_triage',
  'assigned',
  'in_progress',
  'awaiting_review',
  'completed',
];

export const LIFECYCLE_LABEL: Record<Lifecycle, string> = {
  pending_triage: 'Pending Triage',
  assigned: 'Assigned',
  in_progress: 'In Progress',
  awaiting_review: 'Awaiting Review',
  completed: 'Completed',
  rejected: 'Rejected',
};

export const LIFECYCLE_TONE: Record<Lifecycle, 'neutral' | 'command' | 'medical' | 'status' | 'operations'> = {
  pending_triage: 'neutral',
  assigned: 'command',
  in_progress: 'medical',
  awaiting_review: 'command',
  completed: 'status',
  rejected: 'operations',
};

/** Map any real status / delivery_state to a canonical lifecycle bucket. */
export function normalizeLifecycle(raw: string | null | undefined): Lifecycle {
  const s = String(raw ?? '').toLowerCase();
  if (/(reject|cancel)/.test(s)) return 'rejected';
  if (/(deliver|complete|closed|done|merged|validated_closed)/.test(s)) return 'completed';
  if (/(review|awaiting|validated)/.test(s)) return 'awaiting_review';
  if (/(running|in_progress|in-progress|building|active)/.test(s)) return 'in_progress';
  if (/(approved|assigned|planned|accepted)/.test(s)) return 'assigned';
  // pending_triage, pending, proposed, triage, new, blocked-from-triage
  return 'pending_triage';
}

export interface QueueItem {
  id: string;
  title: string;
  summary: string | null;
  rawStatus: string;
  lifecycle: Lifecycle;
  blocked: boolean;
  source: 'build' | 'delivery';
  priority: string | null;
  prUrl: string | null;
  ageDays: number | null;
  createdAt: string | null;
  /** A short, concrete next action for this item. */
  nextAction: string;
  /** MSN-0352: non-null only when this row is an AI-proposed action
   * (create_mission | create_handoff | log_decision) awaiting Captain
   * approval - never executed until approved via
   * /api/build-request/[id]/approve-action. Null for every traditional
   * build request, which is the vast majority of this queue. */
  actionType: string | null;
}

interface BuildRow {
  id?: string;
  request_id: string;
  title: string;
  summary: string | null;
  status: string;
  source: string | null;
  suggested_next_step?: string | null;
  created_at: string;
  action_type?: string | null;
}

function nextActionFor(lifecycle: Lifecycle, blocked: boolean, suggested?: string | null): string {
  if (blocked) return 'Unblock — review the blocker and clear it or reassign.';
  if (suggested && suggested.trim()) return suggested.trim();
  switch (lifecycle) {
    case 'pending_triage': return 'Triage — accept, reject, or set priority.';
    case 'assigned': return 'Start — move into build.';
    case 'in_progress': return 'Progress — drive to a reviewable state / open PR.';
    case 'awaiting_review': return 'Review — approve or reject this item.';
    case 'completed': return 'Done — no action needed.';
    case 'rejected': return 'Closed — rejected.';
  }
}

export interface EngineeringQueueData {
  items: QueueItem[];
  counts: Record<Lifecycle, number>;
  blockers: { title: string; detail: string; severity: string }[];
  nextAction: QueueItem | null;
  isLive: boolean;
}

const EMPTY_COUNTS = (): Record<Lifecycle, number> => ({
  pending_triage: 0, assigned: 0, in_progress: 0, awaiting_review: 0, completed: 0, rejected: 0,
});

export async function fetchEngineeringQueue(): Promise<EngineeringQueueData> {
  const items: QueueItem[] = [];
  let isLive = false;

  // 1) Build request inbox (governance triage queue) — reuse existing table.
  try {
    const supabase = createSupabaseBrowserClient();
    const { data } = await supabase
      .from('build_request_inbox')
      .select('id, request_id, title, summary, status, source, suggested_next_step, created_at, action_type')
      .order('created_at', { ascending: false })
      .limit(40);
    if (data?.length) {
      isLive = true;
      for (const r of data as BuildRow[]) {
        const lifecycle = normalizeLifecycle(r.status);
        const blocked = /block/.test(String(r.status).toLowerCase());
        items.push({
          id: r.id ?? r.request_id,
          title: r.title,
          summary: r.summary,
          rawStatus: r.status,
          lifecycle,
          blocked,
          source: 'build',
          priority: null,
          prUrl: null,
          ageDays: ageInDays(r.created_at),
          createdAt: r.created_at,
          nextAction: nextActionFor(lifecycle, blocked, r.suggested_next_step),
          actionType: r.action_type ?? null,
        });
      }
    }
  } catch {
    /* degrade */
  }

  // 2) Mission delivery view — reuse existing fetcher (in-flight engineering work).
  let rows: DeliveryRow[] = [];
  try {
    rows = await fetchDeliveryRows();
    if (rows.length) isLive = true;
    for (const r of rows) {
      const lifecycle = normalizeLifecycle(r.delivery_state);
      const blocked = r.delivery_state === 'blocked';
      // Skip closed/archived noise unless they're recent — keep list tight for mobile.
      if (['closed', 'archived'].includes(r.delivery_state) && (r.age_days ?? 0) > 7) continue;
      items.push({
        id: `del-${r.title}`,
        title: r.title,
        summary: null,
        rawStatus: r.delivery_state,
        lifecycle,
        blocked,
        source: 'delivery',
        priority: r.priority_norm,
        prUrl: r.pr_url,
        ageDays: r.age_days,
        createdAt: null,
        nextAction: nextActionFor(lifecycle, blocked),
        actionType: null,
      });
    }
  } catch {
    /* degrade */
  }

  // Counts by lifecycle.
  const counts = EMPTY_COUNTS();
  for (const it of items) counts[it.lifecycle] += 1;

  // Blockers (reuse delivery bottleneck detector).
  const blockers = detectBottlenecks(rows)
    .filter((b) => b.severity === 'critical' || b.severity === 'high')
    .map((b) => ({ title: b.title, detail: b.detail, severity: b.severity }));

  // Next engineering action: blocked > awaiting_review > pending_triage.
  const pickOrder: Lifecycle[] = ['awaiting_review', 'pending_triage', 'in_progress', 'assigned'];
  const blockedItem = items.find((i) => i.blocked && i.lifecycle !== 'completed' && i.lifecycle !== 'rejected');
  let nextAction: QueueItem | null = blockedItem ?? null;
  if (!nextAction) {
    for (const lc of pickOrder) {
      const found = items.find((i) => i.lifecycle === lc);
      if (found) { nextAction = found; break; }
    }
  }

  return { items, counts, blockers, nextAction, isLive };
}

function ageInDays(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.round((Date.now() - t) / 86_400_000));
}

/**
 * Approve / reject a review item by updating build_request_inbox.status.
 * Reuses the existing table. Reports the real outcome — if the project's RLS
 * does not permit the authenticated role to write, the error is surfaced rather
 * than silently swallowed.
 */
export async function setQueueItemStatus(
  item: QueueItem,
  decision: 'approved' | 'rejected',
): Promise<{ ok: boolean; error?: string }> {
  if (item.source !== 'build') {
    return { ok: false, error: 'Only build-inbox items can be approved here.' };
  }
  try {
    const supabase = createSupabaseBrowserClient();
    const { data, error } = await supabase
      .from('build_request_inbox')
      .update({ status: decision })
      .eq('id', item.id)
      .select('id');
    if (error) return { ok: false, error: error.message };
    if (!data || data.length === 0) {
      return { ok: false, error: 'No row updated — this role may not have write access (RLS).' };
    }
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Update failed.' };
  }
}
