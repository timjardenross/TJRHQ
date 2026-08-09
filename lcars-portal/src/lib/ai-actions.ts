import { createClient } from '@supabase/supabase-js';
import { nextId, appendToRegistry } from './id-registry';
import { recordHeartbeatServerSide } from './heartbeat';

export interface ActionResult {
  type: string;
  success: boolean;
  detail: string;
  id?: string;
}

type ActionPayload = Record<string, unknown>;

export function supabaseAdmin() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) throw new Error('Supabase URL / service role key not configured');
  return createClient(url, key, { auth: { persistSession: false } });
}

// ── MSN-0352: Conversational Governance Enforcement ────────────────────────
//
// This file used to execute create_mission / create_handoff / log_decision
// the moment an LLM's streamed response contained a correctly-formatted
// <starfleet-action> block - no confirmation, no Captain click-to-approve,
// the only safeguard being the model's own judgement about whether it had
// been "authorised." That is a governance breach: this project's standing
// rule is "human approval mandatory before artefact creation," and the
// whole rest of the platform (Decide's Approve/Hold/Undo model) exists to
// enforce exactly that. A prompt instruction telling the model to behave
// is not equivalent to an enforced gate.
//
// The fix reuses the governance model that already exists rather than
// inventing a second one: parseAndProposeActions() below no longer
// executes anything. It queues a real, ordinary build_request_inbox row
// with status='awaiting_review', carrying enough structured payload
// (action_type / action_payload) to perform the real mutation LATER - but
// only from POST /api/build-request/[id]/approve-action, which is itself
// only reachable by the Captain clicking Approve on this exact item in
// Decide. createMission/createHandoff/logDecision below are the functions
// that route calls on approval, not functions the parser calls directly
// anymore.

/** Executes the real mission insert. Called ONLY from the approve-action
 * route, on explicit Captain approval - never from the chat parser. */
export async function createMission(payload: ActionPayload): Promise<ActionResult> {
  // MSN-0144: mint a canonical USS-TJR-MSN-NNNN ID if the AI did not provide one.
  // Falls back to a timestamp-based MSN ID if the counter file is unavailable.
  let missionId = payload.mission_id as string | undefined;
  if (!missionId) {
    try {
      missionId = await nextId('MSN');
    } catch {
      missionId = `USS-TJR-MSN-${Date.now()}`;
    }
  }

  const title = String(payload.title ?? 'Untitled mission');
  const status = String(payload.status ?? 'Idea');
  const row = {
    mission_id: missionId,
    title,
    priority: payload.priority ?? 'P2',
    status,
    description: payload.description ?? null,
    task_type: payload.task_type ?? null,
    mission_type: payload.mission_type ?? null,
    created_by: 'lcars-ai-console',
    created_at: new Date().toISOString(),
  };

  const { error } = await supabaseAdmin().from('missions').insert(row);
  if (error) return { type: 'create_mission', success: false, detail: error.message };

  // MSN-0145: append runtime entry to the authoritative mission registry.
  appendToRegistry(missionId, title, 'LCARS', status);

  // Chief Engineer follow-up (.claude/skills/bot-reviews/fixes-2026-08-09/
  // final-4-domains.md): this is a genuinely separate live `missions` write
  // path from api/missions/route.ts — Captain-approved AI-console mission
  // creation (MSN-0352 governance gate), reached only from
  // api/build-request/[id]/approve-action/route.ts on explicit approval.
  void recordHeartbeatServerSide({
    domainKey: 'missions',
    status: 'ok',
    detail: `create (ai-console) mission_id=${missionId}`,
  });

  return { type: 'create_mission', success: true, detail: `Mission ${missionId} registered`, id: missionId };
}

/** Executes the real decision insert. Called ONLY from the approve-action
 * route, on explicit Captain approval - never from the chat parser. */
export async function logDecision(payload: ActionPayload): Promise<ActionResult> {
  const row = {
    decision_title: payload.decision ?? payload.title ?? 'Decision recorded via AI console',
    decision_summary: payload.rationale ?? payload.summary ?? null,
    source: 'lcars-ai-console',
    status: 'Active',
    metadata: payload.mission_id ? { mission_id: payload.mission_id } : null,
  };

  const { data, error } = await supabaseAdmin().from('commander_decisions').insert(row).select('id').single();
  if (error) return { type: 'log_decision', success: false, detail: error.message };
  return { type: 'log_decision', success: true, detail: `Decision logged`, id: data?.id };
}

/** create_handoff never needed a separate "execute on approval" step - the
 * queued build_request_inbox row already IS the handoff. Approval in
 * Decide flips its status from awaiting_review to approved (the same
 * mechanism every other build-inbox item already uses); this function
 * exists only to satisfy the approve-action route's uniform interface and
 * always reports success without a second write. */
export async function createHandoff(): Promise<ActionResult> {
  return { type: 'create_handoff', success: true, detail: 'Handoff approved' };
}

/** EOS Phase 2 Priority 5 (Executive Communications Studio): closes the one
 * governance gap the Phase 1 Capability Composition Audit found still open
 * - comms_content's ready_to_publish -> published transition used to be an
 * immediate, ungated update (api/comms/[id]/advance/route.ts). It now
 * routes through this same propose-then-approve path as every other
 * AI/system-proposed mutation (docs/EOS-CANONICAL-ARCHITECTURE-DECISIONS.md
 * §4, "no exceptions"). Called ONLY from the approve-action route, on
 * explicit Captain approval. Guards on status='ready_to_publish' so a
 * stale proposal (the row moved on some other way since it was queued)
 * fails closed instead of silently publishing from an unexpected state. */
export async function publishContent(payload: ActionPayload): Promise<ActionResult> {
  const contentId = String(payload.content_id ?? '');
  const { data, error } = await supabaseAdmin()
    .from('comms_content')
    .update({ status: 'published', updated_at: new Date().toISOString() })
    .eq('id', contentId)
    .eq('status', 'ready_to_publish')
    .select('id')
    .maybeSingle();
  if (error) return { type: 'publish_content', success: false, detail: error.message };
  if (!data) {
    return {
      type: 'publish_content',
      success: false,
      detail: 'Content is no longer in ready_to_publish state - it may have changed since this was proposed',
    };
  }
  return { type: 'publish_content', success: true, detail: `Content ${contentId} published`, id: data.id };
}

const ACTION_TYPES = ['create_mission', 'create_handoff', 'log_decision', 'publish_content'] as const;
export type ProposableActionType = (typeof ACTION_TYPES)[number];

function isProposableActionType(t: string): t is ProposableActionType {
  return (ACTION_TYPES as readonly string[]).includes(t);
}

/** MSN-0352: fail-closed payload validation, run BOTH before a proposal is
 * ever queued (so a malformed action never even reaches Decide) AND again
 * before it executes on approval (so a row that was somehow written with
 * a bad payload still cannot mutate anything). An unknown action_type or
 * a payload missing its required field is always rejected, never
 * defaulted into something plausible-looking. */
export function validateActionPayload(actionType: string, payload: unknown): { ok: true } | { ok: false; error: string } {
  if (!isProposableActionType(actionType)) {
    return { ok: false, error: `Unsupported action type: ${actionType}` };
  }
  if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) {
    return { ok: false, error: 'Action payload must be a JSON object' };
  }
  const p = payload as ActionPayload;
  const nonEmptyString = (v: unknown) => typeof v === 'string' && v.trim().length > 0;

  if (actionType === 'create_mission' && !nonEmptyString(p.title)) {
    return { ok: false, error: 'create_mission requires a non-empty "title"' };
  }
  if (actionType === 'create_handoff' && !nonEmptyString(p.title)) {
    return { ok: false, error: 'create_handoff requires a non-empty "title"' };
  }
  if (actionType === 'log_decision' && !nonEmptyString(p.decision) && !nonEmptyString(p.title)) {
    return { ok: false, error: 'log_decision requires a non-empty "decision" or "title"' };
  }
  if (actionType === 'publish_content' && !nonEmptyString(p.content_id)) {
    return { ok: false, error: 'publish_content requires a non-empty "content_id"' };
  }
  return { ok: true };
}

/** Renders a short, honest, human-readable summary of a proposed action for
 * the Captain to read in Decide - never a claim that anything happened yet. */
function describeProposal(actionType: ProposableActionType, payload: ActionPayload): { title: string; summary: string; rationale: string } {
  switch (actionType) {
    case 'create_mission':
      return {
        title: String(payload.title ?? 'Untitled mission'),
        summary: `Proposed mission: ${String(payload.title ?? 'Untitled mission')}`,
        rationale: String(payload.description ?? payload.rationale ?? ''),
      };
    case 'log_decision':
      return {
        title: String(payload.decision ?? payload.title ?? 'Untitled decision'),
        summary: `Proposed decision log: ${String(payload.decision ?? payload.title ?? 'Untitled decision')}`,
        rationale: String(payload.rationale ?? ''),
      };
    case 'create_handoff':
      return {
        title: String(payload.title ?? 'Untitled handoff'),
        summary: String(payload.description ?? ''),
        rationale: `Priority: ${payload.priority ?? 'P1'}${payload.mission_id ? ` · Mission: ${payload.mission_id}` : ''}`,
      };
    case 'publish_content':
      return {
        title: String(payload.title ?? 'Untitled content'),
        summary: `Proposed publish: ${String(payload.title ?? 'Untitled content')}`,
        rationale: 'Advances this item from Ready to Publish to Published in the Communications pipeline.',
      };
  }
}

/** Queues one proposed action as a real build_request_inbox row awaiting
 * Captain review - never executes it. Returns a result describing the
 * proposal, not a completed action, so the model's own reply can be
 * honest about what actually happened. Exported (EOS Phase 2 Priority 5)
 * so api/comms/[id]/advance/route.ts can queue a publish_content proposal
 * the same governed way parseAndProposeActions queues everything else -
 * one proposal mechanism, not a second one reimplemented per caller. */
export async function proposeAction(actionType: ProposableActionType, payload: ActionPayload): Promise<ActionResult> {
  const { title, summary, rationale } = describeProposal(actionType, payload);
  const ts = new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 15);
  const rand = Math.random().toString(36).slice(2, 8).toUpperCase();
  const requestId = `AI-${actionType.toUpperCase()}-${ts}-${rand}`;

  const row = {
    request_id: requestId,
    title,
    summary: summary || null,
    rationale: rationale || null,
    suggested_next_step: (payload.notes as string) ?? null,
    status: 'awaiting_review',
    source: 'lcars-ai-console-proposed',
    action_type: actionType,
    action_payload: payload,
  };

  const { data, error } = await supabaseAdmin().from('build_request_inbox').insert(row).select('id').single();
  if (error) return { type: actionType, success: false, detail: `Could not queue proposal: ${error.message}` };
  return {
    type: actionType,
    success: true,
    detail: `Proposed for your approval in Decide: "${title}"`,
    id: data?.id,
  };
}

// ── Parser ────────────────────────────────────────────────────────────────────

/** Parses <starfleet-action> blocks from LLM output and queues each as a
 * governed proposal - it never mutates operational state directly. The
 * real mutation only happens if and when the Captain approves the
 * resulting Decide item, via POST /api/build-request/[id]/approve-action. */
export async function parseAndProposeActions(text: string): Promise<ActionResult[]> {
  const pattern = /<starfleet-action\s+type="([^"]+)">([\s\S]*?)<\/starfleet-action>/g;
  const results: ActionResult[] = [];
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    const actionType = match[1];
    let payload: ActionPayload = {};
    try {
      payload = JSON.parse(match[2].trim());
    } catch {
      results.push({ type: actionType, success: false, detail: 'Malformed JSON in action block' });
      continue;
    }

    const validation = validateActionPayload(actionType, payload);
    if (!validation.ok) {
      // Fail closed: an unsupported type or a malformed payload is never
      // queued, never shown to the Captain as something to approve.
      results.push({ type: actionType, success: false, detail: validation.error });
      continue;
    }

    try {
      results.push(await proposeAction(actionType as ProposableActionType, payload));
    } catch (err) {
      results.push({ type: actionType, success: false, detail: String(err) });
    }
  }

  return results;
}
