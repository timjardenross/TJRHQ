// HQ read-side adapters. Each loader calls an EXISTING API and projects the
// response onto an HQ view model. Nothing here stores or copies data, and a
// source that fails is reported by name rather than hidden.
import { normaliseEvidence, normaliseRisk } from './vocab';
import type { HqIntelItem, HqLibraryItem, HqWorkItem, HqWorkState } from './model';

type Fetched<T> = { ok: true; data: T } | { ok: false; status: number; error: string };

export async function getJson<T>(url: string): Promise<Fetched<T>> {
  try {
    const resp = await fetch(url, { headers: { Accept: 'application/json' } });
    if (!resp.ok) return { ok: false, status: resp.status, error: `HTTP ${resp.status}` };
    return { ok: true, data: (await resp.json()) as T };
  } catch (e) {
    return { ok: false, status: 0, error: e instanceof Error ? e.message : 'Network error' };
  }
}

export interface Loaded<T> { items: T[]; unavailable: string[] }

// ── Intelligence ────────────────────────────────────────────────────────────

interface TodayDev {
  event_id: string; title: string; canonical_url: string | null; what_happened: string;
  why_you_care: string; assessment: string; you_need_to: string; confidence_level: string;
  corroboration: number; published_at: string | null;
}
interface WatchItem {
  event_id: string; title: string; canonical_url: string | null; why_watched: string;
  confidence_level: string; significance: string; corroboration: number; last_update: string | null;
}
interface EmergencyAlert {
  id: string; headline: string; description: string | null; severity: string; location: string | null;
  jurisdiction: string; issuedAt: string | null; canonicalUrl: string | null; sourceKey: string;
}
interface HealthItem {
  signal_id: string; title: string; summary: string | null; source_url: string | null; source_name: string;
  topic_label: string; confidence_level: string; collected_at: string | null; safety_relevance: boolean;
  actionable_recommendation?: string | null;
}

export function mapTodayItem(d: TodayDev, needsYou: boolean): HqIntelItem {
  return {
    id: `tech:${d.event_id}`, kind: 'Signal', lens: 'Technical', title: d.title,
    summary: d.what_happened, why: d.why_you_care || null, youNeedTo: d.you_need_to || null,
    risk: null, evidence: normaliseEvidence(d.confidence_level), corroboration: d.corroboration ?? null,
    needsYou, watching: false, when: d.published_at, url: d.canonical_url, sourceName: null,
    legacyHref: '/intelligence-workbench',
  };
}

export function mapWatchItem(w: WatchItem): HqIntelItem {
  return {
    id: `tech:${w.event_id}`, kind: 'Watching', lens: 'Technical', title: w.title,
    summary: w.why_watched, why: null, youNeedTo: null,
    risk: normaliseRisk(w.significance), evidence: normaliseEvidence(w.confidence_level),
    corroboration: w.corroboration ?? null, needsYou: false, watching: true, when: w.last_update,
    url: w.canonical_url, sourceName: null, legacyHref: '/intelligence-workbench',
  };
}

export function mapAlert(a: EmergencyAlert): HqIntelItem {
  const risk = normaliseRisk(a.severity);
  return {
    id: `alert:${a.id}`, kind: 'Official alert', lens: 'Alerts', title: a.headline,
    summary: [a.location, a.description].filter(Boolean).join('. ').slice(0, 280) || a.jurisdiction,
    why: null, youNeedTo: risk === 'High' ? 'Follow the official advice.' : null,
    risk, evidence: 'Strong', corroboration: null,
    // Only the highest tier interrupts. Advice-level stays out of attention.
    needsYou: a.severity === 'emergency_warning', watching: a.severity !== 'emergency_warning',
    when: a.issuedAt, url: a.canonicalUrl, sourceName: a.sourceKey, legacyHref: '/emergency-alert-hub-workbench',
  };
}

export function mapHealthItem(h: HealthItem): HqIntelItem {
  return {
    id: `health:${h.signal_id}`, kind: h.safety_relevance ? 'Safety' : 'Research', lens: 'Health', title: h.title,
    summary: h.summary ?? h.topic_label, why: h.topic_label, youNeedTo: h.actionable_recommendation ?? null,
    risk: h.safety_relevance ? 'Medium' : null, evidence: normaliseEvidence(h.confidence_level), corroboration: null,
    needsYou: h.safety_relevance, watching: false, when: h.collected_at, url: h.source_url,
    sourceName: h.source_name, legacyHref: '/health-osint',
  };
}

export async function loadIntel(): Promise<Loaded<HqIntelItem>> {
  const [today, watching, alerts, health] = await Promise.all([
    getJson<{ needs_you: TodayDev[]; worth_knowing: TodayDev[] }>('/api/intelligence-workbench/today'),
    getJson<{ items: WatchItem[] }>('/api/intelligence-workbench/watching'),
    getJson<{ alerts: EmergencyAlert[] }>('/api/emergency-alerts?activeOnly=true'),
    getJson<{ worth_knowing: HealthItem[]; safety: { items: HealthItem[] } }>('/api/health-osint/today'),
  ]);
  const items: HqIntelItem[] = [];
  const unavailable: string[] = [];
  if (today.ok) {
    items.push(...(today.data.needs_you ?? []).map((d) => mapTodayItem(d, true)));
    items.push(...(today.data.worth_knowing ?? []).map((d) => mapTodayItem(d, false)));
  } else unavailable.push('Technical signals');
  if (watching.ok) items.push(...(watching.data.items ?? []).map(mapWatchItem)); else unavailable.push('Watching');
  if (alerts.ok) items.push(...(alerts.data.alerts ?? []).map(mapAlert)); else unavailable.push('Official alerts');
  if (health.ok) {
    const seen = new Set<string>();
    for (const h of [...(health.data.safety?.items ?? []), ...(health.data.worth_knowing ?? [])]) {
      if (seen.has(h.signal_id)) continue;
      seen.add(h.signal_id);
      items.push(mapHealthItem(h));
    }
  } else unavailable.push('Health evidence');
  return { items, unavailable };
}

// ── Work ────────────────────────────────────────────────────────────────────

interface MissionRow { mission_id: string; title: string; status: string; priority: string | null; created_at: string; updated_at: string | null }
interface Handoff {
  mission_id: string; title: string; handoff_queue?: string; next_action?: string; last_updated?: string;
  metadata?: { engineering_status?: string; pr_url?: string; batch_artifact?: string };
}

const REVIEW_STATES = new Set(['Awaiting Number One Review', 'Awaiting XO Approval', 'Awaiting Captain Approval', 'Validated', 'Idea']);
const ATTENTION_STATES = new Set(['Blocked', 'Requires Rework']);
const DONE_STATES = new Set(['Closed', 'Archived']);

export function missionState(status: string): HqWorkState {
  if (ATTENTION_STATES.has(status)) return 'attention';
  if (DONE_STATES.has(status)) return 'done';
  if (REVIEW_STATES.has(status)) return 'review';
  return 'progress';
}

export function mapMission(m: MissionRow): HqWorkItem {
  const state = missionState(m.status);
  const line =
    m.status === 'Idea' ? 'Mission candidate. Waiting for your review.'
    : state === 'review' ? `${m.status}. Waiting for review.`
    : state === 'attention' ? `${m.status}. Needs attention.`
    : state === 'done' ? `${m.status}.`
    : `${m.status}${m.priority ? ` · ${m.priority}` : ''}.`;
  return {
    id: `mission:${m.mission_id}`, title: m.title, state, line, outputs: [],
    legacyHref: `/mission-workbench/${encodeURIComponent(m.mission_id)}`, updatedAt: m.updated_at ?? m.created_at,
  };
}

export function mapHandoff(h: Handoff): HqWorkItem {
  const es = h.metadata?.engineering_status ?? '';
  const state: HqWorkState =
    es === 'Awaiting Review' ? 'review' : es === 'Pending Triage' ? 'attention' : es === 'Completed' ? 'done' : 'progress';
  const outputs = [h.metadata?.pr_url, h.metadata?.batch_artifact].filter((x): x is string => Boolean(x));
  return {
    id: `handoff:${h.mission_id}`, title: h.title, state,
    line: h.next_action ? `${es || 'Engineering'}. ${h.next_action}` : `${es || 'Engineering'}.`,
    outputs, legacyHref: '/decisions?tab=handoffs', updatedAt: h.last_updated ?? null,
  };
}

export async function loadWork(): Promise<Loaded<HqWorkItem>> {
  const [active, closed, handoffs] = await Promise.all([
    getJson<{ missions: MissionRow[] }>('/api/missions?limit=100'),
    getJson<{ missions: MissionRow[] }>('/api/missions?status=Closed&limit=10'),
    getJson<{ handoffs: Handoff[] }>('/api/engineering-handoffs?include_completed=false'),
  ]);
  const items: HqWorkItem[] = [];
  const unavailable: string[] = [];
  if (active.ok) items.push(...active.data.missions.map(mapMission)); else unavailable.push('Missions');
  if (closed.ok) {
    const weekAgo = Date.now() - 7 * 86_400_000;
    items.push(...closed.data.missions
      .filter((m) => new Date(m.updated_at ?? m.created_at).getTime() >= weekAgo)
      .map(mapMission));
  }
  // Engineering handoffs are owner-gated (403 for anyone else): treat that as
  // "not available to you", not as an error worth showing.
  if (handoffs.ok) items.push(...handoffs.data.handoffs.map(mapHandoff));
  else if (handoffs.status !== 403) unavailable.push('Engineering handoffs');
  // The same record must never appear twice in one list.
  const seen = new Set<string>();
  const unique = items.filter((w) => (seen.has(w.id) ? false : (seen.add(w.id), true)));
  return { items: unique, unavailable };
}

// ── Library ─────────────────────────────────────────────────────────────────

interface KDoc { id: string; filename: string; summary: string | null; source_name: string | null; category: string | null; created_at: string | null; status: string }
interface KMem { id: string; title: string; document_type: string | null; category: string | null; created_at: string | null }
interface SigL { event_id: string; title: string; canonical_url: string | null; sector: string | null; published_at: string | null; brief_id: string | null }
interface BriefL { brief_id: string; generated_at: string; executive_snapshot: string | null; bottom_line?: string | null; overall_risk: string | null }
interface ContentL { id: string; title: string; notes: string | null; status: string; updated_at: string | null }

function storeLabel(source: string | null | undefined, fallback: string): string {
  return source && /notion/i.test(source) ? 'Notion' : fallback;
}

export const mapKnowledgeDoc = (d: KDoc): HqLibraryItem => ({
  id: `kdoc:${d.id}`, title: d.filename, type: 'Document', store: storeLabel(d.source_name, 'Knowledge library'),
  date: d.created_at, excerpt: d.summary ?? `${d.category ?? 'Document'} (${d.status.replace(/_/g, ' ')})`,
  legacyHref: '/knowledge-workbench',
});
export const mapKnowledgeMemory = (d: KMem): HqLibraryItem => ({
  id: `kmem:${d.id}`, title: d.title, type: 'Knowledge', store: 'Command memory', date: d.created_at,
  excerpt: [d.document_type, d.category].filter(Boolean).join(' · ') || 'Command memory entry', legacyHref: '/knowledge-workbench',
});
export const mapSignal = (s: SigL): HqLibraryItem => ({
  id: `sig:${s.event_id}`, title: s.title, type: 'Intelligence', store: 'Intelligence archive', date: s.published_at,
  excerpt: s.sector ?? 'Intelligence signal', legacyHref: s.canonical_url ?? '/intelligence-workbench',
});
export const mapBrief = (b: BriefL): HqLibraryItem => ({
  id: `brief:${b.brief_id}`, title: `Brief ${b.brief_id}`, type: 'Brief', store: 'Brief archive', date: b.generated_at,
  excerpt: b.bottom_line ?? b.executive_snapshot ?? 'Brief', legacyHref: `/briefs/${encodeURIComponent(b.brief_id)}`,
});
export const mapContent = (c: ContentL): HqLibraryItem => ({
  id: `content:${c.id}`, title: c.title, type: 'Content', store: 'Content pipeline', date: c.updated_at,
  excerpt: c.notes ?? c.status.replace(/_/g, ' '), legacyHref: '/content-workbench',
});

export function matchesQuery(text: string, q: string): boolean {
  const words = q.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  const hay = text.toLowerCase();
  return words.every((w) => hay.includes(w));
}

/** Federated search: asks each existing source in turn-free parallel and
 *  merges. No index and no copy: a source that fails is named, not hidden. */
export async function searchLibrary(q: string): Promise<Loaded<HqLibraryItem>> {
  const term = q.trim();
  const enc = encodeURIComponent(term);
  const [docs, mem, sig, briefs, content] = await Promise.all([
    getJson<{ documents: KDoc[] }>(`/api/knowledge-library/documents?limit=15${term ? `&search=${enc}` : ''}`),
    getJson<{ documents: KMem[] }>(`/api/knowledge-library/memory?limit=15${term ? `&search=${enc}` : ''}`),
    getJson<{ items: SigL[] }>(`/api/intelligence-workbench/library${term ? `?q=${enc}` : ''}`),
    getJson<{ briefs: BriefL[] }>('/api/briefs'),
    getJson<{ items: ContentL[] }>('/api/content-workbench'),
  ]);
  const items: HqLibraryItem[] = [];
  const unavailable: string[] = [];
  if (docs.ok) items.push(...docs.data.documents.map(mapKnowledgeDoc)); else unavailable.push('Knowledge documents');
  if (mem.ok) items.push(...mem.data.documents.map(mapKnowledgeMemory)); else unavailable.push('Command memory');
  if (sig.ok) items.push(...sig.data.items.slice(0, 15).map(mapSignal)); else unavailable.push('Intelligence archive');
  if (briefs.ok) items.push(...briefs.data.briefs.map(mapBrief).filter((b) => matchesQuery(`${b.title} ${b.excerpt}`, term)).slice(0, 10));
  else unavailable.push('Briefs');
  if (content.ok) items.push(...content.data.items.map(mapContent).filter((c) => matchesQuery(`${c.title} ${c.excerpt}`, term)).slice(0, 10));
  else unavailable.push('Content');
  return { items, unavailable };
}
