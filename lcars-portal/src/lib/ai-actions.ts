import { createClient } from '@supabase/supabase-js';

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
  const missionId = (payload.mission_id as string) ?? `MSN-AI-${Date.now()}`;
  const row = {
    mission_id: missionId,
    title: payload.title ?? 'Untitled mission',
    priority: payload.priority ?? 'P2',
    status: payload.status ?? 'Idea',
    description: payload.description ?? null,
    task_type: payload.task_type ?? null,
    mission_type: payload.mission_type ?? null,
    created_by: 'lcars-ai-console',
    created_at: new Date().toISOString(),
  };

  const { error } = await supabaseAdmin().from('missions').insert(row);
  if (error) return { type: 'create_mission', success: false, detail: error.message };
  return { type: 'create_mission', success: true, detail: `Mission ${missionId} registered`, id: missionId };
}

async function createHandoff(payload: ActionPayload): Promise<ActionResult> {
  const missionId = (payload.mission_id as string) ?? null;
  const title = (payload.title as string) ?? 'Untitled Handoff';
  const summary = [payload.description, payload.notes].filter(Boolean).join('\n\n') || null;

  const row = {
    title,
    summary,
    status: 'approved',
    metadata: {
      priority: payload.priority ?? 'P1',
      mission_id: missionId,
      source: 'lcars-ai-console',
    },
  };

  const { data, error } = await supabaseAdmin().from('build_request_inbox').insert(row).select('request_id').single();
  if (error) return { type: 'create_handoff', success: false, detail: error.message };
  return { type: 'create_handoff', success: true, detail: `Handoff queued: ${title}`, id: data?.request_id };
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
