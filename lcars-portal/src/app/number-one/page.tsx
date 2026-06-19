import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { MissionCard } from '@/components/MissionCard';
import { crew, missions } from '@/lib/mockData';
import { DEPARTMENTS } from '@/lib/departments';

export const metadata = { title: 'Number One · LCARS Portal' };

export default function NumberOnePage() {
  const assigned = missions.filter((m) =>
    ['ASSIGNED', 'IN_PROGRESS', 'ACTIVE'].includes(m.status.toUpperCase())
  );
  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel
        title="Number One — Crew & Execution"
        accent="operations"
        eyebrow="Coordination"
      >
        <p className="text-sm text-lcars-text/90">
          Crew roster, duty status and current focus. Maps to the agent status
          and coordination endpoints in Phase 2.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {crew.map((c) => {
            const dept = DEPARTMENTS[c.department];
            return (
              <article
                key={c.id}
                className={`flex flex-col gap-2 rounded-lcars border-l-4 ${dept.border} border-edge bg-panel-2/60 p-3`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-bold normal-case text-lcars-text">
                      {c.name}
                    </h3>
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
      </LCARSPanel>

      <LCARSPanel title="Assigned Work" accent="operations" eyebrow="Execution Queue">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {assigned.map((m) => (
            <MissionCard key={m.mission_id} mission={m} />
          ))}
        </div>
      </LCARSPanel>
    </div>
  );
}
