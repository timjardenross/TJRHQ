// MSN-0345: unified Captain Decisions Inbox data layer.
//
// Merges 3 existing, already-governed decision sources into one prioritised
// list WITHOUT changing any of their underlying governance — each source's
// real write path (mission approve/reject API, engineering's
// setQueueItemStatus) is reused as-is, not reimplemented. This file only
// fetches, maps onto the canonical ApprovalQueue contract, and computes one
// shared priority order across sources.
//
// A 3rd source — Operational Intelligence recommendations flagged
// `requires_approval: true` (core/platform/captain_brief_contract.py) — is
// wired in but will show zero items today: that field exists in the backend
// contract and is never set True anywhere in the codebase (confirmed by
// direct grep, MSN-0345). This is not a bug in this file; it's an honest
// reflection of the current platform. The moment any domain starts setting
// it, this inbox surfaces it with no further frontend change required.

import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { fetchEngineeringQueue, setQueueItemStatus, type QueueItem } from '@/lib/engineering-queue';
import type { ApprovalQueueItem } from '@/components/ApprovalQueue';

export type DecisionSource = 'mission' | 'engineering' | 'intelligence';

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

interface QueueMission {
  mission_id: string;
  title: string;
  status: string;
  priority: string | null;
  created_by: string | null;
  created_at: string | null;
}

const AWAITING_STATUSES = ['Awaiting Captain Approval', 'Awaiting XO Approval'];

function shortMissionId(missionId: string): string {
  const m = missionId.match(/(\d+)$/);
  return m ? m[1] : missionId;
}

// Mission priority strings observed in the registry (P0 highest .. P3 lowest,
// unset = treated as P2). Same tier order the Missions board itself uses.
function missionPriorityRank(priority: string | null): number {
  const p = (priority ?? '').toUpperCase();
  if (p.includes('P0')) return 100;
  if (p.includes('P1')) return 80;
  if (p.includes('P2') || !p) return 50;
  if (p.includes('P3')) return 20;
  return 50;
}

function ageBonus(createdAt: string | null): number {
  if (!createdAt) return 0;
  const days = (Date.now() - new Date(createdAt).getTime()) / 86_400_000;
  if (Number.isNaN(days) || days < 0) return 0;
  // Small, capped nudge — age breaks ties within a priority tier, never
  // outranks a full tier above it (max +15 vs. a 20-point tier spacing).
  return Math.min(15, Math.round(days));
}

async function fetchMissionDecisions(): Promise<DecisionItem[]> {
  try {
    const supabase = createSupabaseBrowserClient();
    const { data } = await supabase
      .from('missions')
      .select('mission_id, title, status, priority, created_by, created_at')
      .in('status', AWAITING_STATUSES)
      .order('created_at', { ascending: false })
      .limit(20);
    const missions = (data ?? []) as QueueMission[];
    return missions.map((m) => ({
      id: `mission:${m.mission_id}`,
      source: 'mission' as const,
      code: shortMissionId(m.mission_id),
      title: m.title,
      href: `/missions/${encodeURIComponent(m.mission_id)}`,
      detail: `${m.status}${m.priority ? ` · ${m.priority}` : ''}${m.created_by ? ` · ${m.created_by}` : ''}`,
      priorityRank: missionPriorityRank(m.priority) + ageBonus(m.created_at),
    }));
  } catch {
    return [];
  }
}

async function fetchEngineeringDecisions(): Promise<DecisionItem[]> {
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
  counts: { mission: number; engineering: number; intelligence: number };
}

export async function fetchDecisionsInbox(): Promise<DecisionsInboxData> {
  const [missions, engineering, intelligence] = await Promise.all([
    fetchMissionDecisions(),
    fetchEngineeringDecisions(),
    fetchIntelligenceDecisions(),
  ]);
  const actionable = [...missions, ...engineering].sort((a, b) => b.priorityRank - a.priorityRank);
  return {
    actionable,
    intelligence,
    counts: { mission: missions.length, engineering: engineering.length, intelligence: intelligence.length },
  };
}

/**
 * Dispatches a decision to the correct real, existing governed route based
 * on the `source:` prefix encoded in the merged item's id — never a new
 * write path. Mirrors CaptainApprovalQueue's mission call and Engineering
 * Queue's `setQueueItemStatus` call exactly; this function does not
 * duplicate their logic, it routes to it.
 */
export async function decideItem(
  item: DecisionItem,
  decision: 'approve' | 'reject',
  reason?: string,
): Promise<{ ok: boolean; error?: string }> {
  const [, rawId] = item.id.split(/:(.+)/);
  if (item.source === 'mission') {
    try {
      const resp = await fetch(`/api/missions/${encodeURIComponent(rawId)}/${decision}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: 'LCARS', owner: 'Captain', ...(reason ? { reason } : {}) }),
      });
      const data = await resp.json();
      return resp.ok ? { ok: true } : { ok: false, error: data.error ?? 'Failed' };
    } catch (e) {
      return { ok: false, error: String(e) };
    }
  }
  if (item.source === 'engineering') {
    // setQueueItemStatus expects a QueueItem shaped object; reconstruct the
    // minimal shape it actually reads (id + source) rather than re-fetching.
    const fakeQueueItem = { id: rawId, source: 'build' } as QueueItem;
    return setQueueItemStatus(fakeQueueItem, decision === 'approve' ? 'approved' : 'rejected');
  }
  return { ok: false, error: 'Unknown decision source' };
}
