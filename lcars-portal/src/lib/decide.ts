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
//
// MSN-0352: engineering items now include AI-proposed operational actions
// (create_mission / log_decision, queued by lib/ai-actions.ts's
// parseAndProposeActions instead of executed directly) alongside ordinary
// build requests - same table, same queue, same Approve/Hold/Undo model.
// Approving a proposed create_mission/log_decision routes through
// POST /api/build-request/[id]/approve-action, which performs the real
// mutation only at that point; approving a plain build request or a
// proposed create_handoff still just flips build_request_inbox.status, as
// it always has.

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
  /** MSN-0352: non-null only for an AI-proposed action (create_mission |
   * create_handoff | log_decision) awaiting approval. Drives both the
   * question/reasoning text and which route approveDecideItem calls. */
  actionType?: string | null;
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

/** MSN-0352: plain-fact reasoning for an AI-proposed action, distinct from
 * an ordinary build request - names what will actually happen on approval,
 * never a claim that anything has happened yet. */
export function proposedActionReasoning(item: QueueItem): string {
  if (item.actionType === 'create_mission') {
    return `Proposed by an AI advisor. Approving this will create a new mission. ${item.summary ?? ''}`.trim();
  }
  if (item.actionType === 'log_decision') {
    return `Proposed by an AI advisor. Approving this will log a decision. ${item.summary ?? ''}`.trim();
  }
  return `Proposed by an AI advisor. ${item.summary ?? ''}`.trim();
}

function questionFor(item: QueueItem): string {
  if (item.actionType === 'create_mission') return `Approve mission creation: "${item.title}"?`;
  if (item.actionType === 'log_decision') return `Approve decision log: "${item.title}"?`;
  return `Approve build request "${item.title}"?`;
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
    return reviewable.map((i) => {
      // MSN-0352: create_mission/log_decision/publish_content each perform a
      // real, irreversible mutation on approval (a mission row, a decision
      // row, a comms_content publish) - same principle as mission approvals
      // already applied here (undoAvailable: false, "there is no route
      // back"). undoDecideItem only ever restores build_request_inbox's own
      // priorStatus, never the mutation these route to, so offering undo
      // here would silently fail to reverse the real effect. create_handoff
      // and plain build requests are unchanged: approval is just a status
      // flip, so undo (restoring priorStatus) is still safe.
      const isIrreversibleProposal =
        i.actionType === 'create_mission' || i.actionType === 'log_decision' || i.actionType === 'publish_content';
      return {
        id: `eng:${i.id}`,
        source: 'engineering' as const,
        rawId: i.id,
        question: questionFor(i),
        reasoning: i.actionType ? proposedActionReasoning(i) : engineeringReasoning(i),
        domainTag: 'Engineering',
        evidenceHref: i.prUrl ?? undefined,
        undoAvailable: !isIrreversibleProposal,
        priorStatus: i.rawStatus,
        actionType: i.actionType,
        _sortRank: (i.blocked ? 90 : 60) + Math.min(15, i.ageDays ?? 0),
      };
    });
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

/** Returns the written row's id (EOS Phase 3 Priority 2: this is the id
 * Communications Studio's Decision Brief needs to launch with automatic
 * context - see lib/commsStudio.ts's assembleDecisionBrief()) - or null on
 * any failure. A ledger write failure must never block the real decision
 * it's recording, so this degrades to null rather than throwing; the
 * caller just won't be able to offer a "Draft a Decision Brief" link for
 * that one action. */
async function writeLedger(entry: {
  question: string;
  source: DecideSource;
  item_ref: string;
  action: DecideAction;
  undo_available: boolean;
  prior_status?: string;
}): Promise<string | null> {
  try {
    const supabase = createSupabaseBrowserClient();
    const { data } = await supabase.from('decide_ledger').insert(entry).select('id').single();
    return data?.id ?? null;
  } catch {
    return null;
  }
}

export async function approveDecideItem(item: DecideItem): Promise<{ ok: boolean; error?: string; ledgerId?: string | null }> {
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
  } else if (item.actionType === 'create_mission' || item.actionType === 'log_decision' || item.actionType === 'publish_content') {
    // MSN-0352: the real mutation only happens here, on explicit Captain
    // approval of this exact item - never before, never automatically.
    try {
      const resp = await fetch(`/api/build-request/${encodeURIComponent(item.rawId)}/approve-action`, {
        method: 'POST',
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

  const ledgerId = await writeLedger({
    question: item.question,
    source: item.source,
    item_ref: item.rawId,
    action: 'approve',
    undo_available: result.ok && item.undoAvailable,
    prior_status: item.priorStatus,
  });

  return { ...result, ledgerId };
}

/** Hold defers - it deliberately does not call any source route. The item's
 * underlying status is untouched, so it simply reappears in the queue next
 * time. This is the honest behaviour for "come back to this later": nothing
 * was decided, so nothing should look decided. */
export async function holdDecideItem(item: DecideItem): Promise<{ ok: boolean; ledgerId?: string | null }> {
  const ledgerId = await writeLedger({
    question: item.question,
    source: item.source,
    item_ref: item.rawId,
    action: 'hold',
    undo_available: true,
  });
  return { ok: true, ledgerId };
}

/** Reverses an approval just made. Only ever called when item.undoAvailable
 * is true - mission approvals never set that flag (see DecideItem doc), so
 * this path is only reachable for engineering items today. Restores the
 * captured priorStatus via the same build_request_inbox update mechanism
 * setQueueItemStatus already uses, rather than a generic "rejected" call -
 * a real reversal to the prior state, not a second terminal decision
 * relabelled as one. */
export interface DecideHistoryEntry {
  id: string;
  question: string;
  source: DecideSource;
  action: DecideAction;
  decided_at: string;
  outcome: string | null;
}

/** Past decide_ledger rows, most recent first - read-only, for retrospective
 * outcome capture (see updateDecideOutcome below). Degrades to an empty list
 * on any failure rather than throwing, same convention as the rest of this
 * file's read paths. */
export async function fetchDecideHistory(limit = 20): Promise<DecideHistoryEntry[]> {
  try {
    const supabase = createSupabaseBrowserClient();
    const { data, error } = await supabase
      .from('decide_ledger')
      .select('id, question, source, action, decided_at, outcome')
      .order('decided_at', { ascending: false })
      .limit(limit);
    if (error || !data) return [];
    return data as DecideHistoryEntry[];
  } catch {
    return [];
  }
}

/** Retrospective outcome capture for a past Decide action. decide_ledger.outcome
 * is nullable and, until this function, had no writer anywhere in the codebase
 * (see migration 0074's own comment: "no outcome-tracking mechanism exists yet").
 * Deliberately separate from writeLedger - this updates an existing row by its
 * id rather than inserting a new one, since the action (approve/hold/undo) was
 * already recorded at decision time and outcome is learned later, if ever. */
export async function updateDecideOutcome(ledgerId: string, outcome: string): Promise<{ ok: boolean; error?: string }> {
  try {
    const supabase = createSupabaseBrowserClient();
    const { data, error } = await supabase
      .from('decide_ledger')
      .update({ outcome })
      .eq('id', ledgerId)
      .select('id');
    if (error) return { ok: false, error: error.message };
    if (!data || data.length === 0) return { ok: false, error: 'No row updated.' };
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function undoDecideItem(item: DecideItem): Promise<{ ok: boolean; error?: string; ledgerId?: string | null }> {
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

  const ledgerId = await writeLedger({
    question: item.question,
    source: item.source,
    item_ref: item.rawId,
    action: 'undo',
    undo_available: false,
    prior_status: item.priorStatus,
  });

  return { ok: true, ledgerId };
}
