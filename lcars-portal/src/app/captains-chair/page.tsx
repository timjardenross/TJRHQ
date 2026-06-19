import { LCARSPanel } from '@/components/LCARSPanel';
import { DepartmentCard } from '@/components/DepartmentCard';
import { MissionCard } from '@/components/MissionCard';
import { AlertPanel } from '@/components/AlertPanel';
import { StatusBadge } from '@/components/StatusBadge';
import {
  alerts,
  captainBrief,
  departments,
  missions,
  operatingPicture
} from '@/lib/mockData';

export const metadata = { title: "Captain's Chair · LCARS Portal" };

export default function CaptainsChairPage() {
  const topMissions = missions.slice(0, 3);
  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel
        title="Captain's Daily Brief"
        accent="command"
        eyebrow={`Stardate ${captainBrief.stardate}`}
        actions={
          <StatusBadge label={operatingPicture.readiness} tone="status" />
        }
      >
        <p className="text-lg font-semibold text-command">{captainBrief.greeting}</p>
        <p className="mt-1 text-sm text-lcars-text/90">{captainBrief.headline}</p>

        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {captainBrief.posture.map((p) => (
            <div
              key={p.label}
              className="rounded-lcars border border-edge bg-panel-2/60 p-3"
            >
              <p className="text-[11px] uppercase tracking-wider text-lcars-muted">
                {p.label}
              </p>
              <div className="mt-1">
                <StatusBadge label={p.value} tone={p.tone} />
              </div>
            </div>
          ))}
          <div className="rounded-lcars border border-edge bg-panel-2/60 p-3">
            <p className="text-[11px] uppercase tracking-wider text-lcars-muted">
              Crew On Duty
            </p>
            <p className="lcars-readout mt-1 text-command">
              {operatingPicture.crewOnDuty}
            </p>
          </div>
        </div>

        <div className="mt-4">
          <p className="text-[11px] uppercase tracking-[0.25em] text-lcars-muted">
            Command Priorities
          </p>
          <ol className="mt-2 flex flex-col gap-2">
            {captainBrief.priorities.map((item, i) => (
              <li
                key={item}
                className="flex items-start gap-3 rounded-md border border-edge bg-space/40 p-2 text-sm"
              >
                <span className="font-mono text-command">{String(i + 1).padStart(2, '0')}</span>
                <span>{item}</span>
              </li>
            ))}
          </ol>
        </div>
      </LCARSPanel>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <LCARSPanel title="Department Status" accent="command" eyebrow="Operating Picture">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {departments.map((d) => (
                <DepartmentCard key={d.key} department={d} />
              ))}
            </div>
          </LCARSPanel>
        </div>
        <AlertPanel alerts={alerts} />
      </div>

      <LCARSPanel
        title="Priority Missions"
        accent="command"
        eyebrow={`${operatingPicture.activeMissions} active · ${operatingPicture.blockers} blocked`}
      >
        <div className="grid gap-3 md:grid-cols-3">
          {topMissions.map((m) => (
            <MissionCard key={m.mission_id} mission={m} />
          ))}
        </div>
      </LCARSPanel>
    </div>
  );
}
