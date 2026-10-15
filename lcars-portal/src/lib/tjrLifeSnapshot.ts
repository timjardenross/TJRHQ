// TJR Life snapshot, contract v1 (R3 S3). Read-only, three independent
// sections built with the Captain's user-scoped Supabase client (RLS applies
// as the Captain; never the service role). Contract: docs/r3-planning/
// TJR_LIFE_SNAPSHOT_V1_CONTRACT.md. Shared fixtures: fixtures/tjr-life-snapshot-v1/.
//
// Safety rules enforced here:
//  - Each section is try/caught on its own. A failing (or hung) section is
//    exactly {"error":"unavailable"}: no message, no code, no partial data.
//  - Selects name their columns. Never selected, so never possible to leak:
//    health_snapshot, raw_text, latitude/longitude, canonical_url, source
//    notes, created_by, audit rows, mission lists, OSINT rows, job
//    lastAction text, source error_message.
//  - Free text from feeds/briefs is reduced to plain text on the server
//    (tags stripped first, then entities decoded; see lib/briefText.ts).
import type { SupabaseClient } from '@supabase/supabase-js';
import { buildAgentStatusOverview } from '@/lib/agentStatusOverview';
import { parseBriefText } from '@/lib/briefText';

export const SNAPSHOT_CONTRACT_VERSION = '1.0';
export const SNAPSHOT_ALERT_LIMIT = 20;
export const SNAPSHOT_SECTION_TIMEOUT_MS = 8000;
const MAX_BRIEF_LINES = 200;
const MAX_LINE_CHARS = 1000;
const MAX_HEADLINE_CHARS = 300;
const MAX_SUMMARY_CHARS = 500;

export type SectionUnavailable = { error: 'unavailable' };
export type HqState = 'ok' | 'degraded' | 'attention' | 'unknown';

export interface HqStatusSection {
  generated_at: string;
  summary: string;
  state: HqState;
  error: null;
}
export interface LatestBriefSection {
  generated_at: string | null;
  brief_date: string | null;
  lines: string[];
  error: null;
}
export interface AlertItem {
  id: string;
  headline: string;
  severity: string;
  occurred_at: string;
}
export interface AlertsSection {
  generated_at: string;
  items: AlertItem[];
  error: null;
}
export interface TjrLifeSnapshot {
  contract_version: string;
  generated_at: string;
  hq_status: HqStatusSection | SectionUnavailable;
  latest_brief: LatestBriefSection | SectionUnavailable;
  alerts: AlertsSection | SectionUnavailable;
}

const UNAVAILABLE: SectionUnavailable = { error: 'unavailable' };

/** Strip tags first, then decode the three entities, then collapse control
 *  characters and whitespace. Same order as lib/briefText.ts and for the same
 *  reason: decoding first would turn an escaped "&lt;x&gt;" into a tag that
 *  the stripper then deletes. */
export function toPlainText(raw: unknown, maxChars: number): string {
  if (typeof raw !== 'string') return '';
  const stripped = raw.replace(/<[^>]*>/g, '');
  const decoded = stripped.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
  return tidy(decoded, maxChars);
}

/** Control characters and whitespace only. For text that has ALREADY been
 *  stripped and decoded (brief lines): running the tag stripper again would
 *  delete decoded text such as "<NRP>". */
export function tidy(text: string, maxChars: number): string {
  // eslint-disable-next-line no-control-regex
  const clean = text.replace(/[\u0000-\u001f\u007f]+/g, ' ').replace(/\s+/g, ' ').trim();
  return clean.length > maxChars ? `${clean.slice(0, maxChars - 1)}…` : clean;
}

function toIso(value: unknown): string | null {
  if (typeof value !== 'string' && !(value instanceof Date)) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

function withTimeout<T>(work: Promise<T>, ms: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout>;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error('section timeout')), ms);
  });
  return Promise.race([work, timeout]).finally(() => clearTimeout(timer));
}

const HQ_STATE: Record<string, HqState> = {
  NORMAL: 'ok',
  DEGRADED: 'degraded',
  ATTENTION: 'attention',
  UNKNOWN: 'unknown',
};

export async function buildHqStatusSection(sb: SupabaseClient): Promise<HqStatusSection> {
  const overview = await buildAgentStatusOverview(sb);
  const summary = overview.captainSummary;
  return {
    generated_at: toIso(summary.last_updated) ?? new Date().toISOString(),
    summary: toPlainText(summary.summary, MAX_SUMMARY_CHARS),
    state: HQ_STATE[summary.hq_posture] ?? 'unknown',
    error: null,
  };
}

export async function buildLatestBriefSection(sb: SupabaseClient): Promise<LatestBriefSection> {
  const { data, error } = await sb
    .from('captains_daily_briefs')
    .select('brief_date, generated_at, brief_text')
    .order('generated_at', { ascending: false })
    .limit(1);
  if (error) throw error;
  const row = data?.[0];
  if (!row) {
    return { generated_at: null, brief_date: null, lines: [], error: null };
  }
  const lines: string[] = [];
  for (const line of parseBriefText(typeof row.brief_text === 'string' ? row.brief_text : '')) {
    if (line.type === 'blank') {
      // One empty string marks a paragraph break; never lead with one or repeat it.
      if (lines.length > 0 && lines[lines.length - 1] !== '') lines.push('');
      continue;
    }
    lines.push(tidy(line.text, MAX_LINE_CHARS));
  }
  while (lines.length > 0 && lines[lines.length - 1] === '') lines.pop();
  return {
    generated_at: toIso(row.generated_at),
    brief_date: typeof row.brief_date === 'string' ? row.brief_date.slice(0, 10) : null,
    lines: lines.slice(0, MAX_BRIEF_LINES),
    error: null,
  };
}

export async function buildAlertsSection(sb: SupabaseClient, now: Date): Promise<AlertsSection> {
  const { data, error } = await sb
    .from('alerts')
    .select('id, headline, severity, issued_at, first_seen_at')
    .eq('is_active', true)
    .or(`expiry.is.null,expiry.gt.${now.toISOString()}`)
    .order('issued_at', { ascending: false, nullsFirst: false })
    .limit(SNAPSHOT_ALERT_LIMIT);
  if (error) throw error;
  const items: AlertItem[] = [];
  for (const row of data ?? []) {
    const occurredAt = toIso(row.issued_at) ?? toIso(row.first_seen_at);
    if (!occurredAt || typeof row.id !== 'string') continue;
    items.push({
      id: row.id,
      headline: toPlainText(row.headline, MAX_HEADLINE_CHARS),
      severity: toPlainText(row.severity, 40).toLowerCase() || 'unknown',
      occurred_at: occurredAt,
    });
  }
  return { generated_at: now.toISOString(), items, error: null };
}

async function guarded<T>(section: string, work: () => Promise<T>): Promise<T | SectionUnavailable> {
  try {
    return await withTimeout(work(), SNAPSHOT_SECTION_TIMEOUT_MS);
  } catch (err) {
    // Section name and error class only: never the message, which can embed
    // request details, and never anything derived from the token.
    console.error('[tjr-life-snapshot] section unavailable', section, err instanceof Error ? err.name : 'unknown');
    return UNAVAILABLE;
  }
}

export async function buildTjrLifeSnapshot(
  sb: SupabaseClient,
  now: Date = new Date(),
): Promise<TjrLifeSnapshot> {
  const [hq_status, latest_brief, alerts] = await Promise.all([
    guarded('hq_status', () => buildHqStatusSection(sb)),
    guarded('latest_brief', () => buildLatestBriefSection(sb)),
    guarded('alerts', () => buildAlertsSection(sb, now)),
  ]);
  return {
    contract_version: SNAPSHOT_CONTRACT_VERSION,
    generated_at: now.toISOString(),
    hq_status,
    latest_brief,
    alerts,
  };
}
