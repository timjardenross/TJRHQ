import { StatusBadge } from '@/components/StatusBadge';
import { DEPARTMENTS, toneClasses } from '@/lib/departments';
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
  wellness
} from '@/lib/mockData';

export const metadata = { title: "Captain's Chair · LCARS Portal" };

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

function ActionLink({ children }: { children: React.ReactNode }) {
  return (
    <button className="text-[10px] uppercase tracking-[0.15em] text-command hover:text-command/70">
      {children}
    </button>
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
    { label: 'Reports Ready', sub: 'Awaiting review', count: 5, tone: 'science' as const }
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
              <span
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md ${dept.bg}`}
              >
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
      <div className="mt-3 text-right">
        <ActionLink>View All Priorities →</ActionLink>
      </div>
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
          const barColor =
            sys.value >= 95 ? 'bg-status' : sys.value >= 80 ? 'bg-command' : 'bg-operations';
          const textColor =
            sys.value >= 95
              ? 'text-status'
              : sys.value >= 80
                ? 'text-command'
                : 'text-operations';
          return (
            <li key={sys.label} className="flex items-center gap-3">
              <span className="w-36 shrink-0 text-[10px] uppercase tracking-wide text-lcars-muted">
                {sys.label}
              </span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-edge/60">
                <div
                  className={`h-full rounded-full ${barColor} transition-all`}
                  style={{ width: `${sys.value}%` }}
                />
              </div>
              <span className={`w-10 shrink-0 text-right font-mono text-xs font-bold ${textColor}`}>
                {sys.value}%
              </span>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 text-center text-[10px] font-bold uppercase tracking-[0.25em] text-status">
        No Active System Failures
      </p>
    </Panel>
  );
}

// ── Captain's Timeline ────────────────────────────────────────────────────────

function CaptainTimeline() {
  const STATUS = {
    completed: { text: 'text-status', dot: 'bg-status', glyph: '✓', sub: 'Completed' },
    in_progress: { text: 'text-command', dot: 'bg-command', glyph: '◎', sub: 'In Progress' },
    scheduled: { text: 'text-lcars-muted', dot: 'bg-edge', glyph: '○', sub: 'Scheduled' }
  };
  return (
    <Panel>
      <SectionHeader
        title="Captain's Timeline"
        action={<ActionLink>View Full Schedule</ActionLink>}
      />
      <ul className="flex flex-col gap-2">
        {captainTimeline.map((event) => {
          const s = STATUS[event.status];
          return (
            <li key={event.time} className="flex items-center gap-3">
              <span className="w-10 shrink-0 font-mono text-[11px] text-lcars-muted">
                {event.time}
              </span>
              <span className={`h-2 w-2 shrink-0 rounded-full ${s.dot}`} />
              <div className="min-w-0 flex-1">
                <p className={`text-[11px] font-medium ${s.text}`}>{event.title}</p>
                <p className="text-[10px] text-lcars-muted">{s.sub}</p>
              </div>
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
    critical: { dot: 'bg-operations', text: 'text-operations', priority: 'Critical Priority' },
    warning: { dot: 'bg-command', text: 'text-command', priority: 'High Priority' },
    info: { dot: 'bg-medical', text: 'text-medical', priority: 'Medium Priority' },
    nominal: { dot: 'bg-status', text: 'text-status', priority: 'Nominal' }
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
                  <p className={`mt-0.5 text-[10px] font-semibold ${s.text}`}>{s.priority}</p>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
      <button className="mt-3 w-full rounded border border-edge bg-panel-2/60 py-1.5 text-[10px] uppercase tracking-[0.2em] text-command hover:border-command/50">
        View All Alerts
      </button>
    </Panel>
  );
}

// ── Decisions Awaiting Approval ───────────────────────────────────────────────

function DecisionsPanel() {
  return (
    <Panel className="mt-3">
      <SectionHeader
        title="Decisions Awaiting Approval"
        action={<ActionLink>View All</ActionLink>}
      />
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
    <div
      className="grid gap-3 grid-cols-2 md:grid-cols-3"
      style={{ gridTemplateColumns: `repeat(${depts.length}, minmax(0, 1fr))` }}
    >
      {depts.map((dept) => {
        const theme = DEPARTMENTS[dept.key];
        return (
          <Panel key={dept.key}>
            <div className="mb-2 flex items-center gap-2">
              <span className={`h-6 w-6 shrink-0 rounded-md ${theme.bg}`} />
              <h3 className={`text-[11px] font-bold uppercase tracking-wider ${theme.text}`}>
                {dept.name}
              </h3>
            </div>
            <dl className="flex flex-col gap-1">
              {dept.metrics.map((m) => (
                <div key={m.label} className="flex items-center justify-between">
                  <dt className="text-[10px] uppercase tracking-wide text-lcars-muted">
                    {m.label}
                  </dt>
                  <dd className={`font-mono text-xs font-bold ${theme.text}`}>{m.value}</dd>
                </div>
              ))}
            </dl>
            <div className="mt-2">
              <StatusBadge label={dept.status} tone={dept.tone} />
            </div>
          </Panel>
        );
      })}
    </div>
  );
}

// ── Mission Board (Kanban) ────────────────────────────────────────────────────

function MissionBoard() {
  return (
    <Panel>
      <SectionHeader title="Mission Board" />
      <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${missionBoard.length}, minmax(0, 1fr))` }}>
        {missionBoard.map((col) => {
          const dept = DEPARTMENTS[col.tone];
          return (
            <div key={col.label} className="flex flex-col gap-1.5">
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
              <button className="mt-auto text-center text-[10px] uppercase tracking-[0.15em] text-lcars-muted hover:text-lcars-text">
                View All
              </button>
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
      <SectionHeader title="Today's Briefing" />
      <ul className="flex flex-col gap-2">
        {todaysBriefing.map((item) => {
          const c = toneClasses(item.tone);
          return (
            <li key={item.label} className="flex items-center justify-between gap-2">
              <span className="text-[10px] uppercase tracking-wide text-lcars-muted">
                {item.label}
              </span>
              <span className={`font-mono text-xs font-bold ${c.text}`}>{item.value}</span>
            </li>
          );
        })}
      </ul>
      <button className="mt-3 w-full rounded border border-edge bg-panel-2/60 py-1.5 text-[10px] uppercase tracking-[0.2em] text-command hover:border-command/50">
        View Full Brief
      </button>
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
                <span className="text-[10px] uppercase tracking-wide text-lcars-muted">
                  {item.label}
                </span>
              </div>
              <span className={`font-mono text-sm font-bold ${c.text}`}>{item.count}</span>
            </li>
          );
        })}
      </ul>
      <button className="mt-3 w-full rounded border border-edge bg-panel-2/60 py-1.5 text-[10px] uppercase tracking-[0.2em] text-engineering hover:border-engineering/50">
        View Full Queue
      </button>
    </Panel>
  );
}

// ── Health & Wellness ─────────────────────────────────────────────────────────

function HealthWellness() {
  return (
    <Panel>
      <SectionHeader title="Health & Wellness" />
      <ul className="flex flex-col gap-2">
        {wellness.slice(0, 4).map((m) => {
          const c = toneClasses(m.tone);
          const trendGlyph = { up: '▲', down: '▼', steady: '▬' }[m.trend];
          return (
            <li key={m.label} className="flex items-center justify-between gap-2">
              <span className="text-[10px] uppercase tracking-wide text-lcars-muted">
                {m.label}
              </span>
              <div className="flex items-center gap-1.5">
                <span className={`font-mono text-xs font-bold ${c.text}`}>{m.value}</span>
                <span className={`text-[10px] ${c.text}`}>{trendGlyph}</span>
              </div>
            </li>
          );
        })}
      </ul>
      <button className="mt-3 w-full rounded border border-edge bg-panel-2/60 py-1.5 text-[10px] uppercase tracking-[0.2em] text-medical hover:border-medical/50">
        View Medical Dashboard
      </button>
    </Panel>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CaptainsChairPage() {
  return (
    <div className="flex gap-4">
      {/* Main content */}
      <div className="flex min-w-0 flex-1 flex-col gap-4">
        {/* Row 1: Priority Overview | Ship Status | Timeline */}
        <div className="grid gap-4 xl:grid-cols-[1fr_1.6fr_1fr]">
          <PriorityOverview />
          <ShipStatus />
          <CaptainTimeline />
        </div>

        {/* Row 2: Department cards */}
        <DepartmentRow />

        {/* Row 3: Mission Board */}
        <MissionBoard />

        {/* Row 4: Today's Briefing + Engineering Queue + Health */}
        <div className="grid gap-4 md:grid-cols-3">
          <TodaysBriefing />
          <EngineeringQueue />
          <HealthWellness />
        </div>
      </div>

      {/* Right sidebar: Alerts + Decisions */}
      <div className="hidden w-60 shrink-0 flex-col xl:flex">
        <AlertsSidebar />
        <DecisionsPanel />
      </div>
    </div>
  );
}
