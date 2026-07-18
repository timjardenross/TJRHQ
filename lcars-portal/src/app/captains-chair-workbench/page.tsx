'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Shell } from '@/components/ui/workbench';
import { Badge } from '@/components/ui/Badge';
import { ROSPanels } from '@/components/ROSPanels';
import { MobileOperatingPicture } from '@/components/MobileOperatingPicture';
import { CaptainApprovalQueue } from '@/components/CaptainApprovalQueue';
import { CaptainIntelligencePanel } from '@/components/CaptainIntelligencePanel';
import ProactiveSignals from '@/components/ProactiveSignals';
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

interface TodaysBriefingStats {
  confidence: number | null;
  priorities: number;
  warnings: number;
  recommendations: number;
  nextActions: number;
}

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

// ── Workbench Shell Layout ──────────────────────────────────────────────────

export default function CaptainsChalrWorkbench() {
  const { posture: currentPosture, bodyContext } = useROSData();
  const { alerts: liveAlerts, loading: alertsLoading } = useAlerts();
  const { stats: missionStats, loading: missionStatsLoading } = useLiveMissionStats();
  const { data: engQueueData, loading: engQueueLoading } = useLiveEngineeringQueue();
  const { stats: briefingStats, loading: briefingLoading, operationalPicture } = useTodaysBriefing();
  const [summary, setSummary] = useState<SinceLastSessionSummary | null>(null);

  useEffect(() => {
    loadSinceLastSession().then(setSummary);
  }, []);

  const postureTone = currentPosture === 'STRONG' ? 'status' : currentPosture === 'STABLE' ? 'command' : 'operations';

  return (
    <Shell
      title="Captain's Chair"
      eyebrow="Operational Dashboard"
      back={{ href: '/workbenches', label: 'Workbenches' }}
    >
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

        {/* Operational Hygiene */}
        <div className="rounded-lg border border-wb-border bg-white p-4">
          <h3 className="mb-3 text-sm font-semibold text-wb-ink">Operational Hygiene</h3>
          <p className="mb-3 text-xs text-wb-ink2">Stalled, overdue, and quietly drifting — not urgent, worth a look</p>
          <ProactiveSignals />
        </div>

        {/* Operational Picture */}
        <div className="rounded-lg border border-wb-border bg-white p-4">
          <h3 className="mb-3 text-sm font-semibold text-wb-ink">Operational Picture</h3>
          <p className="mb-3 text-xs text-wb-ink2">Current incidents and emerging risks</p>
          {briefingLoading ? (
            <p className="text-xs text-wb-ink2 animate-pulse">Reading the operational picture…</p>
          ) : operationalPicture.length === 0 ? (
            <p className="text-xs text-wb-ink2">No active incidents or emerging risks.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {operationalPicture.map((item, i) => (
                <li key={item.event_id ?? i} className="rounded-md border border-wb-border/50 bg-wb-bg/50 p-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-[10px] uppercase tracking-wide text-wb-ink2">
                        {item.domain} · {item.event_type}
                      </p>
                      <p className="mt-0.5 text-xs text-wb-ink">{item.reason}</p>
                    </div>
                    {item.risk_score != null && (
                      <span className="shrink-0 font-mono text-[11px] font-bold text-wb-orange">
                        {Math.round(item.risk_score)}
                      </span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Fleet Section — Hidden on FRAGILE/REST */}
        {currentPosture !== 'FRAGILE' && currentPosture !== 'REST' && (
          <div className="space-y-4">
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
                <h3 className="mb-3 text-sm font-semibold text-wb-ink">Today's Briefing</h3>
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
                    {Object.entries(engQueueData).map(([status, count]) => (
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
                  <Link href="/missions" className="block text-xs text-wb-sage-deep hover:underline">
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
          </div>
        )}

        {/* Posture Warning */}
        {(currentPosture === 'FRAGILE' || currentPosture === 'REST') && (
          <div className="rounded-lg border border-wb-border bg-wb-bg p-4">
            <p className="text-sm text-wb-ink">
              Recovery posture is <Badge label={currentPosture} tone={postureTone} /> — operational detail is hidden. Focus on recovery and immediate priorities.
            </p>
          </div>
        )}
      </div>
    </Shell>
  );
}
