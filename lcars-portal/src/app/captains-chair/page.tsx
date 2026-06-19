'use client';

import Link from 'next/link';
import { StatusBadge } from '@/components/StatusBadge';
import { ROSPanels } from '@/components/ROSPanels';
import { DEPARTMENTS, toneClasses } from '@/lib/departments';
import { useROSData } from '@/lib/useROSData';
import {
  alerts,
  captainTimeline,
  decisionsAwaitingApproval,
  departments,
  engineeringQueueSummary,
  missionBoard,
  operatingPicture,
  shipSystemStatus,
  todaysBriefing,
} from '@/lib/mockData';
import type { RecoveryPostureBand } from '@/lib/types';

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

function PriorityOverview() {
  const items = [
    {
      label: 'Decisions Awaiting Approval',
      sub: 'Require your review',
      count: decisionsAwaitingApproval.length,
      tone: 'command' as const
    },
    {
      label: 'Alerts Requiring Attention',
      sub: 'High priority items',
      count: alerts.filter((a) => a.level !== 'nominal').length,
      tone: 'operations' as const
    },
    {
      label: 'Active Missions',
      sub: 'In progress across departments',
      count: operatingPicture.activeMissions,
      tone: 'medical' as const
    },
  ];
  return (
    <Panel>
      <SectionHeader title="Priority Overview" />
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
      <SectionHeader title="Ship Status" />
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
      <SectionHeader title="Captain's Timeline" />
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

function AlertsSidebar() {
  const active = alerts.filter((a) => a.level !== 'nominal');
  const LEVEL = {
    critical: { dot: 'bg-operations', text: 'text-operations' },
    warning:  { dot: 'bg-command',    text: 'text-command' },
    info:     { dot: 'bg-medical',    text: 'text-medical' },
    nominal:  { dot: 'bg-status',     text: 'text-status' }
  };
  return (
    <Panel>
      <SectionHeader
        title="Alerts"
        action={<span className="h-3 w-3 animate-pulse rounded-full bg-operations" />}
      />
      <ul className="flex flex-col gap-2">
        {active.map((a) => {
          const s = LEVEL[a.level];
          return (
            <li key={a.id} className="rounded-md border border-edge bg-panel-2/60 p-2">
              <div className="flex items-start gap-2">
                <span className={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${s.dot}`} />
                <div>
                  <p className={`text-[11px] font-bold uppercase ${s.text}`}>{a.title}</p>
                  <p className="text-[10px] text-lcars-muted">{a.detail}</p>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

// ── Decisions sidebar ─────────────────────────────────────────────────────────

function DecisionsPanel() {
  return (
    <Panel className="mt-3">
      <SectionHeader title="Decisions Awaiting Approval" />
      <ol className="flex flex-col gap-2">
        {decisionsAwaitingApproval.map((d) => (
          <li key={d.id} className="flex gap-2 rounded-md border border-edge bg-panel-2/60 p-2">
            <span className="shrink-0 font-mono text-xs font-bold text-command">{d.id}</span>
            <div className="min-w-0">
              <p className="text-[11px] font-semibold text-lcars-text">{d.title}</p>
              <p className="text-[10px] text-lcars-muted">{d.detail}</p>
            </div>
          </li>
        ))}
      </ol>
    </Panel>
  );
}

// ── Department Row ────────────────────────────────────────────────────────────

function DepartmentRow() {
  const depts = departments.filter((d) => d.key !== 'status');
  return (
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
  );
}

// ── Mission Board ─────────────────────────────────────────────────────────────

function MissionBoard() {
  return (
    <Panel>
      <SectionHeader
        title="Mission Board"
        action={
          <Link href="/missions" className="text-[10px] uppercase tracking-[0.15em] text-command hover:text-command/70">
            View All →
          </Link>
        }
      />
      <div className="overflow-x-auto">
        <div className="flex gap-2" style={{ minWidth: `${missionBoard.length * 160}px` }}>
          {missionBoard.map((col) => {
            const dept = DEPARTMENTS[col.tone];
            return (
              <div key={col.label} className="min-w-[160px] flex-1 flex flex-col gap-1.5">
                <div className="flex items-center justify-between rounded-md border border-edge bg-panel-2/80 px-2 py-1">
                  <span className="text-[10px] font-bold uppercase tracking-wide text-lcars-muted">
                    {col.label}
                  </span>
                  <span className={`font-mono text-xs font-bold ${dept.text}`}>{col.count}</span>
                </div>
                {col.items.map((item) => (
                  <div key={item.title} className="rounded border border-edge bg-space/50 p-1.5">
                    <p className="text-[11px] font-medium text-lcars-text">{item.title}</p>
                    <p className="text-[10px] text-lcars-muted">{item.meta}</p>
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      </div>
    </Panel>
  );
}

// ── Today's Briefing ──────────────────────────────────────────────────────────

function TodaysBriefing() {
  return (
    <Panel>
      <SectionHeader title="Today's Briefing" />
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

function EngineeringQueue() {
  return (
    <Panel>
      <SectionHeader title="Engineering Queue" />
      <ul className="flex flex-col gap-2">
        {engineeringQueueSummary.map((item) => {
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
        href="/engineering"
        className="mt-3 block w-full rounded border border-edge bg-panel-2/60 py-1.5 text-center text-[10px] uppercase tracking-[0.2em] text-engineering hover:border-engineering/50"
      >
        View Engineering →
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

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CaptainsChairPage() {
  const { posture, isLoading } = useROSData();

  const currentPosture: RecoveryPostureBand = posture.posture ?? 'UNKNOWN';

  return (
    <div className="flex gap-4">
      <div className="flex min-w-0 flex-1 flex-col gap-4">

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

        {/* ── Fleet section — collapses on FRAGILE/REST per D-055 ── */}
        <FleetStatusConditional posture={currentPosture}>
          <div className="grid gap-4 xl:grid-cols-[1fr_1.6fr_1fr]">
            <PriorityOverview />
            <ShipStatus />
            <CaptainTimeline />
          </div>
          <DepartmentRow />
          <MissionBoard />
          <div className="grid gap-4 md:grid-cols-3">
            <TodaysBriefing />
            <EngineeringQueue />
            <MedicalBayLink />
          </div>
        </FleetStatusConditional>

      </div>

      <div className="hidden w-60 shrink-0 flex-col xl:flex">
        <AlertsSidebar />
        <DecisionsPanel />
      </div>
    </div>
  );
}
