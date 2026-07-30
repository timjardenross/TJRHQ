/**
 * ai-context.ts — server-side Supabase context fetcher for the AI Console.
 *
 * Builds a structured context block injected into every GLM system prompt,
 * giving the model awareness of the current ship state without the Captain
 * having to paste anything.
 *
 * Uses the service role key when available (full access), falls back to
 * the anon key. Runs server-side only — never called from the browser.
 */

import { createClient } from '@supabase/supabase-js';
import { filterGeneralAccess } from '@/lib/knowledgeSensitivity';

function getSupabase() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  // Prefer service role key for full read access; fall back to anon key
  const key =
    process.env.SUPABASE_SERVICE_ROLE_KEY ??
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !key) return null;
  return createClient(url, key);
}

// ── Individual fetchers ───────────────────────────────────────────────────────

async function fetchActiveMissions(db: any) {
  const { data } = await db
    .from('missions')
    .select('mission_id, title, status, priority')
    .not('status', 'in', '("Closed","Archived","COMPLETE","DEFERRED","CANCELLED")')
    .order('priority', { ascending: true })
    .limit(20);
  return data ?? [];
}

async function fetchRecentDecisions(db: any) {
  const { data } = await db
    .from('decisions')
    .select('decision_type, reasoning, outcome, timestamp')
    .order('timestamp', { ascending: false })
    .limit(10);
  return data ?? [];
}

async function fetchArchitectureRecords(db: any) {
  const { data } = await db
    .from('architecture_records')
    .select('title, status, recommended_option')
    .limit(10);
  return data ?? [];
}

function todayBrisbane(): string {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Australia/Brisbane' });
}

async function fetchTodayHealth(db: any) {
  const today = todayBrisbane();
  const { data } = await db
    .from('health_daily_logs')
    .select('log_date, nervous_system_state, energy, mood, sleep_hours, sleep_quality, workload_constraint, daily_capacity_score, pain_score')
    .eq('log_date', today)
    .maybeSingle();
  return data ?? null;
}

async function fetchRecentHealthLog(db: any) {
  const { data } = await db
    .from('health_daily_logs')
    .select('log_date, nervous_system_state, energy, workload_constraint, daily_capacity_score')
    .order('log_date', { ascending: false })
    .limit(7);
  return data ?? [];
}

async function fetchKnowledgeSummary(db: any) {
  const { data } = await db
    .from('knowledge_documents')
    // MSN-0333: metadata selected only to filter on -- never projected
    // into the returned rows below, since this feeds straight into an
    // LLM prompt (the AI Console's system context) and shouldn't carry
    // raw metadata even for standard documents.
    .select('title, document_type, updated_at, metadata')
    .order('updated_at', { ascending: false })
    .limit(15);
  return filterGeneralAccess(data ?? []).map(({ title, document_type, updated_at }: any) => ({
    title, document_type, updated_at,
  }));
}

async function fetchTodayPulses(db: any) {
  const today = todayBrisbane();
  const { data } = await db
    .from('recovery_pulses')
    .select('pulse_type, captured_at, energy, nervous_system, body_signals, readiness, pain_score, notes')
    .eq('log_date', today)
    .order('captured_at', { ascending: true });
  return data ?? [];
}

async function fetchWorkingMemory(db: any) {
  const { data } = await db
    .from('working_memory')
    .select('key, value, updated_at')
    .order('updated_at', { ascending: false })
    .limit(10);
  return data ?? [];
}

async function fetchEngineeringQueue(db: any) {
  const { data } = await db
    .from('build_request_inbox')
    .select('request_id, title, summary, status, created_at')
    .in('status', ['pending_triage', 'approved'])
    .order('created_at', { ascending: false })
    .limit(10);
  return data ?? [];
}

// ── Context block builder ─────────────────────────────────────────────────────

export interface AIContextBlock {
  text: string;
  sources: string[];
  fetchedAt: string;
}

let _cache: AIContextBlock | null = null;
let _cacheAt = 0;
const CACHE_TTL_MS = 60_000;

export async function buildShipContext(): Promise<AIContextBlock> {
  if (_cache && Date.now() - _cacheAt < CACHE_TTL_MS) return _cache;
  const db: any = getSupabase();
  const sources: string[] = [];
  const sections: string[] = [];
  const fetchedAt = new Date().toISOString();

  if (!db) {
    return {
      text: '<!-- No Supabase connection — context unavailable -->',
      sources: [],
      fetchedAt,
    };
  }

  // Run all fetches in parallel
  const [missions, decisions, architecture, todayHealth, recentHealth, todayPulses, knowledge, memory, engQueue] =
    await Promise.all([
      fetchActiveMissions(db).catch(() => []),
      fetchRecentDecisions(db).catch(() => []),
      fetchArchitectureRecords(db).catch(() => []),
      fetchTodayHealth(db).catch(() => null),
      fetchRecentHealthLog(db).catch(() => []),
      fetchTodayPulses(db).catch(() => []),
      fetchKnowledgeSummary(db).catch(() => []),
      fetchWorkingMemory(db).catch(() => []),
      fetchEngineeringQueue(db).catch(() => []),
    ]);

  // ── Recovery posture ───────────────────────────────────────────────────────
  if (todayHealth) {
    sources.push('health_daily_logs (today)');
    sections.push(
      `CAPTAIN RECOVERY STATUS — ${todayHealth.log_date}
Workload constraint: ${todayHealth.workload_constraint ?? 'Unknown'}
Nervous system: ${todayHealth.nervous_system_state ?? '—'}
Energy: ${todayHealth.energy ?? '—'}
Mood: ${todayHealth.mood ?? '—'}
Sleep: ${todayHealth.sleep_hours ? `${todayHealth.sleep_hours}h` : '—'} · ${todayHealth.sleep_quality ?? '—'}
Capacity score: ${todayHealth.daily_capacity_score ?? '—'}
Pain: ${todayHealth.pain_score ?? '—'}`
    );
  } else if (recentHealth.length > 0) {
    const last = recentHealth[0];
    sources.push('health_daily_logs (last known)');
    sections.push(
      `CAPTAIN RECOVERY STATUS — last check-in ${last.log_date}
Constraint: ${last.workload_constraint ?? 'Unknown'} · NS: ${last.nervous_system_state ?? '—'} · Energy: ${last.energy ?? '—'}
(No check-in logged today)`
    );
  }

  // ── Recovery pulses (today) ────────────────────────────────────────────────
  if (todayPulses.length > 0) {
    sources.push('recovery_pulses');
    const pulseLines = (todayPulses as Array<Record<string, string>>).map(
      (p) => `  [${p.pulse_type}] energy: ${p.energy ?? '—'} · NS: ${p.nervous_system ?? '—'}${p.readiness ? ` · readiness: ${p.readiness}` : ''}${p.pain_score ? ` · pain: ${p.pain_score}` : ''}${p.notes ? ` — ${String(p.notes).slice(0, 80)}` : ''}`
    );
    sections.push(`TODAY'S RECOVERY PULSES\n${pulseLines.join('\n')}`);
  }

  // ── Active missions ────────────────────────────────────────────────────────
  if (missions.length > 0) {
    sources.push('missions');
    const missionLines = (missions as Array<Record<string, string>>).map(
      (m) => `  [${m.priority ?? '—'}] ${m.mission_id} — ${m.title} (${m.status})`
    );
    sections.push(`ACTIVE MISSIONS (${missions.length})\n${missionLines.join('\n')}`);
  }

  // ── Engineering queue ──────────────────────────────────────────────────────
  if (engQueue.length > 0) {
    sources.push('build_request_inbox');
    const qLines = (engQueue as Array<Record<string, string>>).map(
      (r) => `  [${r.status}] ${r.request_id} — ${r.title}`
    );
    sections.push(`ENGINEERING QUEUE (${engQueue.length} pending)\n${qLines.join('\n')}`);
  }

  // ── Recent decisions ───────────────────────────────────────────────────────
  if (decisions.length > 0) {
    sources.push('decisions');
    const decLines = (decisions as Array<Record<string, string>>).map(
      (d) => `  ${(d.timestamp ?? '—').slice(0, 10)} · [${d.decision_type ?? '—'}] ${(d.reasoning ?? '').slice(0, 80)} → ${(d.outcome ?? '').slice(0, 60)}`
    );
    sections.push(`RECENT DECISIONS\n${decLines.join('\n')}`);
  }

  // ── Architecture ───────────────────────────────────────────────────────────
  if (architecture.length > 0) {
    sources.push('architecture_records');
    const archLines = (architecture as Array<Record<string, string>>).map(
      (a) => `  ${a.title} (${a.status ?? '—'}) · chosen: ${a.recommended_option ?? '—'}`
    );
    sections.push(`ARCHITECTURE RECORDS\n${archLines.join('\n')}`);
  }

  // ── Knowledge ──────────────────────────────────────────────────────────────
  if (knowledge.length > 0) {
    sources.push('knowledge_documents');
    const knowLines = (knowledge as Array<Record<string, string>>).map(
      (k) => `  [${k.document_type ?? '—'}] ${k.title}`
    );
    sections.push(`KNOWLEDGE BASE (recent)\n${knowLines.join('\n')}`);
  }

  // ── Working memory ─────────────────────────────────────────────────────────
  if (memory.length > 0) {
    sources.push('working_memory');
    const memLines = (memory as Array<Record<string, string>>).map(
      (m) => `  ${m.key}: ${String(m.value).slice(0, 120)}`
    );
    sections.push(`WORKING MEMORY\n${memLines.join('\n')}`);
  }

  if (sections.length === 0) {
    return {
      text: '<!-- Supabase connected but no data returned -->',
      sources: [],
      fetchedAt,
    };
  }

  const text = `
=== STARSHIP ENDEAVOUR — LIVE SHIP CONTEXT (${new Date().toLocaleDateString('en-AU')}) ===
The following is live data from the USS TJR command systems. Use it to answer questions about the current ship state without asking the Captain to provide it manually.

${sections.join('\n\n')}

=== END SHIP CONTEXT ===
`.trim();

  const result = { text, sources, fetchedAt };
  _cache = result;
  _cacheAt = Date.now();
  return result;
}
