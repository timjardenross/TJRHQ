// HQ Decisions: one inbox over the existing approval mechanisms.
//
// HQ owns no approval logic. Every action here calls the same governed
// function or route the existing workbench uses (decide.ts, the
// approve-action route, ...), adding only an opt-in compare-and-set guard so
// a decision already made in another interface cannot be applied twice.
import { approveDecideItem, fetchDecideQueue, holdDecideItem, type DecideItem } from '@/lib/decide';
import { actOnBrief, actOnDoc, actOnImprovement, loadBriefDecisions, loadDocDecisions, loadImprovementDecisions, type BriefRef, type DocRef, type ImprovementRef } from './decisionSources';
import type { HqDecision, HqPackage } from './model';

const AI_ACTION_COPY: Record<string, { ifApprove: string; recommendation: string; undoable: boolean }> = {
  create_mission: {
    ifApprove: 'A new mission is created from this proposal.',
    recommendation: 'Approve if you want this work started.',
    undoable: false,
  },
  log_decision: {
    ifApprove: 'A decision is recorded in the decision log.',
    recommendation: 'Approve if the wording reflects what you decided.',
    undoable: false,
  },
  publish_content: {
    ifApprove: 'The content is published. This cannot be undone.',
    recommendation: 'Approve only after reading the content.',
    undoable: false,
  },
};

const AI_TITLE_PREFIX: Record<string, string> = {
  create_mission: 'Create mission',
  log_decision: 'Log decision',
  publish_content: 'Publish',
};

/** A readable title from the existing question text, which wraps the real
 *  title in quotes ("Approve build request "X"?"). */
export function titleFor(item: DecideItem): string {
  const quoted = item.question.match(/"(.+)"/)?.[1];
  const base = quoted ?? item.question.replace(/^Approve\s+/i, '').replace(/\?$/, '');
  const prefix = item.actionType ? AI_TITLE_PREFIX[item.actionType] : undefined;
  return prefix && !base.toLowerCase().startsWith(prefix.toLowerCase()) ? `${prefix}: ${base}` : base;
}

/** Map an existing DecideItem onto HQ's explanation fields. The wording is
 *  template text per source type: the underlying data carries a question and
 *  reasoning but no per-item consequences, so HQ states only what the
 *  approval route is known to do. */
export function mapDecideItem(item: DecideItem): HqDecision {
  const isAi = Boolean(item.actionType);
  const copy = item.actionType ? AI_ACTION_COPY[item.actionType] : undefined;
  const rank = item._sortRank;
  const blocked = rank >= 90;
  return {
    id: item.id,
    source: isAi ? 'ai-action' : 'engineering',
    sourceLabel: isAi ? 'AI proposal' : 'Build request',
    title: titleFor(item),
    request: item.question,
    why: item.reasoning || 'No further detail was recorded for this item.',
    recommendation: copy?.recommendation
      ?? (blocked ? 'Review first. This item is blocked.' : 'Approve if the request matches what you want built.'),
    ifApprove: copy?.ifApprove ?? 'The request moves to approved so engineering can start. You can undo this.',
    ifDefer: 'It stays in the queue. Nothing else changes.',
    need: isAi
      ? 'Required. Nothing runs until you approve it.'
      : 'Required by policy. Build requests need your approval.',
    undoable: item.undoAvailable,
    rank,
    // Only plain, reversible build requests that are not blocked are routine.
    routine: !isAi && item.undoAvailable && !blocked,
    legacyHref: '/decisions',
    ref: item,
  };
}

/** Group routine items into one package. A package never contains an item
 *  that needs judgement or cannot be undone, and only forms from 3+ lines. */
export function buildPackage(decisions: HqDecision[], minLines = 3): { pkg: HqPackage | null; rest: HqDecision[] } {
  const routine = decisions.filter((d) => d.routine);
  if (routine.length < minLines) return { pkg: null, rest: decisions };
  const ids = new Set(routine.map((d) => d.id));
  return {
    pkg: { id: 'pkg:routine-build-requests', title: `Routine build requests (${routine.length})`, lines: routine },
    rest: decisions.filter((d) => !ids.has(d.id)),
  };
}

export interface HqDecisionLoad {
  decisions: HqDecision[];
  /** Sources that failed to load, by label. Empty when everything loaded. */
  errors: string[];
}

export async function loadHqDecisions(): Promise<HqDecisionLoad> {
  const errors: string[] = [];
  const decisions: HqDecision[] = [];
  const [eng, briefs, docs, imps] = await Promise.all([
    fetchDecideQueue().then((items) => items.map(mapDecideItem)).catch(() => null),
    loadBriefDecisions(),
    loadDocDecisions(),
    loadImprovementDecisions(),
  ]);
  if (eng) decisions.push(...eng); else errors.push('Build requests');
  if (briefs) decisions.push(...briefs); else errors.push('Brief gate');
  if (docs) decisions.push(...docs); else errors.push('Knowledge review');
  if (imps) decisions.push(...imps); else errors.push('Improvements');
  decisions.sort((a, b) => b.rank - a.rank);
  return { decisions, errors };
}

export interface HqActionResult {
  ok: boolean;
  error?: string;
  /** True when the item had already been decided somewhere else. */
  alreadyDecided?: boolean;
  /** Present when the decision can be reversed. */
  undo?: () => Promise<{ ok: boolean; error?: string }>;
}

// Ids with an action in flight inside this page: a second click on the same
// item is ignored until the first settles.
const inFlight = new Set<string>();

export function isActing(id: string): boolean {
  return inFlight.has(id);
}

async function once<T extends HqActionResult>(id: string, run: () => Promise<T>): Promise<HqActionResult> {
  if (inFlight.has(id)) return { ok: false, error: 'Already in progress.' };
  inFlight.add(id);
  try {
    return await run();
  } finally {
    inFlight.delete(id);
  }
}

const isEngineering = (d: HqDecision) => d.source === 'engineering' || d.source === 'ai-action';

interface ServerReply { ok: boolean; status: number; error?: string }

/** Plain build requests are decided by the server route, which applies the
 *  change as one conditional UPDATE. A 409 means someone (HQ in another tab,
 *  or an existing workbench that wrote first) already decided it. */
async function decideBuildRequest(
  item: DecideItem,
  body: { action: 'approve' | 'decline' | 'undo'; expectedStatus?: string; restoreStatus?: string },
): Promise<ServerReply> {
  try {
    const resp = await fetch(`/api/hq/decisions/build-request/${encodeURIComponent(item.rawId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...body, question: item.question }),
    });
    let json: { error?: string } = {};
    try { json = await resp.json(); } catch { /* non-JSON */ }
    return { ok: resp.ok, status: resp.status, error: json.error };
  } catch (e) {
    return { ok: false, status: 0, error: e instanceof Error ? e.message : 'Network error' };
  }
}

const alreadyDecided = (r: ServerReply) => r.status === 409 && r.error === 'already_decided';
const serverMessage = (r: ServerReply) =>
  alreadyDecided(r) ? 'Already decided elsewhere. Nothing was changed.'
  : r.status === 409 ? 'This item must be approved through its own action route.'
  : r.error ?? 'That did not work. Nothing was changed.';

export function approveHqDecision(d: HqDecision): Promise<HqActionResult> {
  return once(d.id, async () => {
    if (d.source === 'engineering') {
      const item = d.ref as DecideItem;
      const r = await decideBuildRequest(item, { action: 'approve', expectedStatus: item.priorStatus });
      if (!r.ok) return { ok: false, error: serverMessage(r), alreadyDecided: alreadyDecided(r) };
      return {
        ok: true,
        undo: d.undoable
          ? async () => {
              const u = await decideBuildRequest(item, { action: 'undo', restoreStatus: item.priorStatus });
              return { ok: u.ok, error: u.ok ? undefined : serverMessage(u) };
            }
          : undefined,
      };
    }
    if (d.source === 'ai-action') {
      // Executed by the existing approve-action route, which refuses (409)
      // anything no longer awaiting review.
      const res = await approveDecideItem(d.ref as DecideItem, { guardStatus: true });
      if (!res.ok) return { ok: false, error: res.error, alreadyDecided: res.alreadyDecided };
      return { ok: true };
    }
    if (d.source === 'brief') return actOnBrief(d.ref as BriefRef);
    if (d.source === 'knowledge') return actOnDoc(d.ref as DocRef, 'approved_summary');
    if (d.source === 'improvement') return actOnImprovement(d.ref as ImprovementRef, 'approve_improvement');
    return { ok: false, error: 'This decision type is not connected yet.' };
  });
}

export function deferHqDecision(d: HqDecision): Promise<HqActionResult> {
  return once(d.id, async () => {
    // Defer deliberately changes nothing in the source system: the item
    // reappears next time, honestly undecided. Only build requests keep a
    // ledger entry for the deferral, exactly as the existing Decide page does.
    if (isEngineering(d)) {
      const res = await holdDecideItem(d.ref as DecideItem);
      return { ok: res.ok };
    }
    return { ok: true };
  });
}

export function declineHqDecision(d: HqDecision): Promise<HqActionResult> {
  return once(d.id, async () => {
    if (isEngineering(d)) {
      const item = d.ref as DecideItem;
      const r = await decideBuildRequest(item, { action: 'decline', expectedStatus: item.priorStatus });
      return { ok: r.ok, error: r.ok ? undefined : serverMessage(r), alreadyDecided: alreadyDecided(r) };
    }
    if (d.source === 'knowledge') return actOnDoc(d.ref as DocRef, 'rejected');
    if (d.source === 'improvement') return actOnImprovement(d.ref as ImprovementRef, 'reject');
    // A brief cannot be declined from here: the existing gate has no decline
    // step (stand-down and escalation are separate governed actions).
    return { ok: false, error: 'This decision cannot be declined here. Open it in the existing workbench.' };
  });
}
