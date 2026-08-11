'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { WorkbenchShell } from '@/components/ui';
import { ROSPanels } from '@/components/ROSPanels';
import { MobileOperatingPicture } from '@/components/MobileOperatingPicture';
import { CaptainApprovalQueue } from '@/components/CaptainApprovalQueue';
import { CaptainIntelligencePanel } from '@/components/CaptainIntelligencePanel';
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
<<<<<<< HEAD
  operationalPicture: OperationalPictureItem[];
=======
>>>>>>> 3f9972f3d831aafb30298d1ef6b714751063906b
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
<<<<<<< HEAD
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
=======
>>>>>>> 3f9972f3d831aafb30298d1ef6b714751063906b
        setError(null);
      })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load briefing'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

<<<<<<< HEAD
  return { stats, loading, operationalPicture, error };
=======
  return { stats, loading, error };
>>>>>>> 3f9972f3d831aafb30298d1ef6b714751063906b
}

// ── Workbench Shell Layout ──────────────────────────────────────────────────

export default function CaptainsChairWorkbench() {
  const { posture: currentPosture, bodyContext } = useROSData();
  const { alerts: liveAlerts, isLoading: alertsLoading } = useAlerts();
  const { stats: missionStats, loading: missionStatsLoading, error: missionStatsError } = useLiveMissionStats();
  const { data: engQueueData, loading: engQueueLoading, error: engQueueError } = useLiveEngineeringQueue();
<<<<<<< HEAD
  const { stats: briefingStats, loading: briefingLoading, operationalPicture, error: briefingError } = useTodaysBriefing();
=======
  const { stats: briefingStats, loading: briefingLoading, error: briefingError } = useTodaysBriefing();
>>>>>>> 3f9972f3d831aafb30298d1ef6b714751063906b
  const dataErrors = [missionStatsError, engQueueError, briefingError].filter(Boolean) as string[];
  const [summary, setSummary] = useState<SinceLastSessionSummary | null>(null);

  useEffect(() => {
    loadSinceLastSession().then(setSummary);
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
        {/* Recovery Posture */}
        <div className="rounded-lg border border-wb-border bg-white p-4">
          <ROSPanels />
          <MobileOperatingPicture />
        </div>

        {/* Captain Intelligence */}
        <div className="rounded-lg border border-wb-border bg-white p-4">
          <CaptainIntelligencePanel />
        </div>

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
              <div className="rounded-lg border border-wb-border bg-white p-4">
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
                      <span className="font-semibold text-wb-ink">{briefingStats?.confidence ? Math.round(briefingStats.confidence * 100) + '%' : '—'}</span>
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
                    {Object.entries(engQueueData.counts).map(([status, count]) => (
                      <div key={status} className="flex justify-between">
                        <span className="text-wb-ink2">{LIFECYCLE_LABEL[status as keyof typeof LIFECYCLE_LABEL] || status}</span>
                        <span className="font-semibold text-wb-ink">{count as number}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-wb-ink2">No data</p>
                )}
              </div>

              <div className="rounded-lg border border-wb-border bg-white p-4">
                <h3 className="mb-3 text-sm font-semibold text-wb-ink">Quick Links</h3>
                <div className="space-y-2">
                  <Link href="/human-systems-workbench" className="block text-xs text-wb-sage-deep hover:underline">
                    → Medical Bay
                  </Link>
                  <Link href="/mission-workbench" className="block text-xs text-wb-sage-deep hover:underline">
                    → Mission Registry
                  </Link>
                  <Link href="/captains-brief-workbench" className="block text-xs text-wb-sage-deep hover:underline">
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
                      <li key={alert.id} className="border-l-2 border-wb-orange pl-2 text-xs">
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

              <div className="rounded-lg border border-wb-border bg-white p-4">
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
