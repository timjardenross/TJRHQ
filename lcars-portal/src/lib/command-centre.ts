/**
 * Captain's Chair — command-centre live data (USS-TJR-MSN-CCP-001).
 *
 * Reuse-first: this module adds NO new stores or pipelines. It reads the same
 * Command Memory the platform-runtime already populates and reuses the portal's existing
 * fetchers (loadHumanSystems, loadDelivery). Every function returns null/empty on
 * failure so callers fall back to the existing mock panels — identical contract to
 * ros-data.ts.
 *
 * Sources (all existing):
 *   human_systems_recommendations  → Recommended Action (XO Daily Operating Picture)
 *   loadHumanSystems()             → Human Systems readiness  (reused)
 *   loadDelivery()                 → Engineering readiness     (reused)
 *   intelligence_briefs            → Resilience (ORI) readiness
 *   missions                       → Operations + What-Changed
 *   decisions                      → What-Changed + Decision review
 *   mission_execution_events       → Officer activity feed
 *   strategic_objectives           → Operations context
 */

import { supabase } from './supabase';
import { loadHumanSystems, fetchOpenMissionCount } from './human-systems';
import { loadDelivery } from './delivery';
import type { StatusTone } from './types';

function isoDaysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString();
}

function timeOf(iso: string | null | undefined): string {
  if (!iso) return '--:--';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '--:--' : d.toISOString().slice(11, 16);
}

// ── Recommended Action (WP1) ─────────────────────────────────────────────────

export interface RecommendedAction {
  action: string;
  sourceOfficer: string;
  why: string;
  confidence: string;
}

const OFFICER_BY_DOMAIN: Record<string, string> = {
  resilience: 'XO · Daily Operating Picture',
  medical: 'Human Systems Officer',
  movement: 'Human Systems Officer',
  nutrition: 'Human Systems Officer',
  mind: 'Human Systems Officer',
  communications: 'Communications & Presence Officer',
};

export async function fetchRecommendedAction(): Promise<RecommendedAction | null> {
  if (!supabase) return null;
  try {
    const { data, error } = await supabase
      .from('human_systems_recommendations')
      .select('summary, kind, domain, issued_on, created_at')
      .in('kind', ['daily_brief', 'highest_leverage'])
      .order('created_at', { ascending: false })
      .limit(1)
      .maybeSingle<{ summary: string; kind: string; domain: string | null; issued_on: string | null }>();
    if (error || !data) return null;
    const today = new Date().toISOString().slice(0, 10);
    return {
      action: data.summary,
      sourceOfficer: OFFICER_BY_DOMAIN[data.domain ?? ''] ?? 'XO · Daily Operating Picture',
      why: data.kind === 'daily_brief'
        ? 'Highest-leverage action from the unified daily operating picture.'
        : 'Highest-leverage action from the capacity & decision engine.',
      confidence: data.issued_on === today ? "High — today's brief" : 'From the most recent brief',
    };
  } catch {
    return null;
  }
}

// ── Ship Status (WP1) ────────────────────────────────────────────────────────

export interface ShipDomain {
  key: string;
  label: string;
  state: string;
  tone: StatusTone;
  trend: 'up' | 'down' | 'steady';
  detail: string;
}

const RISK_TONE: Record<string, { tone: StatusTone; trend: ShipDomain['trend'] }> = {
  GREEN: { tone: 'status', trend: 'steady' },
  AMBER: { tone: 'operations', trend: 'down' },
  RED: { tone: 'operations', trend: 'down' },
};

async function fetchResilienceDomain(): Promise<ShipDomain | null> {
  if (!supabase) return null;
  try {
    const { data } = await supabase
      .from('intelligence_briefs')
      .select('overall_risk, bottom_line, generated_at')
      .order('generated_at', { ascending: false })
      .limit(1)
      .maybeSingle<{ overall_risk: string | null; bottom_line: string | null }>();
    if (!data) return null;
    const risk = (data.overall_risk ?? 'GREEN').toUpperCase();
    const t = RISK_TONE[risk] ?? { tone: 'neutral' as StatusTone, trend: 'steady' as const };
    return {
      key: 'resilience', label: 'Resilience', state: risk, tone: t.tone, trend: t.trend,
      detail: (data.bottom_line ?? 'Operational resilience nominal').slice(0, 80),
    };
  } catch {
    return null;
  }
}

const BAND_TONE: Record<string, StatusTone> = {
  good: 'status', moderate: 'command', limited: 'operations', depleted: 'operations',
};

export async function fetchShipStatus(): Promise<ShipDomain[] | null> {
  if (!supabase) return null;
  try {
    const [hs, del, resilience, openCount] = await Promise.all([
      loadHumanSystems(), loadDelivery(), fetchResilienceDomain(), fetchOpenMissionCount(),
    ]);

    const domains: ShipDomain[] = [];

    // Human Systems (reused engine).
    const band = hs.snapshot.overallBand;
    domains.push({
      key: 'human-systems', label: 'Human Systems',
      state: `${band.toUpperCase()} ${Math.round(hs.snapshot.overallScore)}`,
      tone: BAND_TONE[band] ?? 'neutral', trend: 'steady',
      detail: `Capacity ${band} · ${openCount ?? '—'} open missions`,
    });

    // Engineering (reused EDO control tower).
    const m = del.metrics;
    const engTone: StatusTone = !m ? 'neutral' : m.blocked_count > 0 ? 'operations' : 'status';
    domains.push({
      key: 'engineering', label: 'Engineering',
      state: m ? (m.blocked_count > 0 ? 'BLOCKED' : 'FLOWING') : 'NO DATA',
      tone: engTone, trend: 'steady',
      detail: m ? `${m.open_count} open · ${m.blocked_count} blocked` : 'No delivery data',
    });

    // Operations (open missions).
    const open = openCount ?? 0;
    domains.push({
      key: 'operations', label: 'Operations',
      state: open > 5 ? 'BUSY' : 'NOMINAL', tone: open > 5 ? 'command' : 'status', trend: 'steady',
      detail: `${open} active mission(s)`,
    });

    // Resilience (ORI).
    if (resilience) domains.push(resilience);

    // Knowledge (lessons captured).
    const { count: lessons } = await supabase
      .from('lessons_learned').select('*', { count: 'exact', head: true });
    domains.push({
      key: 'knowledge', label: 'Knowledge',
      state: lessons ? 'ACTIVE' : 'NO DATA', tone: lessons ? 'science' : 'neutral', trend: 'up',
      detail: `${lessons ?? 0} lessons in Command Memory`,
    });

    // Infrastructure (execution health).
    const { count: failed } = await supabase
      .from('mission_execution_events').select('*', { count: 'exact', head: true }).eq('status', 'failed');
    domains.push({
      key: 'infrastructure', label: 'Infrastructure',
      state: failed && failed > 0 ? 'CHECK' : 'NOMINAL',
      tone: failed && failed > 0 ? 'operations' : 'status', trend: 'steady',
      detail: failed && failed > 0 ? `${failed} failed dispatch(es)` : 'Dispatch healthy',
    });

    return domains;
  } catch {
    return null;
  }
}

// ── What Changed Since Last Visit (WP2) ──────────────────────────────────────

export interface ChangeItem {
  kind: string;
  label: string;
  detail: string;
  tone: StatusTone;
}

export async function fetchWhatChanged(sinceIso?: string): Promise<ChangeItem[] | null> {
  if (!supabase) return null;
  const since = sinceIso ?? isoDaysAgo(1);
  try {
    const items: ChangeItem[] = [];

    const { data: newM } = await supabase
      .from('missions').select('title, created_at').gte('created_at', since)
      .order('created_at', { ascending: false }).limit(5);
    (newM ?? []).forEach((r: { title: string }) =>
      items.push({ kind: 'mission', label: 'New mission', detail: r.title, tone: 'command' }));

    const { data: closedM } = await supabase
      .from('missions').select('title, closed_at').gte('closed_at', since)
      .order('closed_at', { ascending: false }).limit(5);
    (closedM ?? []).forEach((r: { title: string }) =>
      items.push({ kind: 'mission', label: 'Mission closed', detail: r.title, tone: 'status' }));

    const { count: decisions } = await supabase
      .from('decisions').select('*', { count: 'exact', head: true }).gte('timestamp', since);
    if (decisions && decisions > 0)
      items.push({ kind: 'decision', label: 'Decisions recorded', detail: `${decisions} since last visit`, tone: 'science' });

    return items;
  } catch {
    return null;
  }
}

// ── Officer Activity Feed (WP3) ──────────────────────────────────────────────

export interface ActivityEvent {
  time: string;
  label: string;
  tone: StatusTone;
}

export async function fetchOfficerActivity(limit = 8): Promise<ActivityEvent[] | null> {
  if (!supabase) return null;
  try {
    const events: ({ at: string } & ActivityEvent)[] = [];

    const { data: execs } = await supabase
      .from('mission_execution_events').select('status, mission_id, created_at')
      .order('created_at', { ascending: false }).limit(limit);
    (execs ?? []).forEach((r: { status: string; mission_id: string; created_at: string }) =>
      events.push({ at: r.created_at, time: timeOf(r.created_at), tone: 'engineering',
        label: `Engineering · mission ${r.mission_id} ${r.status}` }));

    const { data: recs } = await supabase
      .from('human_systems_recommendations').select('kind, domain, created_at')
      .order('created_at', { ascending: false }).limit(limit);
    (recs ?? []).forEach((r: { kind: string; domain: string | null; created_at: string }) =>
      events.push({ at: r.created_at, time: timeOf(r.created_at), tone: 'command',
        label: `${OFFICER_BY_DOMAIN[r.domain ?? ''] ?? 'XO'} · ${r.kind.replace('_', ' ')}` }));

    const { data: decs } = await supabase
      .from('decisions').select('decision_type, timestamp')
      .order('timestamp', { ascending: false }).limit(limit);
    (decs ?? []).forEach((r: { decision_type: string | null; timestamp: string }) =>
      events.push({ at: r.timestamp, time: timeOf(r.timestamp), tone: 'science',
        label: `Decision logged · ${r.decision_type ?? 'decision'}` }));

    return events
      .sort((a, b) => (a.at < b.at ? 1 : -1))
      .slice(0, limit)
      .map(({ time, label, tone }) => ({ time, label, tone }));
  } catch {
    return null;
  }
}
