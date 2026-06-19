import { StatusBadge } from '@/components/StatusBadge';
import { MissionCard } from '@/components/MissionCard';
import { DEPARTMENTS, toneClasses } from '@/lib/departments';
import {
  commandCalendar,
  commandReadiness,
  communications,
  crew,
  decisionsAwaitingApproval,
  deptCrewCounts,
  missions
} from '@/lib/mockData';

export const metadata = { title: 'Number One — XO Command · LCARS Portal' };

// ── Shared primitives ─────────────────────────────────────────────────────────

function Panel({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-lcars border border-edge bg-panel/60 p-3 ${className}`}>
      {children}
    </div>
  );
}

function SectionHeader({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="text-[11px] font-bold uppercase tracking-[0.25em] text-lcars-muted">{title}</h2>
      {action}
    </div>
  );
}

// ── Stats header ──────────────────────────────────────────────────────────────

function CommandStats() {
  return (
    <Panel>
      <div className="flex flex-wrap items-center gap-0 divide-x divide-edge">
        <div className="flex flex-col pr-6">
          <span className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">Command Readiness</span>
          <span className="font-lcars text-2xl font-bold leading-none text-status mt-0.5">
            {commandReadiness.readiness}%
          </span>
        </div>
        <div className="flex flex-col px-6">
          <span className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">Decisions Pending</span>
          <span className="font-lcars text-2xl font-bold leading-none text-command mt-0.5">
            {commandReadiness.decisionsPending}
          </span>
        </div>
        <div className="flex flex-col pl-6">
          <span className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">Crew Status</span>
          <span className="font-lcars text-2xl font-bold leading-none text-status mt-0.5">
            {commandReadiness.crewStatus}
          </span>
        </div>
      </div>
    </Panel>
  );
}

// ── Command Overview (decisions) ──────────────────────────────────────────────

function CommandOverview() {
  return (
    <Panel>
      <SectionHeader title="Command Overview" action={
        <span className="text-[10px] uppercase tracking-[0.1em] text-lcars-muted">
          Awaiting Your Review
        </span>
      } />
      <ol className="flex flex-col gap-2">
        {decisionsAwaitingApproval.map((d) => (
          <li key={d.id} className="flex gap-3 rounded-md border border-edge bg-panel-2/60 p-2.5">
            <span className="shrink-0 font-mono text-xs font-bold text-command">{d.id}</span>
            <div className="min-w-0">
              <p className="text-[11px] font-semibold text-lcars-text">{d.title}</p>
              <p className="text-[10px] text-lcars-muted">{d.detail}</p>
              <p className="mt-0.5 text-[10px] text-science">From: {d.from}</p>
            </div>
          </li>
        ))}
      </ol>
      <button className="mt-3 w-full rounded border border-edge bg-panel-2/60 py-1.5 text-[10px] uppercase tracking-[0.2em] text-command hover:border-command/50">
        View All Decisions
      </button>
    </Panel>
  );
}

// ── Command Calendar ──────────────────────────────────────────────────────────

function CommandCalendar() {
  const STATUS = {
    completed:   { text: 'text-status',      dot: 'bg-status',  glyph: '✓' },
    in_progress: { text: 'text-command',     dot: 'bg-command', glyph: '◎' },
    scheduled:   { text: 'text-lcars-muted', dot: 'bg-edge',    glyph: '○' }
  };
  return (
    <Panel>
      <SectionHeader title="Command Calendar" action={
        <button className="text-[10px] uppercase tracking-[0.15em] text-command hover:text-command/70">
          View Full Schedule
        </button>
      } />
      <ul className="flex flex-col gap-2">
        {commandCalendar.map((ev) => {
          const s = STATUS[ev.status];
          return (
            <li key={ev.time} className="flex items-center gap-3">
              <span className="w-10 shrink-0 font-mono text-[11px] text-lcars-muted">{ev.time}</span>
              <span className={`h-2 w-2 shrink-0 rounded-full ${s.dot}`} />
              <p className={`flex-1 text-[11px] font-medium ${s.text}`}>{ev.title}</p>
              <span className={`shrink-0 text-sm ${s.text}`}>{s.glyph}</span>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

// ── Crew & Department Status ──────────────────────────────────────────────────

function CrewDeptStatus() {
  return (
    <Panel>
      <SectionHeader title="Crew & Department Status" />
      <div className="grid grid-cols-5 gap-2">
        {deptCrewCounts.map((d) => {
          const dept = DEPARTMENTS[d.key];
          const c = toneClasses(d.status);
          return (
            <div key={d.key} className="flex flex-col items-center gap-1.5 rounded-md border border-edge bg-panel-2/60 p-2">
              <span className={`h-7 w-7 rounded-md ${dept.bg}`} />
              <span className={`font-mono text-sm font-bold ${dept.text}`}>{d.count}</span>
              <span className={`text-[9px] font-bold uppercase tracking-wide ${c.text}`}>NOMINAL</span>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

// ── Communications ────────────────────────────────────────────────────────────

function CommunicationsPanel() {
  return (
    <Panel>
      <SectionHeader title="Communications" />
      <ul className="flex flex-col gap-2">
        <li className="flex items-center justify-between rounded-md border border-edge bg-panel-2/60 p-2.5">
          <span className="text-[10px] uppercase tracking-wide text-lcars-muted">Unread Messages</span>
          <span className="font-mono text-sm font-bold text-command">{communications.unreadMessages}</span>
        </li>
        <li className="flex items-center justify-between rounded-md border border-edge bg-panel-2/60 p-2.5">
          <span className="text-[10px] uppercase tracking-wide text-lcars-muted">Active Threads</span>
          <span className="font-mono text-sm font-bold text-science">{communications.activeThreads}</span>
        </li>
      </ul>
      <button className="mt-3 w-full rounded border border-edge bg-panel-2/60 py-1.5 text-[10px] uppercase tracking-[0.2em] text-science hover:border-science/50">
        View Communications
      </button>
    </Panel>
  );
}

// ── Crew Roster ───────────────────────────────────────────────────────────────

function CrewRoster() {
  return (
    <Panel>
      <SectionHeader title="Crew Roster" action={
        <StatusBadge label={`${crew.length} on duty`} tone="status" />
      } />
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {crew.map((c) => {
          const dept = DEPARTMENTS[c.department];
          return (
            <article
              key={c.id}
              className="flex flex-col gap-2 rounded-lcars border border-edge bg-panel-2/60 p-3"
              style={{ borderLeftColor: dept.hex, borderLeftWidth: 4 }}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="text-sm font-bold normal-case text-lcars-text">{c.name}</h3>
                  <p className="text-[11px] text-lcars-muted">{c.role}</p>
                </div>
                <StatusBadge label={c.status} tone={c.tone} />
              </div>
              <p className="text-xs text-lcars-text/80">{c.focus}</p>
              <span className="font-mono text-[10px] text-lcars-muted">{c.id}</span>
            </article>
          );
        })}
      </div>
    </Panel>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function NumberOnePage() {
  const assigned = missions.filter((m) =>
    ['ASSIGNED', 'IN_PROGRESS', 'ACTIVE'].includes(m.status.toUpperCase())
  );
  return (
    <div className="flex flex-col gap-4">
      <CommandStats />

      <div className="grid gap-4 xl:grid-cols-[1fr_260px]">
        <div className="flex flex-col gap-4">
          <CommandOverview />
          <CrewDeptStatus />
        </div>
        <div className="flex flex-col gap-4">
          <CommandCalendar />
          <CommunicationsPanel />
        </div>
      </div>

      <CrewRoster />

      <Panel>
        <SectionHeader title="Active Missions" action={
          <StatusBadge label={`${assigned.length} active`} tone="operations" />
        } />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {assigned.map((m) => <MissionCard key={m.mission_id} mission={m} />)}
        </div>
      </Panel>
    </div>
  );
}
