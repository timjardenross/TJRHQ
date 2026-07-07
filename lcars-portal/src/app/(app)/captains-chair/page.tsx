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
import { ACTIVE_STATUSES, COMPLETED_STATUSES, AWAITING_CAPTAIN_STATUSES } from '@/lib/missionStatus';
import {
  fetchEngineeringQueue,
  LIFECYCLE_ORDER,
  LIFECYCLE_LABEL,
  LIFECYCLE_TONE,
  type EngineeringQueueData,
} from '@/lib/engineering-queue';
import type { AlertSeverity } from '@/lib/alerts';
import {
  captainTimeline,
  departments,
  shipSystemStatus,
  todaysBriefing,
} from '@/lib/mockData';
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

function ShipStatus() {
  return (
    <Panel>
      <SectionHeader
        title="Ship Status"
        action={<DataSourceIndicator live={false} mockLabel="Preview Data" variant="inline" />}
      />
      <ul className="flex flex-col gap-2.5">
        {shipSystemStatus.map((sys) => {
          const barColor = sys.value >= 95 ? 'bg-status' : sys.value >= 80 ? 'bg-command' : 'bg-operations';
          const textColor = sys.value >= 95 ? 'text-status' : sys.value >= 80 ? 'text-command' : 'text-operations';
          return (
            <li key={sys.label} className="flex items-center gap-3">
              <span className="w-36 shrink-0 text-[10px] uppercase tracking-wide text-lcars-muted">
                {sys.label}
              </span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-edge/60">
                <div className={`h-full rounded-full ${barColor} transition-all`} style={{ width: `${sys.value}%` }} />
              </div>
              <span className={`w-10 shrink-0 text-right font-mono text-xs font-bold ${textColor}`}>
                {sys.value}%
              </span>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

// ── Captain's Timeline ────────────────────────────────────────────────────────

function CaptainTimeline() {
  const STATUS = {
    completed:   { text: 'text-status',      dot: 'bg-status',  glyph: '✓' },
    in_progress: { text: 'text-command',     dot: 'bg-command', glyph: '◎' },
    scheduled:   { text: 'text-lcars-muted', dot: 'bg-edge',    glyph: '○' }
  };
  return (
    <Panel>
      <SectionHeader
        title="Captain's Timeline"
        action={<DataSourceIndicator live={false} mockLabel="Preview Data" variant="inline" />}
      />
      <ul className="flex flex-col gap-2">
        {captainTimeline.map((event) => {
          const s = STATUS[event.status];
          return (
            <li key={event.time} className="flex items-center gap-3">
              <span className="w-10 shrink-0 font-mono text-[11px] text-lcars-muted">{event.time}</span>
              <span className={`h-2 w-2 shrink-0 rounded-full ${s.dot}`} />
              <p className={`flex-1 text-[11px] font-medium ${s.text}`}>{event.title}</p>
              <span className={`shrink-0 text-sm ${s.text}`}>{s.glyph}</span>
            </li>
          );
        })}
      </ul>
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

function DepartmentRow() {
  const depts = departments.filter((d) => d.key !== 'status');
  return (
    <div>
      <SectionHeader
        title="Departments"
        action={<DataSourceIndicator live={false} mockLabel="Preview Data" variant="inline" />}
      />
      <div className="overflow-x-auto">
      <div className="flex gap-3" style={{ minWidth: `${depts.length * 160}px` }}>
        {depts.map((dept) => {
          const theme = DEPARTMENTS[dept.key];
          return (
            <Link key={dept.key} href={`/${dept.key}`} className="block min-w-[160px] flex-1">
              <div className="rounded-lcars border border-edge bg-panel/60 p-3 hover:border-command/60 transition-colors h-full">
                <div className="mb-2 flex items-center gap-2">
                  <span className={`h-5 w-5 shrink-0 rounded-md ${theme.bg}`} />
                  <h3 className={`text-[10px] font-bold uppercase tracking-wider ${theme.text}`}>
                    {dept.name}
                  </h3>
                </div>
                <dl className="flex flex-col gap-1">
                  {dept.metrics.map((m) => (
                    <div key={m.label} className="flex items-center justify-between">
                      <dt className="text-[10px] uppercase tracking-wide text-lcars-muted">{m.label}</dt>
                      <dd className={`font-mono text-xs font-bold ${theme.text}`}>{m.value}</dd>
                    </div>
                  ))}
                </dl>
                <div className="mt-2">
                  <StatusBadge label={dept.status} tone={dept.tone} />
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

function TodaysBriefing() {
  return (
    <Panel>
      <SectionHeader
        title="Today's Briefing"
        action={<DataSourceIndicator live={false} mockLabel="Preview Data" variant="inline" />}
      />
      <ul className="flex flex-col gap-2">
        {todaysBriefing.map((item) => {
          const c = toneClasses(item.tone);
          return (
            <li key={item.label} className="flex items-center justify-between gap-2">
              <span className="text-[10px] uppercase tracking-wide text-lcars-muted">{item.label}</span>
              <span className={`font-mono text-xs font-bold ${c.text}`}>{item.value}</span>
            </li>
          );
        })}
      </ul>
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

  const currentPosture: RecoveryPostureBand = posture.posture ?? 'UNKNOWN';

  return (
    <div className="flex gap-4">
      <div className="flex min-w-0 flex-1 flex-col gap-4">

        {/* WP A (MSN-0321): page had no title anywhere — the nav label was
            the only place a Captain ever saw this page's name. */}
        <h1 className="font-lcars text-lg font-bold uppercase tracking-wider text-lcars-text">
          Captain&apos;s Chair
        </h1>

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

        {/* ── Fleet section — collapses on FRAGILE/REST per D-055 ── */}
        <FleetStatusConditional posture={currentPosture}>
          <div className="grid gap-4 xl:grid-cols-[1fr_1.6fr_1fr]">
            <PriorityOverview
              decisionsCount={missionStats?.decisionsCount ?? 0}
              alertsCount={liveAlerts.length}
              activeMissionsCount={missionStats?.active ?? 0}
              loading={missionStatsLoading || alertsLoading}
            />
            <ShipStatus />
            <CaptainTimeline />
          </div>
          <DepartmentRow />
          <MissionBoard stats={missionStats} loading={missionStatsLoading} />
          <div className="grid gap-4 md:grid-cols-3">
            <TodaysBriefing />
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
