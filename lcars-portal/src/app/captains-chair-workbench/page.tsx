'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { WorkbenchShell } from '@/components/ui';
import { ROSPanels } from '@/components/ROSPanels';
import { MobileOperatingPicture } from '@/components/MobileOperatingPicture';
import { CaptainApprovalQueue } from '@/components/CaptainApprovalQueue';
import { CaptainIntelligencePanel } from '@/components/CaptainIntelligencePanel';
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

const ALERT_SEVERITY_BORDER: Record<AlertSeverity, string> = {
  critical: 'border-state-crit',
  high: 'border-state-crit',
  warning: 'border-state-warn',
};
import { departments } from '@/lib/mockData';
import type { RecoveryPostureBand, StateTone } from '@/lib/types';

// ── All data hooks preserved from legacy /captains-chair ──────────────────────

interface LiveMissionStats {
  total: number;
  active: number;
  in_progress: number;
  blocked: number;
  completed: number;
  decisionsCount: number;
}

function useLiveMissionStats(): { stats: LiveMissionStats | null; loading: boolean; error: string | null } {
  const [stats, setStats] = useState<LiveMissionStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const supabase = createSupabaseBrowserClient();
        const { data, error: fetchError } = await supabase.from('missions').select('status');
        if (cancelled) return;
        if (fetchError) throw fetchError;
        if (!data) return;
        setStats({
          total: data.length,
          active: data.filter((m) => ACTIVE_STATUSES.includes(m.status)).length,
          in_progress: data.filter((m) => m.status === 'Implemented' || m.status === 'Tested').length,
          blocked: data.filter((m) => m.status === 'Blocked').length,
          completed: data.filter((m) => COMPLETED_STATUSES.includes(m.status)).length,
          decisionsCount: data.filter((m) => AWAITING_CAPTAIN_STATUSES.includes(m.status)).length,
        });
        // A failed request previously left stats null with no error state —
        // panels silently rendered 0/"No data", indistinguishable from a
        // real quiet day. Every other workbench surfaces fetch failures via
        // an explicit wb-crit banner; this brings Captain's Chair in line.
        setError(null);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load mission stats');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  return { stats, loading, error };
}

function useLiveEngineeringQueue(): { data: EngineeringQueueData | null; loading: boolean; error: string | null } {
  const [data, setData] = useState<EngineeringQueueData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchEngineeringQueue()
      .then((d) => { if (!cancelled) { setData(d); setError(null); } })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load engineering queue'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return { data, loading, error };
}

interface TodaysBriefingStats {
  confidence: number | null;
  priorities: number;
  warnings: number;
  recommendations: number;
  nextActions: number;
}

function useTodaysBriefing(): {
  stats: TodaysBriefingStats | null;
  loading: boolean;
  error: string | null;
} {
  const [stats, setStats] = useState<TodaysBriefingStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/captain-brief')
      .then((r) => {
        if (!r.ok) throw new Error(`Captain's brief unavailable (${r.status})`);
        return r.json();
      })
      .then((doc) => {
        if (cancelled || !doc) return;
        setStats({
          confidence: doc.confidence ?? null,
          priorities: doc.priorities?.length ?? 0,
          warnings: doc.warnings?.length ?? 0,
          recommendations: doc.recommendations?.length ?? 0,
          nextActions: doc.next_actions?.length ?? 0,
        });
        setError(null);
      })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load briefing'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return { stats, loading, error };
}

// Ported from legacy (app)/captains-chair (MSN-0345): real today's Event Bus
// activity (core_events), same table 12+ real emit-points across the
// platform already write to.
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

// Ported from legacy (app)/captains-chair (EXEC-010B WP9).
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

function NotebookCard() {
  const [readyCount, setReadyCount] = useState<number | null>(null);
  const [capturedCount, setCapturedCount] = useState<number | null>(null);
  const [topOpportunity, setTopOpportunity] = useState<NbNote | null>(null);
  const [recentRouted, setRecentRouted] = useState<NbNote[]>([]);

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
        setRecentRouted(routed.slice(0, 3) as NbNote[]);
      });
  }, []);

  const hasAction = (readyCount ?? 0) > 0;

  function noteTitle(n: NbNote) {
    return n.title || n.raw_content.slice(0, 48) + (n.raw_content.length > 48 ? '…' : '');
  }

  return (
    <div className={`rounded-lg border bg-white p-4 ${hasAction ? 'border-wb-sage-deep/40' : 'border-wb-border'}`}>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-wb-ink">Captain&apos;s Notebook</h3>
        <Link href="/captains-notebook" className="text-[10px] uppercase tracking-[0.15em] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
          Open →
        </Link>
      </div>
      {readyCount === null ? (
        <p className="text-xs text-wb-ink2 animate-pulse">Loading…</p>
      ) : (
        <div className="space-y-2 text-xs">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className={`h-2 w-2 shrink-0 rounded-full ${hasAction ? 'bg-wb-sage-deep animate-pulse' : 'bg-wb-border'}`} />
              <span className="text-wb-ink2">Ready for routing</span>
            </div>
            <span className={`font-mono font-semibold ${hasAction ? 'text-wb-sage-deep' : 'text-wb-ink2'}`}>{readyCount}</span>
          </div>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 shrink-0 rounded-full bg-wb-border" />
              <span className="text-wb-ink2">Pending triage</span>
            </div>
            <span className="font-mono font-semibold text-wb-ink2">{capturedCount}</span>
          </div>

          {topOpportunity && (
            <div className="mt-1 rounded border border-wb-sage-deep/20 bg-wb-sage-deep/5 px-2 py-1.5">
              <p className="mb-0.5 text-[9px] uppercase tracking-[0.2em] text-wb-sage-deep">Top opportunity</p>
              <p className="truncate text-wb-ink">{noteTitle(topOpportunity)}</p>
              {topOpportunity.recommended_route && (
                <p className="text-[10px] text-wb-ink2">→ {topOpportunity.recommended_route}</p>
              )}
            </div>
          )}

          {recentRouted.length > 0 && (
            <div className="mt-1">
              <p className="mb-1 text-[9px] uppercase tracking-[0.2em] text-wb-ink2">Recent conversions</p>
              {recentRouted.map((n) => (
                <p key={n.id} className="truncate text-[10px] text-wb-ink2/80">
                  ✓ {noteTitle(n)}{n.routed_entity_type ? ` → ${n.routed_entity_type.replace(/_/g, ' ')}` : ''}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Ported from legacy (app)/captains-chair (MSN-0345). See lib/sinceLastSession.ts's
// own header for exactly what this can and can't answer honestly.
function SinceLastSessionCard({ summary, loading }: { summary: SinceLastSessionSummary | null; loading: boolean }) {
  if (loading || !summary) return null;
  if (summary.firstSession) {
    return (
      <div className="rounded-lg border border-wb-border bg-white p-4">
        <h3 className="mb-1 text-sm font-semibold text-wb-ink">Since Last Session</h3>
        <p className="text-xs text-wb-ink2">First session on this browser — nothing to compare against yet.</p>
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-wb-border bg-white p-4">
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-wb-ink">Since Last Session</h3>
        <span className="text-[10px] uppercase tracking-wide text-wb-ink2">
          Since {new Date(summary.previousSessionAt!).toLocaleString()}
        </span>
      </div>
      {summary.eventCount === 0 ? (
        <p className="text-xs text-wb-ink2">Nothing new since your last visit.</p>
      ) : (
        <div className="flex flex-col gap-2">
          <p className="text-sm text-wb-ink">
            <span className="font-mono font-bold text-wb-sage-deep">{summary.eventCount}</span> event
            {summary.eventCount === 1 ? '' : 's'} across the platform since your last visit.
          </p>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] uppercase tracking-wide text-wb-ink2">
            {summary.byDomain.map((d) => (
              <span key={d.domain}>{d.domain} · {d.count}</span>
            ))}
          </div>
        </div>
      )}
      <p className="mt-2 text-[10px] text-wb-ink2/70">
        Answers &quot;what changed.&quot; What completed, worsened, was delegated, or was learned
        aren&apos;t yet trackable — no data source for those exists in the platform today.
      </p>
    </div>
  );
}

// ── Workbench Shell Layout ──────────────────────────────────────────────────

export default function CaptainsChairWorkbench() {
  const { posture: currentPosture } = useROSData();
  const { alerts: liveAlerts, isLoading: alertsLoading } = useAlerts();
  const { stats: missionStats, loading: missionStatsLoading, error: missionStatsError } = useLiveMissionStats();
  const { data: engQueueData, loading: engQueueLoading, error: engQueueError } = useLiveEngineeringQueue();
  const { stats: briefingStats, loading: briefingLoading, error: briefingError } = useTodaysBriefing();
  const { events: timelineEvents, loading: timelineLoading } = useCaptainTimeline();
  const dataErrors = [missionStatsError, engQueueError, briefingError].filter(Boolean) as string[];
  const [summary, setSummary] = useState<SinceLastSessionSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    loadSinceLastSession()
      .then((s) => { if (!cancelled) setSummary(s); })
      .finally(() => { if (!cancelled) setSummaryLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const postureBand = currentPosture.posture;

  return (
    <WorkbenchShell
      title="Captain's Chair"
      eyebrow="Operational Dashboard"
      tagline="USS TJR · Captain's Chair · Operational Dashboard"
      back={{ href: '/workbenches', label: 'Workbenches' }}
    >
      {dataErrors.length > 0 && (
        <p className="mb-4 rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">
          {dataErrors.length === 1 ? dataErrors[0] : `${dataErrors.length} panels failed to load: ${dataErrors.join('; ')}`}
        </p>
      )}
      {/* ── Always-visible panels ── */}
      <div className="space-y-4">
        {/* Since Last Session — ported from legacy (app)/captains-chair
            (MSN-0345). Was fetched (loadSinceLastSession()) but never
            rendered here; the state existed but was dead. */}
        <SinceLastSessionCard summary={summary} loading={summaryLoading} />

        {/* Recovery Posture — desktop hidden below lg to avoid rendering both
            ROSPanels' full desktop stack AND MobileOperatingPicture's mobile
            stack simultaneously on the same viewport (was doubling scroll
            length exactly where the 2026-08-09 mobile review's collapsed-
            <details> fix below was trying to reduce it). No outer card
            wrapper — WorkbenchPanel already supplies its own card chrome per
            panel; wrapping it again was card-in-card with no purpose. */}
        <div className="hidden lg:block"><ROSPanels /></div>
        <MobileOperatingPicture />

        {/* Captain Intelligence — WorkbenchPanel supplies its own chrome. */}
        <CaptainIntelligencePanel />

        {/* Fleet Section — Hidden on FRAGILE/REST.
            2026-08-09 mobile/iPad review (P1): this is ~8 panels deep on
            top of the 4 always-visible ones above — a very long single-
            column scroll on a phone. The full hierarchy rework (hero zone
            + collapsed-by-default secondary section) is still deferred
            per the Captain's own call to review this page separately.
            This is a narrower, lower-risk mobile-only fix in the meantime:
            a native <details> disclosure, open by default (desktop and
            first-load mobile both see exactly today's layout, zero
            behavioural change), with a <summary> toggle that only renders
            below lg — so a mobile user who's already seen "what needs me"
            gets a real way to collapse the rest without scrolling past it
            every time, while lg+ never even renders the toggle and always
            shows the content open (browsers render <details open> content
            regardless of viewport, so hiding the summary doesn't hide the
            content at any breakpoint). No JS state, no hydration risk. */}
        {postureBand !== 'FRAGILE' && postureBand !== 'REST' && (
          <details open className="group space-y-4">
            <summary className="mb-1 flex cursor-pointer list-none items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-wb-ink2 lg:hidden">
              <span className="transition group-open:rotate-90">▶</span>
              Operational detail
            </summary>
            {/* Mission Overview */}
            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-lg border border-wb-border bg-white p-5">
                <h3 className="mb-3 text-sm font-semibold text-wb-ink">Priority Overview</h3>
                {missionStatsLoading ? (
                  <p className="text-xs text-wb-ink2 animate-pulse">Loading…</p>
                ) : (
                  <div className="space-y-2 text-xs">
                    <div className="flex justify-between">
                      <span className="text-wb-ink2">Decisions awaiting approval</span>
                      <span className="font-semibold text-wb-ink">{missionStats?.decisionsCount ?? 0}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-wb-ink2">Live alerts</span>
                      <span className="font-semibold text-wb-ink">{liveAlerts.length}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-wb-ink2">Active missions</span>
                      <span className="font-semibold text-wb-ink">{missionStats?.active ?? 0}</span>
                    </div>
                  </div>
                )}
              </div>

              {/* Mission Board */}
              <div className="rounded-lg border border-wb-border bg-white p-4">
                <h3 className="mb-3 text-sm font-semibold text-wb-ink">Mission Status</h3>
                {missionStatsLoading ? (
                  <p className="text-xs text-wb-ink2 animate-pulse">Loading…</p>
                ) : (
                  <div className="space-y-2 text-xs">
                    <div className="flex justify-between">
                      <span className="text-wb-ink2">Total</span>
                      <span className="font-semibold text-wb-ink">{missionStats?.total ?? 0}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-wb-ink2">In Progress</span>
                      <span className="font-semibold text-wb-ink">{missionStats?.in_progress ?? 0}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-wb-ink2">Blocked</span>
                      <span className="font-semibold text-wb-ink">{missionStats?.blocked ?? 0}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-wb-ink2">Completed</span>
                      <span className="font-semibold text-wb-ink">{missionStats?.completed ?? 0}</span>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Departments — ported from legacy (app)/captains-chair (MSN-0345).
                Names/links are real (route to real live pages); no per-dept
                metric values, same as legacy — building a real cross-domain
                metrics query was out of that mission's scope. */}
            <div className="rounded-lg border border-wb-border bg-white p-4">
              <h3 className="mb-3 text-sm font-semibold text-wb-ink">Departments</h3>
              <div className="overflow-x-auto">
                <div className="flex gap-3" style={{ minWidth: `${departments.filter((d) => d.key !== 'status').length * 140}px` }}>
                  {departments.filter((d) => d.key !== 'status').map((dept) => {
                    const theme = DEPARTMENTS[dept.key];
                    return (
                      <Link key={dept.key} href={`/${dept.key}`} className="block min-w-[140px] flex-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
                        <div className="flex items-center gap-2 rounded-md border border-wb-border bg-wb-bg p-2.5 transition-colors hover:border-wb-sage-deep/60">
                          <span className={`h-4 w-4 shrink-0 rounded ${theme.bg} ring-1 ring-inset ring-black/25`} />
                          <span className={`text-[10px] font-semibold uppercase tracking-wide ${theme.text}`}>{dept.name}</span>
                        </div>
                      </Link>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Captain's Timeline & Captain's Notebook — ported from legacy
                (app)/captains-chair (MSN-0345 / EXEC-010B WP9). */}
            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-lg border border-wb-border bg-white p-4">
                <h3 className="mb-3 text-sm font-semibold text-wb-ink">Captain&apos;s Timeline</h3>
                {timelineLoading ? (
                  <p className="text-xs text-wb-ink2 animate-pulse">Loading…</p>
                ) : timelineEvents.length === 0 ? (
                  <p className="text-xs text-wb-ink2">No events logged yet today.</p>
                ) : (
                  <ul className="space-y-2">
                    {timelineEvents.map((event) => (
                      <li key={event.id} className="flex items-center gap-2 text-xs">
                        <span className="w-10 shrink-0 font-mono text-wb-ink2">{event.time}</span>
                        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-wb-sage-deep" />
                        <span className="text-wb-ink">{event.title}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <NotebookCard />
            </div>

            {/* Today's Briefing & Engineering Queue */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              <div className="rounded-lg border border-wb-border bg-white p-4">
                <h3 className="mb-3 text-sm font-semibold text-wb-ink">Today&apos;s Briefing</h3>
                {briefingLoading ? (
                  <p className="text-xs text-wb-ink2 animate-pulse">Loading…</p>
                ) : (
                  <div className="space-y-2 text-xs">
                    <div className="flex justify-between">
                      <span className="text-wb-ink2">Confidence</span>
                      <span className="font-semibold text-wb-ink">{briefingStats?.confidence != null ? `${briefingStats.confidence}%` : '—'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-wb-ink2">Priorities</span>
                      <span className="font-semibold text-wb-ink">{briefingStats?.priorities ?? 0}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-wb-ink2">Warnings</span>
                      <span className="font-semibold text-wb-ink">{briefingStats?.warnings ?? 0}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-wb-ink2">Recommendations</span>
                      <span className="font-semibold text-wb-ink">{briefingStats?.recommendations ?? 0}</span>
                    </div>
                  </div>
                )}
              </div>

              <div className="rounded-lg border border-wb-border bg-white p-4">
                <h3 className="mb-3 text-sm font-semibold text-wb-ink">Engineering Queue</h3>
                {engQueueLoading ? (
                  <p className="text-xs text-wb-ink2 animate-pulse">Loading…</p>
                ) : engQueueData ? (
                  <div className="space-y-2 text-xs">
                    {[...LIFECYCLE_ORDER, 'rejected' as const].map((status) => {
                      const c = toneClasses(LIFECYCLE_TONE[status]);
                      return (
                        <div key={status} className="flex justify-between">
                          <span className={c.text}>{LIFECYCLE_LABEL[status]}</span>
                          <span className="font-semibold text-wb-ink">{engQueueData.counts[status] ?? 0}</span>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-xs text-wb-ink2">No data</p>
                )}
              </div>

              <div className="rounded-lg border border-wb-border bg-white p-3">
                <h3 className="mb-3 text-sm font-semibold text-wb-ink">Quick Links</h3>
                <div className="space-y-2">
                  <Link href="/human-systems-workbench" className="block text-xs text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
                    → Medical Bay
                  </Link>
                  <Link href="/mission-workbench" className="block text-xs text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
                    → Mission Registry
                  </Link>
                  <Link href="/captains-brief-workbench" className="block text-xs text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
                    → Full Brief
                  </Link>
                </div>
              </div>
            </div>

            {/* Alerts & Approval Queue */}
            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-lg border border-wb-border bg-white p-4">
                <h3 className="mb-3 text-sm font-semibold text-wb-ink">Live Alerts</h3>
                {alertsLoading ? (
                  <p className="text-xs text-wb-ink2 animate-pulse">Loading…</p>
                ) : liveAlerts.length === 0 ? (
                  <p className="text-xs text-wb-ink2">No alerts.</p>
                ) : (
                  <ul className="space-y-2">
                    {liveAlerts.slice(0, 5).map((alert) => (
                      <li key={alert.id} className={`border-l-2 ${ALERT_SEVERITY_BORDER[alert.severity]} pl-2 text-xs`}>
                        <p className="font-semibold text-wb-ink">{alert.title}</p>
                        <p className="text-wb-ink2">{alert.detail}</p>
                      </li>
                    ))}
                    {liveAlerts.length > 5 && (
                      <p className="text-xs text-wb-ink2">+{liveAlerts.length - 5} more</p>
                    )}
                  </ul>
                )}
              </div>

              <div className="rounded-lg border border-wb-border bg-white p-5">
                <h3 className="mb-3 text-sm font-semibold text-wb-ink">Approvals Pending</h3>
                <CaptainApprovalQueue />
              </div>
            </div>
          </details>
        )}

        {/* Operational-detail-hidden note. 2026-08-09's own note above this
            box explains WHY the Fleet section is collapsed on FRAGILE/REST;
            this used to also restate "Recovery posture is X" via its own
            StatusBadge — the 3rd/4th time that band appeared on this page
            (Recovery Posture panel above already shows it, prominently,
            with real severity colour). Now just explains the hiding, colour
            matched to severity (wb-warn/wb-crit) instead of a neutral box
            that didn't read as a warning at all. */}
        {(postureBand === 'FRAGILE' || postureBand === 'REST') && (
          <div
            className={
              postureBand === 'REST'
                ? 'rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-4'
                : 'rounded-lg border border-wb-warn/40 bg-wb-warn/10 p-4'
            }
          >
            <p className={postureBand === 'REST' ? 'text-sm text-wb-crit-on' : 'text-sm text-wb-warn-on'}>
              Operational detail is hidden while recovery posture is low — see Recovery Posture above. Focus on recovery and immediate priorities.
            </p>
          </div>
        )}
      </div>
    </WorkbenchShell>
  );
}
