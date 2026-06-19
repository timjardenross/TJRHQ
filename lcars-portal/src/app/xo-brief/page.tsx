import { StatusBadge } from '@/components/StatusBadge';
import { toneClasses } from '@/lib/departments';
import {
  astrometricsStats,
  dataStreams,
  intelligenceBrief,
  latestDiscovery,
  researchCategories,
  researchQueue
} from '@/lib/mockData';

export const metadata = { title: 'Astrometrics Lab · LCARS Portal' };

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

// ── Stats row ─────────────────────────────────────────────────────────────────

function AstrometricsStats() {
  return (
    <Panel>
      <div className="flex flex-wrap items-center gap-0 divide-x divide-edge">
        <div className="flex flex-col pr-6">
          <span className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">Research Readiness</span>
          <span className="font-lcars text-2xl font-bold leading-none text-status mt-0.5">
            {astrometricsStats.readiness}%
          </span>
        </div>
        <div className="flex flex-col px-6">
          <span className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">Active Projects</span>
          <span className="font-lcars text-2xl font-bold leading-none text-science mt-0.5">
            {astrometricsStats.activeProjects}
          </span>
        </div>
        <div className="flex flex-col pl-6">
          <span className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">Reports Ready</span>
          <span className="font-lcars text-2xl font-bold leading-none text-command mt-0.5">
            {astrometricsStats.reportsReady}
          </span>
        </div>
      </div>
    </Panel>
  );
}

// ── Research Overview ─────────────────────────────────────────────────────────

function ResearchOverview() {
  const max = Math.max(...researchCategories.map((c) => c.count));
  return (
    <Panel>
      <SectionHeader title="Research Overview" action={
        <span className="text-[10px] uppercase tracking-[0.1em] text-lcars-muted">
          Active Projects by Category
        </span>
      } />
      <ul className="flex flex-col gap-2.5">
        {researchCategories.map((cat) => {
          const c = toneClasses(cat.tone);
          return (
            <li key={cat.label} className="flex items-center gap-3">
              <span className="w-36 shrink-0 text-[10px] uppercase tracking-wide text-lcars-muted">
                {cat.label}
              </span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-edge/60">
                <div
                  className={`h-full rounded-full ${c.dot}`}
                  style={{ width: `${(cat.count / max) * 100}%` }}
                />
              </div>
              <span className={`w-4 shrink-0 text-right font-mono text-xs font-bold ${c.text}`}>
                {cat.count}
              </span>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

// ── Data Streams ──────────────────────────────────────────────────────────────

function DataStreams() {
  return (
    <Panel>
      <SectionHeader title="Data Streams" action={
        <button className="text-[10px] uppercase tracking-[0.15em] text-science hover:text-science/70">
          View All Streams
        </button>
      } />
      <ul className="flex flex-col divide-y divide-edge overflow-hidden rounded-md border border-edge">
        {dataStreams.map((s) => {
          const c = toneClasses(s.tone);
          return (
            <li key={s.label} className="flex items-center justify-between bg-panel-2/50 px-3 py-2">
              <span className="text-[11px] text-lcars-text">{s.label}</span>
              <StatusBadge label={s.value} tone={s.tone} />
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

// ── Latest Discovery ──────────────────────────────────────────────────────────

function LatestDiscoveryPanel() {
  return (
    <Panel>
      <SectionHeader title="Latest Discovery" />
      <div className="rounded-md border border-science/40 bg-science/5 p-3">
        <p className="text-[10px] uppercase tracking-[0.2em] text-science">New Candidate</p>
        <p className="mt-1 text-sm font-bold text-lcars-text">{latestDiscovery.designation}</p>
        <p className="text-[11px] text-science">{latestDiscovery.classification}</p>
        <p className="mt-2 text-[10px] text-lcars-muted">Distance: {latestDiscovery.distance}</p>
        <p className="mt-2 text-xs leading-relaxed text-lcars-text/80">{latestDiscovery.detail}</p>
        <button className="mt-3 w-full rounded border border-science/40 bg-transparent py-1.5 text-[10px] uppercase tracking-[0.2em] text-science hover:border-science/70">
          View Full Report
        </button>
      </div>
    </Panel>
  );
}

// ── Research Queue ────────────────────────────────────────────────────────────

function ResearchQueue() {
  const STATUS_STYLE = {
    in_progress: { label: 'In Progress', tone: 'medical'  as const },
    queued:      { label: 'Queued',      tone: 'neutral'  as const },
    completed:   { label: 'Completed',   tone: 'status'   as const }
  };
  return (
    <Panel>
      <SectionHeader title="Research Queue" action={
        <button className="text-[10px] uppercase tracking-[0.15em] text-science hover:text-science/70">
          View Full Report
        </button>
      } />
      <ol className="flex flex-col gap-2">
        {researchQueue.map((item) => {
          const s = STATUS_STYLE[item.status];
          return (
            <li key={item.id} className="flex gap-3 rounded-md border border-edge bg-panel-2/60 p-2.5">
              <span className="shrink-0 font-mono text-xs font-bold text-science">{item.id}</span>
              <div className="min-w-0 flex-1">
                <p className="text-[11px] font-semibold text-lcars-text">{item.title}</p>
                <p className="text-[10px] text-lcars-muted">{item.location}</p>
              </div>
              <StatusBadge label={s.label} tone={s.tone} />
            </li>
          );
        })}
      </ol>
    </Panel>
  );
}

// ── Intelligence Brief (preserved) ───────────────────────────────────────────

function IntelBrief() {
  const brief = intelligenceBrief;
  return (
    <Panel>
      <SectionHeader title={brief.title} action={
        <div className="flex flex-wrap gap-1.5">
          {brief.themes.map((t) => (
            <span
              key={t}
              className="rounded-full border border-science bg-science/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-science"
            >
              {t}
            </span>
          ))}
        </div>
      } />
      <p className="mb-3 text-sm text-lcars-text/90">{brief.summary}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {brief.sections.map((s) => (
          <div key={s.heading} className="rounded-md border border-edge bg-panel-2/60 p-3">
            <h3 className="mb-1 text-[11px] font-bold uppercase tracking-[0.2em] text-science">
              {s.heading}
            </h3>
            <p className="text-xs leading-relaxed text-lcars-text/80">{s.body}</p>
          </div>
        ))}
      </div>
    </Panel>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function XOBriefPage() {
  return (
    <div className="flex flex-col gap-4">
      <AstrometricsStats />

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="flex flex-col gap-4">
          <ResearchOverview />
          <DataStreams />
        </div>
        <div className="flex flex-col gap-4">
          <LatestDiscoveryPanel />
          <ResearchQueue />
        </div>
      </div>

      <IntelBrief />
    </div>
  );
}
