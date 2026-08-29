// MSN-0345: unified Captain Decisions Inbox data layer.
//
// Merges governed decision sources into one prioritised list WITHOUT
// changing any of their underlying governance — each source's real write
// path (engineering's setQueueItemStatus) is reused as-is, not
// reimplemented. This file only fetches, maps onto the canonical
// ApprovalQueue contract, and computes one shared priority order across
// sources.
//
// A 2nd source — Operational Intelligence recommendations flagged
// `requires_approval: true` (core/platform/captain_brief_contract.py) — is
// wired in but will show zero items today: that field exists in the backend
// contract and is never set True anywhere in the codebase (confirmed by
// direct grep, MSN-0345). This is not a bug in this file; it's an honest
// reflection of the current platform. The moment any domain starts setting
// it, this inbox surfaces it with no further frontend change required.
//
// 2026-08-29: the mission-approval source (fetchMissionDecisions) removed.
// Confirmed via live DB query that missions have had zero rows in an
// approval-eligible status for ~2 months and no meaningful activity since —
// the operator confirmed missions are no longer the day-to-day unit of
// work. The API routes this called (/api/missions/[id]/approve|reject) were
// removed in the same pass (see lib/decide.ts's header for the fuller note).

import { fetchEngineeringQueue, setQueueItemStatus, type QueueItem } from '@/lib/engineering-queue';
import type { ApprovalQueueItem } from '@/components/ApprovalQueue';

export type DecisionSource = 'engineering' | 'intelligence';

export interface DecisionItem extends ApprovalQueueItem {
  source: DecisionSource;
  /** Higher = more urgent. Computed once at merge time so the whole inbox sorts as one list, not grouped by source. */
  priorityRank: number;
}

export interface IntelligenceDecisionItem {
  id: string;
  description: string;
  sourceDomain: string;
  confidence: number | null;
  briefHref: string;
}

export async function fetchEngineeringDecisions(): Promise<DecisionItem[]> {
  try {
    const data = await fetchEngineeringQueue();
    const reviewable = data.items.filter((i) => i.lifecycle === 'awaiting_review' && i.source === 'build');
    return reviewable.map((i: QueueItem) => ({
      id: `eng:${i.id}`,
      source: 'engineering' as const,
      title: i.title,
      detail: `${i.rawStatus}${i.priority ? ` · ${i.priority}` : ''}${i.ageDays != null ? ` · ${i.ageDays}d old` : ''}`,
      priorityRank:
        (i.blocked ? 90 : 60) +
        (i.priority?.toLowerCase().includes('p0') ? 20 : i.priority?.toLowerCase().includes('p1') ? 10 : 0) +
        Math.min(15, i.ageDays ?? 0),
    }));
  } catch {
    return [];
  }
}

/**
 * OI recommendations flagged `requires_approval: true`. Real fetch, real
 * filter — will legitimately return [] today (see file header). Kept
 * separate from `DecisionItem`/`ApprovalQueue` rather than forced through
 * the approve/reject contract: no governed approve/reject route exists for
 * an OI recommendation today, and inventing one would be new governance,
 * which this mission explicitly does not authorise. Rendered read-only,
 * linking back to Captain's Brief — the real source of truth — rather than
 * a fake action button.
 */
async function fetchIntelligenceDecisions(): Promise<IntelligenceDecisionItem[]> {
  try {
    const resp = await fetch('/api/captain-brief');
    if (!resp.ok) return [];
    const doc = await resp.json();
    const pools: unknown[] = [...(doc.recommendations ?? []), ...(doc.priorities ?? [])];
    const out: IntelligenceDecisionItem[] = [];
    for (const raw of pools) {
      const item = raw as {
        event_id?: string | null;
        description?: string;
        reason?: string;
        domain?: string;
        confidence?: number | null;
        recommendation?: { description?: string; confidence?: number | null; requires_approval?: boolean };
        requires_approval?: boolean;
      };
      const requiresApproval = item.requires_approval === true || item.recommendation?.requires_approval === true;
      if (!requiresApproval) continue;
      out.push({
        id: item.event_id ?? `${item.domain ?? 'unknown'}:${out.length}`,
        description: item.description ?? item.recommendation?.description ?? item.reason ?? 'Untitled recommendation',
        sourceDomain: item.domain ?? 'operational-intelligence',
        confidence: item.confidence ?? item.recommendation?.confidence ?? null,
        briefHref: '/captains-brief',
      });
    }
    return out;
  } catch {
    return [];
  }
}

export interface DecisionsInboxData {
  actionable: DecisionItem[]; // sorted, highest priorityRank first
  intelligence: IntelligenceDecisionItem[]; // real, currently expected empty (see header)
  counts: { engineering: number; intelligence: number };
}

export async function fetchDecisionsInbox(): Promise<DecisionsInboxData> {
  const [engineering, intelligence] = await Promise.all([
    fetchEngineeringDecisions(),
    fetchIntelligenceDecisions(),
  ]);
  const actionable = [...engineering].sort((a, b) => b.priorityRank - a.priorityRank);
  return {
    actionable,
    intelligence,
    counts: { engineering: engineering.length, intelligence: intelligence.length },
  };
}

/**
 * Dispatches a decision to the correct real, existing governed route based
 * on the `source:` prefix encoded in the merged item's id — never a new
 * write path. Mirrors Engineering Queue's `setQueueItemStatus` call
 * exactly; this function does not duplicate its logic, it routes to it.
 */
export async function decideItem(
  item: DecisionItem,
  decision: 'approve' | 'reject',
  reason?: string,
): Promise<{ ok: boolean; error?: string }> {
  const [, rawId] = item.id.split(/:(.+)/);
  if (item.source === 'engineering') {
    // setQueueItemStatus expects a QueueItem shaped object; reconstruct the
    // minimal shape it actually reads (id + source) rather than re-fetching.
    const fakeQueueItem = { id: rawId, source: 'build' } as QueueItem;
    return setQueueItemStatus(fakeQueueItem, decision === 'approve' ? 'approved' : 'rejected');
  }
  return { ok: false, error: 'Unknown decision source' };
}
