// TJR Life snapshot, contract v1.1 (R3 S3; v1.1 = richer alerts). Read-only, three independent
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

export const SNAPSHOT_CONTRACT_VERSION = '1.1';
export const SNAPSHOT_ALERT_LIMIT = 20;
export const SNAPSHOT_SECTION_TIMEOUT_MS = 8000;
// Approved allowlist caps (PO, R3 review). Lengths are UTF-16 code units.
export const MAX_BRIEF_LINES = 40;
export const MAX_LINE_CHARS = 500;
export const MAX_HEADLINE_CHARS = 160;
export const MAX_SUMMARY_CHARS = 400;
export const MAX_ALERT_ID_CHARS = 64;
export const MAX_RESPONSE_BYTES = 64 * 1024;
export const MAX_JURISDICTION_CHARS = 8;
export const MAX_SOURCE_NAME_CHARS = 40;
export const ALERT_SEVERITIES = ['emergency_warning', 'watch_and_act', 'advice', 'unknown'] as const;
export type AlertSeverity = (typeof ALERT_SEVERITIES)[number];
export const ALERT_TYPES = [
  'bushfire', 'flood', 'storm', 'cyclone', 'heatwave', 'hazard_reduction',
  'structure_fire', 'severe_weather', 'tsunami', 'other',
] as const;
export type AlertType = (typeof ALERT_TYPES)[number];
export const ALERT_STATUSES = ['new', 'active', 'updated', 'superseded', 'expired', 'inactive', 'errored'] as const;
export type AlertStatus = (typeof ALERT_STATUSES)[number] | 'unknown';

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
  severity: AlertSeverity;
  occurred_at: string;
  // v1.1 additions. jurisdiction, source_name and updated_at are omitted when
  // the stored value is missing or unusable; the others are always present.
  jurisdiction?: string;
  alert_type: AlertType;
  status: AlertStatus;
  expires_at: string | null;
  updated_at?: string;
  source_name?: string;
}
export interface AlertsSection {
  generated_at: string;
  last_polled_at: string | null;
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
  if (clean.length <= maxChars) return clean;
  let cut = clean.slice(0, maxChars - 1);
  // Never end on half of a surrogate pair.
  if (/[\ud800-\udbff]$/.test(cut)) cut = cut.slice(0, -1);
  return `${cut}…`;
}

function toSeverity(raw: unknown): AlertSeverity {
  const value = typeof raw === 'string' ? raw.trim().toLowerCase() : '';
  return (ALERT_SEVERITIES as readonly string[]).includes(value) ? (value as AlertSeverity) : 'unknown';
}

function toEnum<T extends string>(raw: unknown, allowed: readonly T[], fallback: T): T {
  const value = typeof raw === 'string' ? raw.trim().toLowerCase() : '';
  return (allowed as readonly string[]).includes(value) ? (value as T) : fallback;
}

/** Plain text of at most maxChars, or undefined when nothing usable remains. */
function optionalText(raw: unknown, maxChars: number): string | undefined {
  const text = toPlainText(raw, maxChars);
  return text.length > 0 ? text : undefined;
}

// PostgREST returns a many-to-one embed as an object; tolerate a one-element array.
function embeddedSourceName(embed: unknown): unknown {
  const one = Array.isArray(embed) ? embed[0] : embed;
  return one && typeof one === 'object' ? (one as { source_name?: unknown }).source_name : undefined;
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
  lines.length = Math.min(lines.length, MAX_BRIEF_LINES);
  while (lines.length > 0 && lines[lines.length - 1] === '') lines.pop();
  return {
    generated_at: toIso(row.generated_at),
    brief_date: typeof row.brief_date === 'string' ? row.brief_date.slice(0, 10) : null,
    lines,
    error: null,
  };
}

export async function buildAlertsSection(sb: SupabaseClient, now: Date): Promise<AlertsSection> {
  const notExpired = `expiry.is.null,expiry.gt.${now.toISOString()}`;
  const { data, error } = await sb
    .from('alerts')
    .select(
      'id, headline, severity, issued_at, first_seen_at, jurisdiction, alert_type, status, expiry, updated_at_src, last_seen_at, alert_sources(source_name)',
    )
    .eq('is_active', true)
    .or(notExpired)
    .order('issued_at', { ascending: false, nullsFirst: false })
    .limit(SNAPSHOT_ALERT_LIMIT);
  if (error) throw error;
  // Newest last_seen_at over ALL active unexpired alerts (not just the capped
  // page). The source heartbeat is not read.
  const polled = await sb
    .from('alerts')
    .select('last_seen_at')
    .eq('is_active', true)
    .or(notExpired)
    .order('last_seen_at', { ascending: false })
    .limit(1);
  if (polled.error) throw polled.error;
  const items: AlertItem[] = [];
  const seen = new Set<string>();
  for (const row of data ?? []) {
    const occurredAt = toIso(row.issued_at) ?? toIso(row.first_seen_at);
    // An id over the cap is dropped, not truncated (truncation could collide);
    // a repeated id is dropped so ids are unique within a response.
    if (!occurredAt || typeof row.id !== 'string' || row.id.length === 0) continue;
    if (row.id.length > MAX_ALERT_ID_CHARS || seen.has(row.id)) continue;
    seen.add(row.id);
    const item: AlertItem = {
      id: row.id,
      headline: toPlainText(row.headline, MAX_HEADLINE_CHARS),
      severity: toSeverity(row.severity),
      occurred_at: occurredAt,
      alert_type: toEnum(row.alert_type, ALERT_TYPES, 'other'),
      status: toEnum<AlertStatus>(row.status, ALERT_STATUSES, 'unknown'),
      expires_at: toIso(row.expiry),
    };
    const jurisdiction = optionalText(row.jurisdiction, MAX_JURISDICTION_CHARS);
    if (jurisdiction) item.jurisdiction = jurisdiction;
    const updatedAt = toIso(row.updated_at_src) ?? toIso(row.last_seen_at);
    if (updatedAt) item.updated_at = updatedAt;
    const sourceName = optionalText(embeddedSourceName(row.alert_sources), MAX_SOURCE_NAME_CHARS);
    if (sourceName) item.source_name = sourceName;
    items.push(item);
  }
  return {
    generated_at: now.toISOString(),
    last_polled_at: toIso(polled.data?.[0]?.last_seen_at),
    items,
    error: null,
  };
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
  return enforceSizeCap({
    contract_version: SNAPSHOT_CONTRACT_VERSION,
    generated_at: now.toISOString(),
    hq_status,
    latest_brief,
    alerts,
  });
}

function sizeOf(snapshot: TjrLifeSnapshot): number {
  return new TextEncoder().encode(JSON.stringify(snapshot)).length;
}

/** Total response cap. The per-field caps bound the normal case, but 3-byte
 *  characters can still push a full snapshot past 64 KB. Shed content in a
 *  fixed order, newest information last: brief lines from the end, then
 *  alerts from the end, then (cannot happen with the caps, kept as a
 *  guarantee) whole sections. */
export function enforceSizeCap(snapshot: TjrLifeSnapshot): TjrLifeSnapshot {
  const out: TjrLifeSnapshot = { ...snapshot };
  if (sizeOf(out) <= MAX_RESPONSE_BYTES) return out;
  if ('lines' in out.latest_brief) {
    const brief = { ...out.latest_brief, lines: [...out.latest_brief.lines] };
    out.latest_brief = brief;
    while (brief.lines.length > 0 && sizeOf(out) > MAX_RESPONSE_BYTES) {
      brief.lines.pop();
      while (brief.lines.length > 0 && brief.lines[brief.lines.length - 1] === '') brief.lines.pop();
    }
  }
  if ('items' in out.alerts) {
    const alerts = { ...out.alerts, items: [...out.alerts.items] };
    out.alerts = alerts;
    while (alerts.items.length > 0 && sizeOf(out) > MAX_RESPONSE_BYTES) alerts.items.pop();
  }
  if (sizeOf(out) > MAX_RESPONSE_BYTES) {
    out.latest_brief = UNAVAILABLE;
    out.alerts = UNAVAILABLE;
    out.hq_status = UNAVAILABLE;
  }
  return out;
}
