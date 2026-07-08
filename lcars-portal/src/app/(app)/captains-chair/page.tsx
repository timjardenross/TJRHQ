'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { StatusBadge } from '@/components/StatusBadge';
import { ROSPanels } from '@/components/ROSPanels';
import { MobileOperatingPicture } from '@/components/MobileOperatingPicture';
import { CaptainApprovalQueue } from '@/components/CaptainApprovalQueue';
import { CaptainIntelligencePanel } from '@/components/CaptainIntelligencePanel';
import ProactiveSignals from '@/components/ProactiveSignals';
import { LCARSPanel } from '@/components/LCARSPanel';
import { DataSourceIndicator } from '@/components/DataSourceIndicator';
import { DEPARTMENTS, toneClasses, stateToneClasses } from '@/lib/departments';
import { useROSData } from '@/lib/useROSData';
import { useAlerts } from '@/lib/useAlerts';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { loadSinceLastSession, type SinceLastSessionSummary } from '@/lib/sinceLastSession';
import { ACTIVE_STATUSES, COMPLETED_STATUSES, AWAITING_CAPTAIN_STATUSES } from '@/lib/missionStatus';
import {
  fetchEngineeringQueue,
  LIFECYCLE_ORDER,
  LIFECYCLE_LABEL,
  LIFECYCLE_TONE,
  type EngineeringQueueData,
} from '@/lib/engineering-queue';
import type { AlertSeverity } from '@/lib/alerts';
import { departments } from '@/lib/mockData';
import type { RecoveryPostureBand, StateTone } from '@/lib/types';

// ── Live mission summary (WP A: Truth & Trust — MSN-0321) ────────────────────
// Single query backs Priority Overview's decision/mission counts and the
// Mission Board tiles below, so both read the same authoritative numbers
// the /missions page itself reports.

interface LiveMissionStats {
  total: number;
  active: number;
  in_progress: number;
  blocked: number;
  completed: number;
  decisionsCount: number;
}

function useLiveMissionStats(): { stats: LiveMissionStats | null; loading: boolean } {
  const [stats, setStats] = useState<LiveMissionStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const supabase = createSupabaseBrowserClient();
        const { data } = await supabase.from('missions').select('status');
        if (cancelled || !data) return;
        setStats({
          total: data.length,
          active: data.filter((m) => ACTIVE_STATUSES.includes(m.status)).length,
          in_progress: data.filter((m) => m.status === 'Implemented' || m.status === 'Tested').length,
          blocked: data.filter((m) => m.status === 'Blocked').length,
          completed: data.filter((m) => COMPLETED_STATUSES.includes(m.status)).length,
          decisionsCount: data.filter((m) => AWAITING_CAPTAIN_STATUSES.includes(m.status)).length,
        });
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  return { stats, loading };
}

function useLiveEngineeringQueue(): { data: EngineeringQueueData | null; loading: boolean } {
  const [data, setData] = useState<EngineeringQueueData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchEngineeringQueue()
      .then((d) => { if (!cancelled) setData(d); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return { data, loading };
}

// MSN-0345: replaces TodaysBriefing's fabricated summary numbers with the
// real CaptainBriefDocument the /captains-brief page itself renders — same
// API route, same data, no new backend.
interface TodaysBriefingStats {
  confidence: number | null;
  priorities: number;
  warnings: number;
  recommendations: number;
  nextActions: number;
}

// MSN-0345: Operational Picture item shape — a subset of CaptainBriefItem
// (captains-brief/page.tsx's own local type) sufficient for a compact
// "situation in seconds" view. Not re-fetched separately — comes from the
// same /api/captain-brief call TodaysBriefing already makes.
interface OperationalPictureItem {
  event_id: string | null;
  domain: string;
  event_type: string;
  reason: string;
  risk_score: number | null;
  recommendation: { description: string; confidence: number | null; evidence: string[] } | null;
}

function useTodaysBriefing(): {
  stats: TodaysBriefingStats | null;
  loading: boolean;
  operationalPicture: OperationalPictureItem[];
} {
  const [stats, setStats] = useState<TodaysBriefingStats | null>(null);
  const [operationalPicture, setOperationalPicture] = useState<OperationalPictureItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/captain-brief')
      .then((r) => (r.ok ? r.json() : null))
      .then((doc) => {
        if (cancelled || !doc) return;
        setStats({
          confidence: doc.confidence ?? null,
          priorities: doc.priorities?.length ?? 0,
          warnings: doc.warnings?.length ?? 0,
          recommendations: doc.recommendations?.length ?? 0,
          nextActions: doc.next_actions?.length ?? 0,
        });
        // Warnings first (highest risk_score, already the page's own
        // definition of "needs a look"), then operational_intelligence,
        // deduped by event_id, capped — a picture, not a full re-list.
        const pool = [...(doc.warnings ?? []), ...(doc.operational_intelligence ?? [])];
        const seen = new Set<string>();
        const picture: OperationalPictureItem[] = [];
        for (const item of pool) {
          const key = item.event_id ?? item.reason;
          if (seen.has(key)) continue;
          seen.add(key);
          picture.push(item);
          if (picture.length >= 5) break;
        }
        setOperationalPicture(picture);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return { stats, loading, operationalPicture };
}

// MSN-0345 Objective 5: "understand the situation within seconds" — a
// compact, real view over Operational Intelligence's actual computed
// fields (risk_score, confidence, evidence), not a new backend query.
// Reuses ConfidenceIndicator + the evidence disclosure pattern shipped for
// Captain's Brief (MSN-0344) rather than inventing a third rendering.
function OperationalPicture({ items, loading }: { items: OperationalPictureItem[]; loading: boolean }) {
  return (
    <LCARSPanel title="Operational Picture" accent="science" eyebrow="Current incidents and emerging risks — Operational Intelligence">
      {loading ? (
        <p className="text-xs text-lcars-muted animate-pulse">Reading the operational picture…</p>
      ) : items.length === 0 ? (
        <p className="text-xs text-lcars-muted">No active incidents or emerging risks in the current brief.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((item, i) => (
            <li key={item.event_id ?? i} className="rounded-md border border-edge bg-panel-2/60 p-2.5">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-[10px] uppercase tracking-wide text-lcars-muted">
                    {item.domain} · {item.event_type}
                  </p>
                  <p className="mt-0.5 text-xs text-lcars-text/90">{item.reason}</p>
                </div>
                {item.risk_score != null && (
                  <span className="shrink-0 font-mono text-[11px] font-bold text-operations">
                    risk {Math.round(item.risk_score)}
                  </span>
                )}
              </div>
              {item.recommendation && (
                <div className="mt-1.5 flex flex-col gap-1">
                  <p className="text-[11px] text-command">→ {item.recommendation.description}</p>
                  {item.recommendation.evidence && item.recommendation.evidence.length > 0 && (
                    <details className="text-[11px]">
                      <summary className="cursor-pointer text-lcars-muted hover:text-lcars-text">
                        Evidence ({item.recommendation.evidence.length})
                      </summary>
                      <ul className="mt-1 flex flex-col gap-0.5 pl-3">
                        {item.recommendation.evidence.map((e, j) => (
                          <li key={j} className="list-disc text-lcars-text/70">{e}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <Link href="/intelligence" className="mt-2 inline-block text-[10px] uppercase tracking-[0.15em] text-command hover:text-command/70">
        Full Intelligence Picture →
      </Link>
    </LCARSPanel>
  );
}

// MSN-0345: replaces CaptainTimeline's fabricated schedule with today's real
// Event Bus activity (core_events) — the same table 12+ real emit-points
// across the platform already write to (see MSN-0343's Registry work).
// Every row here already happened, so all render as "completed" — there is
// no real "scheduled" future-event source to distinguish from today.
interface LiveTimelineEvent {
  id: string;
  time: string;
  title: string;
}

function useCaptainTimeline(): { events: LiveTimelineEvent[]; loading: boolean } {
  const [events, setEvents] = useState<LiveTimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const supabase = createSupabaseBrowserClient();
        const since = new Date();
        since.setHours(0, 0, 0, 0);
        const { data } = await supabase
          .from('core_events')
          .select('event_id, event_type, domain, occurred_at')
          .gte('occurred_at', since.toISOString())
          .order('occurred_at', { ascending: false })
          .limit(8);
        if (cancelled) return;
        setEvents(
          (data ?? []).map((e) => ({
            id: e.event_id,
            time: new Date(e.occurred_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            title: `${e.domain} · ${e.event_type}`,
          })),
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  return { events, loading };
}

// MSN-0345: Since Last Session hook + panel. See lib/sinceLastSession.ts's
// own header for exactly what this can and can't answer honestly.

function useSinceLastSession(): { summary: SinceLastSessionSummary | null; loading: boolean } {
  const [summary, setSummary] = useState<SinceLastSessionSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    loadSinceLastSession()
      .then((s) => { if (!cancelled) setSummary(s); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return { summary, loading };
}

function SinceLastSessionPanel({ summary, loading }: { summary: SinceLastSessionSummary | null; loading: boolean }) {
  if (loading || !summary) return null;
  if (summary.firstSession) {
    return (
      <LCARSPanel title="Since Last Session" accent="command">
        <p className="text-xs text-lcars-muted">First session on this browser — nothing to compare against yet.</p>
      </LCARSPanel>
    );
  }
  return (
    <LCARSPanel title="Since Last Session" accent="command" eyebrow={`Since ${new Date(summary.previousSessionAt!).toLocaleString()}`}>
      {summary.eventCount === 0 ? (
        <p className="text-xs text-lcars-muted">Nothing new since your last visit.</p>
      ) : (
        <div className="flex flex-col gap-2">
          <p className="text-sm text-lcars-text/90">
            <span className="font-mono font-bold text-command">{summary.eventCount}</span> event
            {summary.eventCount === 1 ? '' : 's'} across the platform since your last visit.
          </p>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] uppercase tracking-wide text-lcars-muted">
            {summary.byDomain.map((d) => (
              <span key={d.domain}>{d.domain} · {d.count}</span>
            ))}
          </div>
        </div>
      )}
      <p className="mt-2 text-[10px] text-lcars-muted/70">
        Answers &quot;what changed.&quot; What completed, worsened, was delegated, or was learned
        aren&apos;t yet trackable — no data source for those exists in the platform today (honestly
        disclosed, not fabricated — see MSN-0345).
      </p>
    </LCARSPanel>
  );
}

// ── Shared micro-components ───────────────────────────────────────────────────

function SectionHeader({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="text-[11px] font-bold uppercase tracking-[0.25em] text-lcars-muted">{title}</h2>
      {action}
    </div>
  );
}

function Panel({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-lcars border border-edge bg-panel/60 p-3 ${className}`}>
      {children}
    </div>
  );
}

// ── Posture tone map ──────────────────────────────────────────────────────────

const POSTURE_TONE: Record<RecoveryPostureBand, { text: string; border: string; bg: string }> = {
  STRONG:  { text: 'text-status',     border: 'border-status',     bg: 'bg-status/10' },
  STABLE:  { text: 'text-command',    border: 'border-command',    bg: 'bg-command/10' },
  FRAGILE: { text: 'text-operations', border: 'border-operations', bg: 'bg-operations/10' },
  REST:    { text: 'text-medical',    border: 'border-medical',    bg: 'bg-medical/10' },
  UNKNOWN: { text: 'text-lcars-muted', border: 'border-edge',     bg: 'bg-edge/10' },
};

// ── Captain Capacity Headline ─────────────────────────────────────────────────
// D-055: Capacity is the primary strategic measure. It leads the page.

function CapacityHeadline({
  posture,
  postureMessage,
  capacityMessage,
}: {
  posture: RecoveryPostureBand;
  postureMessage: string;
  capacityMessage: string;
}) {
  const c = POSTURE_TONE[posture];
  const capacityLabel: Record<RecoveryPostureBand, string> = {
    STRONG:  'High',
    STABLE:  'Moderate',
    FRAGILE: 'Low',
    REST:    'Minimal — rest priority',
    UNKNOWN: 'Unknown',
  };
  return (
    <div className={`rounded-lcars border ${c.border} ${c.bg} p-4`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.3em] text-lcars-muted mb-1">
            Captain Capacity — D-055
          </p>
          <div className="flex items-baseline gap-3">
            <p className={`font-lcars text-3xl font-bold ${c.text}`}>{capacityLabel[posture]}</p>
            <StatusBadge label={posture} tone={
              posture === 'STRONG' ? 'status' :
              posture === 'STABLE' ? 'command' :
              posture === 'FRAGILE' ? 'operations' :
              posture === 'REST' ? 'medical' : 'neutral'
            } />
          </div>
          <p className="text-xs text-lcars-text/80 mt-2 leading-relaxed max-w-prose">
            {postureMessage || capacityMessage}
          </p>
        </div>
        <div className="flex flex-col gap-2 shrink-0">
          <Link
            href="/recovery-brief"
            className="rounded-lcars border border-medical/40 bg-medical/5 px-3 py-2 text-[10px] uppercase tracking-[0.2em] text-medical hover:border-medical/70 transition-colors text-center"
          >
            Recovery Brief →
          </Link>
          <Link
            href="/captains-log"
            className="rounded-lcars border border-edge px-3 py-2 text-[10px] uppercase tracking-[0.2em] text-lcars-muted hover:border-command hover:text-command transition-colors text-center"
          >
            Log Today →
          </Link>
        </div>
      </div>
    </div>
  );
}

// ── Fleet Status Conditional ──────────────────────────────────────────────────
// D-055: On FRAGILE/REST, mission detail recedes. Recovery leads.

function FleetStatusConditional({
  posture,
  children,
}: {
  posture: RecoveryPostureBand;
  children: React.ReactNode;
}) {
  const isProtected = posture === 'FRAGILE' || posture === 'REST';
  const c = POSTURE_TONE[posture];

  if (!isProtected) {
    return <>{children}</>;
  }

  return (
    <Panel>
      <SectionHeader title="Mission Detail" />
      <p className="mb-3 text-[11px] leading-relaxed text-lcars-text/80">
        Recovery posture is{' '}
        <span className={`font-semibold ${c.text}`}>{posture}</span>{' '}
        today. The nervous system benefits from reduced ambient load.
        Mission detail is available when you need it.
      </p>
      <details className="group">
        <summary className="w-full cursor-pointer rounded border border-edge bg-panel-2/60 py-1.5 text-center text-[10px] uppercase tracking-[0.2em] text-lcars-muted hover:text-lcars-text">
          View Active Missions
        </summary>
        <div className="mt-3 flex flex-col gap-4">
          {children}
        </div>
      </details>
    </Panel>
  );
}

// ── Priority Overview ─────────────────────────────────────────────────────────

function PriorityOverview({
  decisionsCount,
  alertsCount,
  activeMissionsCount,
  loading,
}: {
  decisionsCount: number;
  alertsCount: number;
  activeMissionsCount: number;
  loading: boolean;
}) {
  const items = [
    {
      label: 'Decisions Awaiting Approval',
      sub: 'Require your review',
      count: decisionsCount,
      tone: 'command' as const
    },
    {
      label: 'Alerts Requiring Attention',
      sub: 'Gated, meaningful escalations only',
      count: alertsCount,
      tone: 'operations' as const
    },
    {
      label: 'Active Missions',
      sub: 'In progress across departments',
      count: activeMissionsCount,
      tone: 'medical' as const
    },
  ];
  return (
    <Panel>
      <SectionHeader
        title="Priority Overview"
        action={<DataSourceIndicator live={!loading} loading={loading} variant="inline" />}
      />
      <ul className="flex flex-col gap-2">
        {items.map((item) => {
          const dept = DEPARTMENTS[item.tone];
          return (
            <li
              key={item.label}
              className="flex items-center gap-3 rounded-md border border-edge bg-panel-2/60 p-2"
            >
              <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md ${dept.bg}`}>
                <span className="font-mono text-[10px] font-bold text-space">
                  {String(item.count).padStart(2, '0')}
                </span>
              </span>
              <div className="min-w-0 flex-1">
                <p className={`text-[11px] font-semibold uppercase tracking-wide ${dept.text}`}>
                  {item.label}
                </p>
                <p className="text-[10px] text-lcars-muted">{item.sub}</p>
              </div>
              <span className={`font-lcars text-xl font-bold ${dept.text}`}>{item.count}</span>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

// ── Ship Status ───────────────────────────────────────────────────────────────
// MSN-0345: retired. No real per-subsystem health source exists anywhere in
// the platform today, and building one (new backend queries across N
// invented "ship systems") is exactly the kind of new backend service this
// mission's own scope explicitly avoids ("do not create new backend
// services unless absolutely necessary"). A permanently-fake panel is worse
// than no panel — removed rather than left mock. If real per-subsystem
// health becomes a real need, `/operations`'s existing service/integration
// status is the closer real starting point, not this component's shape.

// ── Captain's Timeline ────────────────────────────────────────────────────────

function CaptainTimeline({ events, loading }: { events: LiveTimelineEvent[]; loading: boolean }) {
  return (
    <Panel>
      <SectionHeader
        title="Captain's Timeline"
        action={<DataSourceIndicator live={!loading} loading={loading} variant="inline" />}
      />
      {loading ? (
        <p className="text-[10px] text-lcars-muted">Loading…</p>
      ) : events.length === 0 ? (
        <p className="text-[10px] text-lcars-muted">No events logged yet today.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {events.map((event) => (
            <li key={event.id} className="flex items-center gap-3">
              <span className="w-10 shrink-0 font-mono text-[11px] text-lcars-muted">{event.time}</span>
              <span className="h-2 w-2 shrink-0 rounded-full bg-status" />
              <p className="flex-1 text-[11px] font-medium text-lcars-text">{event.title}</p>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

// ── Alerts sidebar ────────────────────────────────────────────────────────────

const ALERT_SEVERITY_TONE: Record<AlertSeverity, StateTone> = {
  critical: 'crit',
  high: 'warn',
  warning: 'warn',
};

function AlertsSidebar({
  alerts,
  loading,
}: {
  alerts: { id: string; title: string; why: string; href: string; severity: AlertSeverity }[];
  loading: boolean;
}) {
  return (
    <Panel>
      <SectionHeader
        title="Alerts"
        action={<DataSourceIndicator live={!loading} loading={loading} variant="inline" />}
      />
      {loading ? (
        <p className="text-[10px] text-lcars-muted">Loading…</p>
      ) : alerts.length === 0 ? (
        <p className="text-[10px] text-lcars-muted">All clear — nothing needs you right now.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {alerts.map((a) => {
            const c = stateToneClasses(ALERT_SEVERITY_TONE[a.severity]);
            return (
              <li key={a.id} className="rounded-md border border-edge bg-panel-2/60 p-2">
                <Link href={a.href} className="block">
                  <div className="flex items-start gap-2">
                    <span className={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${c.dot}`} />
                    <div>
                      <p className={`text-[11px] font-bold uppercase ${c.text}`}>{a.title}</p>
                      <p className="text-[10px] text-lcars-muted">{a.why}</p>
                    </div>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

// ── Department Row ────────────────────────────────────────────────────────────
// MSN-0345: the per-department metric VALUES (dept.metrics) were fabricated —
// no real query backed them, and building one across 5 unrelated domains'
// tables in this pass would be new backend work this mission's scope
// avoids. The department NAMES and LINKS are real (they route to real,
// live pages) — kept, with the fake numbers removed rather than shown
// alongside a now-misleading "live" label. DataSourceIndicator now
// correctly reflects what's actually true: this is real navigation, not
// live metrics.

function DepartmentRow() {
  const depts = departments.filter((d) => d.key !== 'status');
  return (
    <div>
      <SectionHeader
        title="Departments"
        action={<DataSourceIndicator live={true} variant="inline" />}
      />
      <div className="overflow-x-auto">
      <div className="flex gap-3" style={{ minWidth: `${depts.length * 160}px` }}>
        {depts.map((dept) => {
          const theme = DEPARTMENTS[dept.key];
          return (
            <Link key={dept.key} href={`/${dept.key}`} className="block min-w-[160px] flex-1">
              <div className="rounded-lcars border border-edge bg-panel/60 p-3 hover:border-command/60 transition-colors h-full">
                <div className="flex items-center gap-2">
                  <span className={`h-5 w-5 shrink-0 rounded-md ${theme.bg}`} />
                  <h3 className={`text-[10px] font-bold uppercase tracking-wider ${theme.text}`}>
                    {dept.name}
                  </h3>
                </div>
              </div>
            </Link>
          );
        })}
      </div>
      </div>
    </div>
  );
}

// ── Mission Board ─────────────────────────────────────────────────────────────
// WP A: Truth & Trust (MSN-0321) — was a fabricated 5-column kanban with
// invented mission titles ("Security Audit", "VPS Hardening", ...). Replaced
// with the same live stat tiles the /missions page itself reports, off the
// same query useLiveMissionStats() runs — one authoritative number, not two.

function MissionBoard({
  stats,
  loading,
}: {
  stats: LiveMissionStats | null;
  loading: boolean;
}) {
  const tiles = [
    { label: 'Total', value: stats?.total ?? 0, tone: 'command' as const },
    { label: 'Active', value: stats?.active ?? 0, tone: 'medical' as const },
    { label: 'In Progress', value: stats?.in_progress ?? 0, tone: 'science' as const },
    { label: 'Blocked', value: stats?.blocked ?? 0, tone: 'operations' as const },
    { label: 'Completed', value: stats?.completed ?? 0, tone: 'status' as const },
  ];
  return (
    <Panel>
      <SectionHeader
        title="Mission Board"
        action={
          <div className="flex items-center gap-3">
            <DataSourceIndicator live={!loading} loading={loading} variant="inline" />
            <Link href="/missions" className="text-[10px] uppercase tracking-[0.15em] text-command hover:text-command/70">
              View All →
            </Link>
          </div>
        }
      />
      <div className="grid grid-cols-5 gap-2">
        {tiles.map((t) => {
          const dept = DEPARTMENTS[t.tone];
          return (
            <div key={t.label} className="rounded-md border border-edge bg-panel-2/60 p-2 text-center">
              <p className={`font-lcars text-lg font-bold ${dept.text}`}>{t.value}</p>
              <p className="text-[9px] uppercase tracking-wide text-lcars-muted">{t.label}</p>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

// ── Today's Briefing ──────────────────────────────────────────────────────────
// MSN-0345: replaced fabricated summary numbers with the real
// CaptainBriefDocument (same /api/captain-brief route, same data /captains-brief renders).

function TodaysBriefing({ stats, loading }: { stats: TodaysBriefingStats | null; loading: boolean }) {
  const rows = stats
    ? [
        { label: 'Confidence', value: stats.confidence != null ? `${stats.confidence}%` : '—', tone: 'command' as const },
        { label: 'Priorities', value: String(stats.priorities), tone: 'command' as const },
        { label: 'Warnings', value: String(stats.warnings), tone: stats.warnings > 0 ? 'operations' as const : 'status' as const },
        { label: 'Recommendations', value: String(stats.recommendations), tone: 'command' as const },
        { label: 'Next Actions', value: String(stats.nextActions), tone: 'command' as const },
      ]
    : [];
  return (
    <Panel>
      <SectionHeader
        title="Today's Briefing"
        action={<DataSourceIndicator live={!loading} loading={loading} variant="inline" />}
      />
      {loading ? (
        <p className="text-[10px] text-lcars-muted">Loading…</p>
      ) : !stats ? (
        <p className="text-[10px] text-lcars-muted">Brief unavailable — run the daily brief.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {rows.map((item) => {
            const c = toneClasses(item.tone);
            return (
              <li key={item.label} className="flex items-center justify-between gap-2">
                <span className="text-[10px] uppercase tracking-wide text-lcars-muted">{item.label}</span>
                <span className={`font-mono text-xs font-bold ${c.text}`}>{item.value}</span>
              </li>
            );
          })}
        </ul>
      )}
      <Link href="/captains-brief" className="mt-2 inline-block text-[10px] uppercase tracking-[0.15em] text-command hover:text-command/70">
        View Full Brief →
      </Link>
    </Panel>
  );
}

// ── Engineering Queue ─────────────────────────────────────────────────────────
// WP A: Truth & Trust (MSN-0321) — was a static mock count. Now reads the
// same fetchEngineeringQueue() lifecycle counts the /engineering-queue page
// itself renders, and links there (was pointing at /engineering — a
// different page with different data — which is a truth bug in its own right).

function EngineeringQueue({
  data,
  loading,
}: {
  data: EngineeringQueueData | null;
  loading: boolean;
}) {
  const rows = LIFECYCLE_ORDER.map((l) => ({
    label: LIFECYCLE_LABEL[l],
    count: data?.counts[l] ?? 0,
    tone: LIFECYCLE_TONE[l],
  }));
  return (
    <Panel>
      <SectionHeader
        title="Engineering Queue"
        action={<DataSourceIndicator live={!loading} loading={loading} variant="inline" />}
      />
      <ul className="flex flex-col gap-2">
        {rows.map((item) => {
          const c = toneClasses(item.tone);
          return (
            <li key={item.label} className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${c.dot}`} />
                <span className="text-[10px] uppercase tracking-wide text-lcars-muted">{item.label}</span>
              </div>
              <span className={`font-mono text-sm font-bold ${c.text}`}>{item.count}</span>
            </li>
          );
        })}
      </ul>
      <Link
        href="/engineering-queue"
        className="mt-3 block w-full rounded border border-edge bg-panel-2/60 py-1.5 text-center text-[10px] uppercase tracking-[0.2em] text-engineering hover:border-engineering/50"
      >
        View Engineering Queue →
      </Link>
    </Panel>
  );
}

// ── Medical Bay Link ──────────────────────────────────────────────────────────

function MedicalBayLink() {
  return (
    <Panel>
      <SectionHeader title="Recovery Detail" />
      <p className="mb-3 text-[11px] leading-relaxed text-lcars-text/80">
        Full recovery indexes, Life Participation Score, body context trend,
        and Medical Officer assessment.
      </p>
      <Link
        href="/medical"
        className="block w-full rounded border border-medical/40 bg-medical/5 py-2 text-center text-[10px] uppercase tracking-[0.2em] text-medical hover:border-medical/70"
      >
        View Medical Bay →
      </Link>
    </Panel>
  );
}

// ── Notebook Widget (EXEC-010B WP9) ──────────────────────────────────────────

interface NbNote {
  id: string;
  title: string | null;
  raw_content: string;
  status: string;
  created_at: string;
  recommended_route: string | null;
  strategic_alignment_score: number | null;
  routed_entity_type: string | null;
  routed_to_id: string | null;
}

function NotebookWidget() {
  const [readyCount, setReadyCount]       = useState<number | null>(null);
  const [capturedCount, setCapturedCount] = useState<number | null>(null);
  const [topOpportunity, setTopOpportunity] = useState<NbNote | null>(null);
  const [recentRouted, setRecentRouted]   = useState<NbNote[]>([]);

  useEffect(() => {
    const supabase = createSupabaseBrowserClient();
    supabase
      .from('intelligence_notes')
      .select('id, title, raw_content, status, created_at, recommended_route, strategic_alignment_score, routed_entity_type, routed_to_id')
      .in('status', ['CAPTURED', 'OFFICER_REVIEW', 'NUMBER_ONE_REVIEW', 'READY_FOR_ROUTING', 'ROUTED'])
      .order('created_at', { ascending: false })
      .limit(100)
      .then(({ data }) => {
        if (!data) return;
        const ready = data.filter((n) => n.status === 'READY_FOR_ROUTING');
        const captured = data.filter((n) => n.status === 'CAPTURED');
        const routed = data.filter((n) => n.status === 'ROUTED' && n.routed_to_id);

        setReadyCount(ready.length);
        setCapturedCount(captured.length);

        const top = ready.sort((a, b) =>
          (b.strategic_alignment_score ?? 0) - (a.strategic_alignment_score ?? 0)
        )[0] ?? null;
        setTopOpportunity(top as NbNote | null);
        setRecentRouted((routed.slice(0, 3) as NbNote[]));
      });
  }, []);

  const hasAction = (readyCount ?? 0) > 0;

  function noteTitle(n: NbNote) {
    return n.title || n.raw_content.slice(0, 48) + (n.raw_content.length > 48 ? '…' : '');
  }

  return (
    <Panel className={hasAction ? 'border-command/40' : ''}>
      <SectionHeader
        title="Captain's Notebook"
        action={
          <Link
            href="/captains-notebook"
            className="text-[10px] uppercase tracking-[0.15em] text-command hover:text-command/70"
          >
            Open →
          </Link>
        }
      />
      {readyCount === null ? (
        <p className="text-[10px] text-lcars-muted">Loading…</p>
      ) : (
        <div className="flex flex-col gap-2">
          {/* Route queue */}
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className={`h-2 w-2 shrink-0 rounded-full ${hasAction ? 'bg-command animate-pulse' : 'bg-edge'}`} />
              <span className="text-[10px] uppercase tracking-wide text-lcars-muted">Ready for routing</span>
            </div>
            <span className={`font-mono text-sm font-bold ${hasAction ? 'text-command' : 'text-lcars-muted'}`}>
              {readyCount}
            </span>
          </div>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 shrink-0 rounded-full bg-edge" />
              <span className="text-[10px] uppercase tracking-wide text-lcars-muted">Pending triage</span>
            </div>
            <span className="font-mono text-sm font-bold text-lcars-muted">{capturedCount}</span>
          </div>

          {/* Top opportunity */}
          {topOpportunity && (
            <div className="mt-1 rounded border border-command/20 bg-command/5 px-2 py-1.5">
              <p className="text-[9px] uppercase tracking-[0.2em] text-command mb-0.5">Top opportunity</p>
              <p className="text-[10px] text-lcars-text truncate">{noteTitle(topOpportunity)}</p>
              {topOpportunity.recommended_route && (
                <p className="text-[9px] text-lcars-muted">→ {topOpportunity.recommended_route}</p>
              )}
            </div>
          )}

          {/* Recent conversions */}
          {recentRouted.length > 0 && (
            <div className="mt-1">
              <p className="text-[9px] uppercase tracking-[0.2em] text-status mb-1">Recent conversions</p>
              {recentRouted.map((n) => (
                <p key={n.id} className="text-[9px] text-lcars-muted/80 truncate">
                  ✓ {noteTitle(n)}{n.routed_entity_type ? ` → ${n.routed_entity_type.replace(/_/g, ' ')}` : ''}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CaptainsChairPage() {
  const { posture, isLoading } = useROSData();
  const { stats: missionStats, loading: missionStatsLoading } = useLiveMissionStats();
  const { data: engQueueData, loading: engQueueLoading } = useLiveEngineeringQueue();
  const { alerts: liveAlerts, isLoading: alertsLoading } = useAlerts();
  const { stats: briefingStats, loading: briefingLoading, operationalPicture } = useTodaysBriefing();
  const { events: timelineEvents, loading: timelineLoading } = useCaptainTimeline();
  const { summary: sinceLastSession, loading: sinceLastSessionLoading } = useSinceLastSession();

  const currentPosture: RecoveryPostureBand = posture.posture ?? 'UNKNOWN';

  return (
    <div className="flex gap-4">
      <div className="flex min-w-0 flex-1 flex-col gap-4">

        {/* WP A (MSN-0321): page had no title anywhere — the nav label was
            the only place a Captain ever saw this page's name. */}
        <h1 className="font-lcars text-lg font-bold uppercase tracking-wider text-lcars-text">
          Captain&apos;s Chair
        </h1>

        {/* ── MSN-0345: Since Last Session — first thing on the page, per
            Objective 3's "what changed since last session" ask. ── */}
        <SinceLastSessionPanel summary={sinceLastSession} loading={sinceLastSessionLoading} />

        {/* ── MSN-IOS-001 WP2: iPhone-first daily operating picture (mobile only) ── */}
        <MobileOperatingPicture />

        {/* ── D-055: Captain Capacity leads the page ── */}
        {!isLoading && (
          <CapacityHeadline
            posture={currentPosture}
            postureMessage={posture.posture_message ?? ''}
            capacityMessage={posture.capacity_message ?? ''}
          />
        )}

        {/* ── Recovery panels (live Supabase data via useROSData) ── */}
        <ROSPanels />

        {/* ── MSN-0335: renamed from "Proactive Signals" — investigation
            found the real duplicate with AlertsSidebar (blocked missions,
            pain-trend) was exactly 2 checks, now merged into alerts.ts as
            the one authoritative urgent-alert engine. What remains here
            (stalled >14d, review >48h, log-gap >3d, recovery-pulse-gap)
            is genuinely a different KIND of signal — operational hygiene
            reminders, not urgent "why now" alerts — so it's named and
            framed as that, not a second competing attention engine. ── */}
        <LCARSPanel title="Operational Hygiene" accent="command" eyebrow="Stalled, overdue, and quietly drifting — not urgent, worth a look">
          <ProactiveSignals />
        </LCARSPanel>

        {/* ── MSN-0329 Phase 5: Captain Intelligence (Cognitive Core),
            first production surface. Outside FleetStatusConditional —
            generation is an explicit Captain-triggered action, not
            passive info that should hide during REST/FRAGILE. ── */}
        <CaptainIntelligencePanel />

        {/* ── MSN-0345: Operational Picture — outside FleetStatusConditional,
            same reasoning as CaptainIntelligencePanel above: active risks are
            not the kind of secondary info that should hide during REST/FRAGILE. ── */}
        <OperationalPicture items={operationalPicture} loading={briefingLoading} />

        {/* ── Fleet section — collapses on FRAGILE/REST per D-055 ── */}
        <FleetStatusConditional posture={currentPosture}>
          <div className="grid gap-4 xl:grid-cols-2">
            <PriorityOverview
              decisionsCount={missionStats?.decisionsCount ?? 0}
              alertsCount={liveAlerts.length}
              activeMissionsCount={missionStats?.active ?? 0}
              loading={missionStatsLoading || alertsLoading}
            />
            <CaptainTimeline events={timelineEvents} loading={timelineLoading} />
          </div>
          <DepartmentRow />
          <MissionBoard stats={missionStats} loading={missionStatsLoading} />
          <div className="grid gap-4 md:grid-cols-3">
            <TodaysBriefing stats={briefingStats} loading={briefingLoading} />
            <EngineeringQueue data={engQueueData} loading={engQueueLoading} />
            <MedicalBayLink />
          </div>
          <NotebookWidget />
        </FleetStatusConditional>

      </div>

      <div className="hidden w-60 shrink-0 flex-col xl:flex">
        <AlertsSidebar alerts={liveAlerts} loading={alertsLoading} />
        {/* MSN-0305/WP A (MSN-0321): was DecisionsPanel — mock
            decisionsAwaitingApproval data, now a live count (see
            useLiveMissionStats above). CaptainApprovalQueue.tsx remains the
            one place a decision is actually actioned (approve/reject). */}
        <div className="mt-3">
          <CaptainApprovalQueue />
        </div>
      </div>
    </div>
  );
}
