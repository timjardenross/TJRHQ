import { createClient } from '@supabase/supabase-js';
import { writeFileSync } from 'fs';
import { join } from 'path';

export interface ActionResult {
  type: string;
  success: boolean;
  detail: string;
  id?: string;
}

type ActionPayload = Record<string, unknown>;

function supabaseAdmin() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) throw new Error('SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set');
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
  const repoRoot = process.env.REPO_ROOT ?? '/opt/starship-endeavour';
  const handoffsDir = join(repoRoot, 'Missions', 'Engineering-Handoffs');
  const ts = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 15).replace(/(\d{8})(\d{6})/, '$1-$2');
  const slug = ((payload.title as string) ?? 'handoff').toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 50);
  const filename = `ENG-HANDOFF-${ts}-${slug}.md`;
  const missionId = (payload.mission_id as string) ?? 'UNKNOWN';

  const content = [
    `# Engineering Handoff`,
    ``,
    `- Status: PENDING_TRIAGE`,
    `- Batch Status: PENDING`,
    `- Priority: ${payload.priority ?? 'P1'}`,
    `- Mission ID: ${missionId}`,
    `- System Actor: LCARS AI Console`,
    `- Policy Decision: APPROVED_FOR_ENGINEERING`,
    `- Source: LCARS portal AI console ${new Date().toISOString().slice(0, 10)}`,
    ``,
    `## Mission Title`,
    ``,
    `${payload.title ?? 'Untitled Handoff'}`,
    ``,
    `## Description`,
    ``,
    `${payload.description ?? ''}`,
    ``,
    `## Implementation Notes`,
    ``,
    `${payload.notes ?? ''}`,
  ].join('\n');

  try {
    writeFileSync(join(handoffsDir, filename), content, 'utf-8');
    return { type: 'create_handoff', success: true, detail: `Handoff written: ${filename}`, id: filename };
  } catch (err) {
    return { type: 'create_handoff', success: false, detail: String(err) };
  }
}

async function logDecision(payload: ActionPayload): Promise<ActionResult> {
  const decisionId = `DEC-AI-${Date.now()}`;
  const row = {
    id: decisionId,
    statement: payload.decision ?? payload.statement ?? 'Decision recorded via AI console',
    rationale: payload.rationale ?? null,
    created_by: 'lcars-ai-console',
    created_at: new Date().toISOString(),
    owner: 'lcars-ai-console',
    status: 'Active',
    alternatives: null,
  };

  const { error } = await supabaseAdmin().from('commander_decisions').insert(row);
  if (error) return { type: 'log_decision', success: false, detail: error.message };
  return { type: 'log_decision', success: true, detail: `Decision ${decisionId} logged`, id: decisionId };
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
