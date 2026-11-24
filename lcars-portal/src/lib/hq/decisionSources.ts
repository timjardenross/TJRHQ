// The other approval mechanisms HQ's Decisions inbox reads and acts through.
// Every write goes to the same governed route the existing workbench uses;
// HQ adds only a re-check of the item's current state immediately before
// acting, for the routes that have no server-side state guard of their own.
import { getJson } from './data';
import type { HqDecision } from './model';

export interface BriefRef { kind: 'brief'; briefId: string; status: 'IN_REVIEW' | 'QA_PASSED' }
export interface DocRef { kind: 'doc'; docId: string }
export interface ImprovementRef { kind: 'improvement'; opportunityId: string; mayApproveHere: boolean }

interface BriefRow { brief_id: string; generated_at: string; approval_status: string | null; executive_snapshot: string | null; bottom_line?: string | null; overall_risk: string | null }
interface DocRow { id: string; filename: string; summary: string | null; sensitivity: string | null; memory_recommendation: string | null; category: string | null }
interface OppRow {
  opportunity_id: string; title: string; summary: string; why_relevant: string; change_class: string;
  value: string | null; risk_level?: string | null; stage_detail?: string; lifecycle_state?: string;
}

const RECENT_HOURS = 48;
// Classes the existing Improvements workbench refuses to approve outside a mission.
const MISSION_ONLY = new Set(['capability', 'product_improvement', 'architecture']);

export function briefDecision(b: BriefRow): HqDecision | null {
  const status = b.approval_status;
  if (status !== 'IN_REVIEW' && status !== 'QA_PASSED') return null;
  const age = Date.now() - new Date(b.generated_at).getTime();
  if (!(age >= 0 && age <= RECENT_HOURS * 3_600_000)) return null; // old IN_REVIEW briefs pre-date auto-publish
  const publish = status === 'QA_PASSED';
  return {
    id: `brief:${b.brief_id}`, source: 'brief', sourceLabel: 'Brief gate',
    title: publish ? `Publish brief ${b.brief_id}` : `Mark brief ${b.brief_id} QA passed`,
    request: publish ? 'Publish this brief. QA has passed.' : 'Confirm this brief has passed quality review.',
    why: b.bottom_line ?? b.executive_snapshot ?? 'No summary was recorded for this brief.',
    recommendation: publish ? 'Publish once you have read it.' : 'Mark it passed once you are satisfied with its quality.',
    ifApprove: publish ? 'The brief is published and the publish notification is sent. This cannot be undone.' : 'The brief moves to QA passed and then awaits publishing.',
    ifDefer: publish ? 'The brief stays unpublished and no notification is sent.' : 'The brief stays in review.',
    need: publish ? 'Required. Publishing is an executive approval only you can give.' : 'Required. QA sign-off is a governed step.',
    undoable: false, rank: publish ? 100 : 80, routine: false, legacyHref: `/intelligence-workbench/brief/${encodeURIComponent(b.brief_id)}`,
    ref: { kind: 'brief', briefId: b.brief_id, status } satisfies BriefRef,
  };
}

export function docDecision(d: DocRow): HqDecision {
  return {
    id: `doc:${d.id}`, source: 'knowledge', sourceLabel: 'Knowledge review', title: `Add “${d.filename}” to the library`,
    request: 'Approve a reviewed summary of this document for the library.',
    why: d.summary ?? 'No summary was recorded.',
    recommendation: d.memory_recommendation ? `System recommendation: ${d.memory_recommendation}.` : 'Approve the summary if it is accurate. Full text stays in review.',
    ifApprove: 'The summary becomes searchable in the library. This cannot be undone here.',
    ifDefer: 'The document stays out of search results.',
    need: `Required. Nothing enters the library until you approve it.${d.sensitivity ? ` Sensitivity: ${d.sensitivity}.` : ''}`,
    undoable: false, rank: 30, routine: false, legacyHref: '/knowledge-workbench', ref: { kind: 'doc', docId: d.id } satisfies DocRef,
  };
}

export function improvementDecision(o: OppRow): HqDecision {
  const mayApproveHere = !MISSION_ONLY.has(o.change_class);
  return {
    id: `improvement:${o.opportunity_id}`, source: 'improvement', sourceLabel: 'Improvement', title: o.title,
    request: 'Approve this proposed improvement.', why: o.why_relevant || o.summary,
    recommendation: mayApproveHere ? 'Approve if the benefit is worth the effort.' : 'This needs a mission. Open it in Improvements to continue.',
    ifApprove: 'The improvement is approved and queued for implementation.',
    ifDefer: 'It stays proposed and will be offered again.',
    need: `Your call. A judgement about priorities.${o.value ? ` Estimated value: ${o.value}.` : ''}`,
    undoable: false, rank: 40, routine: false, legacyHref: '/self-improvement-findings',
    ref: { kind: 'improvement', opportunityId: o.opportunity_id, mayApproveHere } satisfies ImprovementRef,
  };
}

export async function loadBriefDecisions(): Promise<HqDecision[] | null> {
  const r = await getJson<{ briefs: BriefRow[] }>('/api/briefs');
  if (!r.ok) return null;
  return r.data.briefs.map(briefDecision).filter((d): d is HqDecision => d !== null);
}
export async function loadDocDecisions(): Promise<HqDecision[] | null> {
  const r = await getJson<{ documents: DocRow[] }>('/api/knowledge-library/documents?status=awaiting_review&review_decision=none&limit=10');
  return r.ok ? r.data.documents.map(docDecision) : null;
}
/** Owner-gated: a 403 means "not available to you", returned as an empty list, not an error. */
export async function loadImprovementDecisions(): Promise<HqDecision[] | null> {
  const r = await getJson<{ opportunities: OppRow[] }>('/api/self-improvement/opportunities?state=proposed');
  if (!r.ok) return r.status === 403 || r.status === 401 ? [] : null;
  return r.data.opportunities.map(improvementDecision);
}

type Post = { ok: boolean; status: number; body: Record<string, unknown> };
async function postJson(url: string, body: unknown): Promise<Post> {
  try {
    const resp = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    let parsed: Record<string, unknown> = {};
    try { parsed = await resp.json(); } catch { /* non-JSON body */ }
    return { ok: resp.ok, status: resp.status, body: parsed };
  } catch (e) {
    return { ok: false, status: 0, body: { error: e instanceof Error ? e.message : 'Network error' } };
  }
}
const errOf = (p: Post) => String(p.body.error ?? p.body.detail ?? `HTTP ${p.status}`);

export type SourceResult = { ok: boolean; error?: string; alreadyDecided?: boolean };

/** Brief gate. Re-reads the brief's status first: publishing an already
 *  published brief is a silent no-op upstream that re-fires the publish
 *  notification, so HQ never sends publish unless the brief is still QA_PASSED. */
export async function actOnBrief(ref: BriefRef): Promise<SourceResult> {
  const cur = await getJson<{ brief: { approval_status: string | null } | null }>(`/api/briefs/${encodeURIComponent(ref.briefId)}`);
  if (!cur.ok) return { ok: false, error: 'Could not confirm the brief status. Nothing was changed.' };
  const status = cur.data.brief?.approval_status ?? null;
  if (status !== ref.status) return { ok: false, alreadyDecided: true, error: 'This brief changed elsewhere. Nothing was changed.' };
  const action = ref.status === 'QA_PASSED' ? 'brief.publish' : 'brief.qa_pass';
  const res = await postJson('/api/intelligence-workbench/action', { action, payload: { brief_id: ref.briefId } });
  return res.ok ? { ok: true } : { ok: false, error: errOf(res) };
}

/** Knowledge review. The route itself returns 409 once decided, so a second
 *  decision from any interface is rejected server-side. */
export async function actOnDoc(ref: DocRef, decision: 'approved_summary' | 'rejected'): Promise<SourceResult> {
  const res = await postJson(`/api/knowledge-library/documents/${encodeURIComponent(ref.docId)}/decide`, { decision });
  if (res.ok) return { ok: true };
  return { ok: false, alreadyDecided: res.status === 409, error: errOf(res) };
}

/** Improvements. The upstream has no state guard, so HQ re-checks that the
 *  opportunity is still proposed immediately before deciding. */
export async function actOnImprovement(ref: ImprovementRef, decision: 'approve_improvement' | 'reject'): Promise<SourceResult> {
  if (decision === 'approve_improvement' && !ref.mayApproveHere) {
    return { ok: false, error: 'This improvement needs a mission. Open it in Improvements.' };
  }
  const cur = await getJson<{ opportunities: OppRow[] }>('/api/self-improvement/opportunities?state=proposed');
  if (!cur.ok) return { ok: false, error: 'Could not confirm the current state. Nothing was changed.' };
  if (!cur.data.opportunities.some((o) => o.opportunity_id === ref.opportunityId)) {
    return { ok: false, alreadyDecided: true, error: 'Already decided elsewhere. Nothing was changed.' };
  }
  const res = await postJson('/api/self-improvement/opportunities/decide', { opportunity_id: ref.opportunityId, decision_type: decision });
  return res.ok ? { ok: true } : { ok: false, error: errOf(res) };
}
