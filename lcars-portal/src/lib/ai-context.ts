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
    .select('mission_id, title, status, priority, owner, department')
    .not('status', 'in', '("COMPLETE","DEFERRED","CANCELLED")')
    .order('priority', { ascending: true })
    .limit(20);
  return data ?? [];
}

async function fetchRecentDecisions(db: any) {
  const { data } = await db
    .from('decisions')
    .select('title, status, decision_date, owner')
    .order('decision_date', { ascending: false })
    .limit(10);
  return data ?? [];
}

async function fetchArchitectureRecords(db: any) {
  const { data } = await db
    .from('architecture_records')
    .select('title, status, record_type')
    .limit(10);
  return data ?? [];
}

async function fetchTodayHealth(db: any) {
  const today = new Date().toISOString().slice(0, 10);
  const { data } = await db
    .from('analytics_health_daily')
    .select('log_date, nervous_system_state, energy, mood, sleep_hours, sleep_quality, posture_band, posture_message')
    .eq('log_date', today)
    .maybeSingle();
  return data ?? null;
}

async function fetchRecentHealthLog(db: any) {
  const { data } = await db
    .from('analytics_health_daily')
    .select('log_date, nervous_system_state, energy, posture_band')
    .order('log_date', { ascending: false })
    .limit(7);
  return data ?? [];
}

async function fetchKnowledgeSummary(db: any) {
  const { data } = await db
    .from('knowledge_documents')
    .select('title, category, status')
    .order('updated_at', { ascending: false })
    .limit(15);
  return data ?? [];
}

async function fetchCommandMemory(db: any) {
  const { data } = await db
    .from('command_memory')
    .select('key, value, updated_at')
    .limit(10);
  return data ?? [];
}

// ── Context block builder ─────────────────────────────────────────────────────

export interface AIContextBlock {
  text: string;
  sources: string[];
  fetchedAt: string;
}

export async function buildShipContext(): Promise<AIContextBlock> {
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
  const [missions, decisions, architecture, todayHealth, recentHealth, knowledge, memory] =
    await Promise.all([
      fetchActiveMissions(db).catch(() => []),
      fetchRecentDecisions(db).catch(() => []),
      fetchArchitectureRecords(db).catch(() => []),
      fetchTodayHealth(db).catch(() => null),
      fetchRecentHealthLog(db).catch(() => []),
      fetchKnowledgeSummary(db).catch(() => []),
      fetchCommandMemory(db).catch(() => []),
    ]);

  // ── Recovery posture ───────────────────────────────────────────────────────
  if (todayHealth) {
    sources.push('health_daily_logs (today)');
    sections.push(
      `CAPTAIN RECOVERY STATUS — ${todayHealth.log_date}
Posture: ${todayHealth.posture_band ?? 'Unknown'}
${todayHealth.posture_message ? `Posture note: ${todayHealth.posture_message}` : ''}
Nervous system: ${todayHealth.nervous_system_state ?? '—'}
Energy: ${todayHealth.energy ?? '—'}
Mood: ${todayHealth.mood ?? '—'}
Sleep: ${todayHealth.sleep_hours ? `${todayHealth.sleep_hours}h` : '—'} · ${todayHealth.sleep_quality ?? '—'}`
    );
  } else if (recentHealth.length > 0) {
    const last = recentHealth[0];
    sources.push('health_daily_logs (last known)');
    sections.push(
      `CAPTAIN RECOVERY STATUS — last check-in ${last.log_date}
Posture: ${last.posture_band ?? 'Unknown'} · NS: ${last.nervous_system_state ?? '—'} · Energy: ${last.energy ?? '—'}
(No check-in logged today)`
    );
  }

  // ── Active missions ────────────────────────────────────────────────────────
  if (missions.length > 0) {
    sources.push('missions');
    const missionLines = (missions as Array<Record<string, string>>).map(
      (m) => `  [${m.priority}] ${m.mission_id} — ${m.title} (${m.status}) · ${m.owner}`
    );
    sections.push(`ACTIVE MISSIONS (${missions.length})\n${missionLines.join('\n')}`);
  }

  // ── Recent decisions ───────────────────────────────────────────────────────
  if (decisions.length > 0) {
    sources.push('decisions');
    const decLines = (decisions as Array<Record<string, string>>).map(
      (d) => `  ${d.decision_date ?? '—'} · ${d.title} (${d.status})`
    );
    sections.push(`RECENT DECISIONS\n${decLines.join('\n')}`);
  }

  // ── Architecture ───────────────────────────────────────────────────────────
  if (architecture.length > 0) {
    sources.push('architecture_records');
    const archLines = (architecture as Array<Record<string, string>>).map(
      (a) => `  ${a.record_type ?? 'ADR'} · ${a.title} (${a.status})`
    );
    sections.push(`ARCHITECTURE RECORDS\n${archLines.join('\n')}`);
  }

  // ── Knowledge ──────────────────────────────────────────────────────────────
  if (knowledge.length > 0) {
    sources.push('knowledge_documents');
    const knowLines = (knowledge as Array<Record<string, string>>).map(
      (k) => `  [${k.category ?? '—'}] ${k.title} (${k.status ?? 'active'})`
    );
    sections.push(`KNOWLEDGE BASE (recent)\n${knowLines.join('\n')}`);
  }

  // ── Command memory ─────────────────────────────────────────────────────────
  if (memory.length > 0) {
    sources.push('command_memory');
    const memLines = (memory as Array<Record<string, string>>).map(
      (m) => `  ${m.key}: ${String(m.value).slice(0, 120)}`
    );
    sections.push(`COMMAND MEMORY\n${memLines.join('\n')}`);
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

  return { text, sources, fetchedAt };
}
