'use client';

// STARSHIP-REDESIGN.md §5: Decide. One item at a time, full-width, plain
// question, plain reasoning, domain tag, evidence if available. No table,
// no ranked list, no Priority Engine claim, no fake recommendation.
//
// Sources are exactly the two governed, already-real approve/reject routes:
// mission approvals (reused from lib/decisions.ts, unchanged) and
// engineering approvals (build_request_inbox via lib/engineering-queue.ts,
// unchanged). Knowledge Library approval items were evaluated and
// deliberately excluded this pass: its real action set is five outcomes
// (approve_metadata / approve_summary / approve_chunks / reject /
// needs_review), not the Approve/Hold/Undo model here - collapsing that
// onto a generic "Approve" button would either lose information or invent
// a mapping the source route was never designed for. That is a "not safely
// available" call, not a "the data doesn't exist" call.
//
// No Operational Intelligence decisions are invented here - there is no
// governed OI decision route to reuse, so none are shown, exactly as
// lib/decisions.ts's own header already documents for the legacy /decisions
// page.

import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { fetchMissionDecisions } from '@/lib/decisions';
import { fetchEngineeringQueue, setQueueItemStatus, type QueueItem } from '@/lib/engineering-queue';

export type DecideSource = 'mission' | 'engineering';
export type DecideAction = 'approve' | 'hold' | 'undo';

export interface DecideItem {
  /** Namespaced id, e.g. "mission:MSN-0123" or "eng:<uuid>" - matches lib/decisions.ts's convention. */
  id: string;
  source: DecideSource;
  /** The id within the source system itself (mission_id, or build_request_inbox.id). */
  rawId: string;
  question: string;
  reasoning: string;
  domainTag: string;
  evidenceHref?: string;
  /** Whether the underlying route supports reversing an approval. Missions:
   * never (the approval API's REJECTION_ELIGIBLE list excludes 'Approved',
   * enforced server-side - there is no route back). Engineering: yes, by
   * restoring the captured priorStatus via the same update mechanism
   * setQueueItemStatus already uses. */
  undoAvailable: boolean;
  /** Engineering only - the item's real status immediately before any
   * decision, captured so undo restores it exactly rather than guessing. */
  priorStatus?: string;
  /** Internal ordering only (reused from lib/decisions.ts's real, existing
   * mission-priority + engineering-blocked/priority/age heuristic) - never
   * displayed, never labeled "Priority Engine". That heuristic is a
   * disclosed placeholder (see docs/INVENTORY.md, MSN-0346 finding #2);
   * presenting it as ranking logic to the Captain would be exactly the
   * trust hazard this rewrite exists to remove. It only decides which one
   * item appears next. */
  _sortRank: number;
}

export const DECIDE_EMPTY_TITLE = 'Nothing needs your judgement right now.';
export const DECIDE_EMPTY_DETAIL = 'Mission and engineering approval queues are both clear.';

/** Plain, fact-only reasoning - no recommendation, no confidence score, no
 * ranking claim. Every clause is a real field value already fetched from
 * the governed source, never an inference about what the Captain should do. */
export function missionReasoning(detail: string | undefined): string {
  return `This mission is awaiting your decision. ${detail ?? 'No further detail recorded.'}`;
}

export function engineeringReasoning(item: QueueItem): string {
  const bits: string[] = [`Status: ${item.rawStatus}.`];
  if (item.blocked) bits.push('Currently blocked.');
  if (item.priority) bits.push(`Priority ${item.priority}.`);
  if (item.ageDays != null) bits.push(`${item.ageDays} day${item.ageDays === 1 ? '' : 's'} old.`);
  return bits.join(' ');
}

async function fetchDecideMissionItems(): Promise<DecideItem[]> {
  const missions = await fetchMissionDecisions();
  return missions.map((m) => ({
    id: m.id,
    source: 'mission' as const,
    rawId: m.id.split(/:(.+)/)[1] ?? m.id,
    question: `Approve mission "${m.title}"?`,
    reasoning: missionReasoning(m.detail),
    domainTag: 'Mission',
    evidenceHref: m.href,
    undoAvailable: false,
    _sortRank: m.priorityRank,
  }));
}

async function fetchDecideEngineeringItems(): Promise<DecideItem[]> {
  try {
    const data = await fetchEngineeringQueue();
    const reviewable = data.items.filter((i) => i.lifecycle === 'awaiting_review' && i.source === 'build');
    return reviewable.map((i) => ({
      id: `eng:${i.id}`,
      source: 'engineering' as const,
      rawId: i.id,
      question: `Approve build request "${i.title}"?`,
      reasoning: engineeringReasoning(i),
      domainTag: 'Engineering',
      evidenceHref: i.prUrl ?? undefined,
      undoAvailable: true,
      priorStatus: i.rawStatus,
      _sortRank: (i.blocked ? 90 : 60) + Math.min(15, i.ageDays ?? 0),
    }));
  } catch {
    return [];
  }
}

export async function fetchDecideQueue(): Promise<DecideItem[]> {
  const [missions, engineering] = await Promise.all([
    fetchDecideMissionItems(),
    fetchDecideEngineeringItems(),
  ]);
  return [...missions, ...engineering].sort((a, b) => b._sortRank - a._sortRank);
}

/** Count only - for Home's "Needs you" line. Same real sources, no fetch of
 * the fuller per-item shape Decide itself needs. */
export async function fetchDecideCount(): Promise<number> {
  const items = await fetchDecideQueue();
  return items.length;
}

async function writeLedger(entry: {
  question: string;
  source: DecideSource;
  item_ref: string;
  action: DecideAction;
  undo_available: boolean;
  prior_status?: string;
}): Promise<void> {
  try {
    const supabase = createSupabaseBrowserClient();
    await supabase.from('decide_ledger').insert(entry);
  } catch {
    // Ledger write failure must never block the real decision it's
    // recording - the source-of-truth action already happened (or, for
    // hold, deliberately didn't).
  }
}

export async function approveDecideItem(item: DecideItem): Promise<{ ok: boolean; error?: string }> {
  let result: { ok: boolean; error?: string };
  if (item.source === 'mission') {
    try {
      const resp = await fetch(`/api/missions/${encodeURIComponent(item.rawId)}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: 'Decide', owner: 'Captain' }),
      });
      const data = await resp.json();
      result = resp.ok ? { ok: true } : { ok: false, error: data.error ?? 'Failed' };
    } catch (e) {
      result = { ok: false, error: String(e) };
    }
  } else {
    const fakeQueueItem = { id: item.rawId, source: 'build' } as QueueItem;
    result = await setQueueItemStatus(fakeQueueItem, 'approved');
  }

  await writeLedger({
    question: item.question,
    source: item.source,
    item_ref: item.rawId,
    action: 'approve',
    undo_available: result.ok && item.undoAvailable,
    prior_status: item.priorStatus,
  });

  return result;
}

/** Hold defers - it deliberately does not call any source route. The item's
 * underlying status is untouched, so it simply reappears in the queue next
 * time. This is the honest behaviour for "come back to this later": nothing
 * was decided, so nothing should look decided. */
export async function holdDecideItem(item: DecideItem): Promise<{ ok: boolean }> {
  await writeLedger({
    question: item.question,
    source: item.source,
    item_ref: item.rawId,
    action: 'hold',
    undo_available: true,
  });
  return { ok: true };
}

/** Reverses an approval just made. Only ever called when item.undoAvailable
 * is true - mission approvals never set that flag (see DecideItem doc), so
 * this path is only reachable for engineering items today. Restores the
 * captured priorStatus via the same build_request_inbox update mechanism
 * setQueueItemStatus already uses, rather than a generic "rejected" call -
 * a real reversal to the prior state, not a second terminal decision
 * relabelled as one. */
export async function undoDecideItem(item: DecideItem): Promise<{ ok: boolean; error?: string }> {
  if (!item.undoAvailable || item.source !== 'engineering' || !item.priorStatus) {
    return { ok: false, error: "Undo is not supported for this decision's source." };
  }
  try {
    const supabase = createSupabaseBrowserClient();
    const { data, error } = await supabase
      .from('build_request_inbox')
      .update({ status: item.priorStatus })
      .eq('id', item.rawId)
      .select('id');
    if (error) return { ok: false, error: error.message };
    if (!data || data.length === 0) return { ok: false, error: 'No row updated.' };
  } catch (e) {
    return { ok: false, error: String(e) };
  }

  await writeLedger({
    question: item.question,
    source: item.source,
    item_ref: item.rawId,
    action: 'undo',
    undo_available: false,
    prior_status: item.priorStatus,
  });

  return { ok: true };
}
