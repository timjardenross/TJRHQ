import { LCARSPanel } from '@/components/LCARSPanel';
import { DepartmentCard } from '@/components/DepartmentCard';
import { StatusBadge } from '@/components/StatusBadge';
import { departments, services } from '@/lib/mockData';

export const metadata = { title: 'Engineering · LCARS Portal' };

export default function EngineeringPage() {
  const engDepts = departments.filter((d) =>
    ['engineering', 'status'].includes(d.key)
  );
  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel
        title="Engineering Deck"
        accent="engineering"
        eyebrow="Systems & Runtime"
      >
        <p className="text-sm text-lcars-text/90">
          Build pipeline, runtime services and integration health for the USS TJR
          computer core. Phase 1 shows placeholder telemetry.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {engDepts.map((d) => (
            <DepartmentCard key={d.key} department={d} />
          ))}
        </div>
      </LCARSPanel>

      <LCARSPanel title="System Readouts" accent="engineering" eyebrow="Telemetry">
        <div className="grid gap-3 sm:grid-cols-3">
          {services.map((s) => (
            <div
              key={s.name}
              className="rounded-lcars border border-edge bg-panel-2/60 p-3"
            >
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-sm font-semibold normal-case text-lcars-text">
                  {s.name}
                </h3>
                <StatusBadge label={s.state} tone={s.tone} />
              </div>
              <p className="mt-1 text-xs text-lcars-muted">{s.detail}</p>
            </div>
          ))}
        </div>
      </LCARSPanel>
    </div>
  );
}
