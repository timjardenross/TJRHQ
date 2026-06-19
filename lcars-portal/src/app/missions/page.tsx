import { LCARSPanel } from '@/components/LCARSPanel';
import { MissionCard } from '@/components/MissionCard';
import { missions, missionSummary } from '@/lib/mockData';

export const metadata = { title: 'Missions · LCARS Portal' };

export default function MissionsPage() {
  const stats = [
    { label: 'Total', value: missionSummary.total, tone: 'text-command' },
    { label: 'Active', value: missionSummary.active, tone: 'text-medical' },
    { label: 'In Progress', value: missionSummary.in_progress, tone: 'text-science' },
    { label: 'Blocked', value: missionSummary.blocked, tone: 'text-operations' },
    { label: 'Completed', value: missionSummary.completed, tone: 'text-status' }
  ];

  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel title="Mission Registry" accent="command" eyebrow="Mission Control">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {stats.map((s) => (
            <div
              key={s.label}
              className="rounded-lcars border border-edge bg-panel-2/60 p-3 text-center"
            >
              <p className={`font-lcars text-2xl font-bold ${s.tone}`}>{s.value}</p>
              <p className="text-[10px] uppercase tracking-wider text-lcars-muted">
                {s.label}
              </p>
            </div>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-2 text-[11px] text-lcars-muted">
          {(['P0', 'P1', 'P2', 'P3'] as const).map((p) => (
            <span
              key={p}
              className="rounded-md border border-edge px-2 py-1 font-mono"
            >
              {p}: {missionSummary.by_priority[p]}
            </span>
          ))}
        </div>
      </LCARSPanel>

      <LCARSPanel title="Active Missions" accent="command" eyebrow="Sorted by priority">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {missions.map((m) => (
            <MissionCard key={m.mission_id} mission={m} />
          ))}
        </div>
      </LCARSPanel>
    </div>
  );
}
