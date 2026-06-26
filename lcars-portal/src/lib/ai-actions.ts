import { createClient } from '@supabase/supabase-js';
import { nextId, appendToRegistry } from './id-registry';

export interface ActionResult {
  type: string;
  success: boolean;
  detail: string;
  id?: string;
}

type ActionPayload = Record<string, unknown>;

function supabaseAdmin() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) throw new Error('Supabase URL / service role key not configured');
  return createClient(url, key, { auth: { persistSession: false } });
}

// ── Action handlers ───────────────────────────────────────────────────────────

async function createMission(payload: ActionPayload): Promise<ActionResult> {
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

  return { type: 'create_mission', success: true, detail: `Mission ${missionId} registered`, id: missionId };
}

async function createHandoff(payload: ActionPayload): Promise<ActionResult> {
  const title = (payload.title as string) ?? 'Untitled Handoff';
  const missionId = (payload.mission_id as string) ?? null;
  const ts = new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 15);
  const rand = Math.random().toString(36).slice(2, 8).toUpperCase();
  const requestId = `AI-BREQ-${ts}-${rand}`;

  const row = {
    request_id: requestId,
    title,
    summary: (payload.description as string) ?? null,
    rationale: `Priority: ${payload.priority ?? 'P1'}${missionId ? ` · Mission: ${missionId}` : ''}`,
    suggested_next_step: (payload.notes as string) ?? null,
    status: 'approved',
    source: 'lcars-ai-console',
  };

  const { error } = await supabaseAdmin().from('build_request_inbox').insert(row);
  if (error) return { type: 'create_handoff', success: false, detail: error.message };
  return { type: 'create_handoff', success: true, detail: `Handoff queued: ${title}`, id: requestId };
}

async function logDecision(payload: ActionPayload): Promise<ActionResult> {
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

// ── Parser ────────────────────────────────────────────────────────────────────

export async function parseAndExecuteActions(text: string): Promise<ActionResult[]> {
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

    try {
      let result: ActionResult;
      if (actionType === 'create_mission') result = await createMission(payload);
      else if (actionType === 'create_handoff') result = await createHandoff(payload);
      else if (actionType === 'log_decision') result = await logDecision(payload);
      else result = { type: actionType, success: false, detail: `Unknown action type: ${actionType}` };
      results.push(result);
    } catch (err) {
      results.push({ type: actionType, success: false, detail: String(err) });
    }
  }

  return results;
}
