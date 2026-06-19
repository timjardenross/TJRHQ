import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { wellness } from '@/lib/mockData';
import { toneClasses } from '@/lib/departments';

export const metadata = { title: 'Medical / Wellness · LCARS Portal' };

const TREND_GLYPH: Record<string, string> = {
  up: '▲',
  down: '▼',
  steady: '▬'
};

export default function MedicalPage() {
  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel
        title="Medical Bay — Captain Wellness"
        accent="medical"
        eyebrow="Recovery & Readiness"
        actions={<StatusBadge label="Monitoring" tone="medical" />}
      >
        <p className="text-sm text-lcars-text/90">
          Wellness and recovery indicators for the Captain. Data is governed by
          ADR-HEALTH-001 and will be sourced from the personal-health endpoint in
          Phase 2. Phase 1 shows placeholder readings.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {wellness.map((m) => {
            const c = toneClasses(m.tone);
            return (
              <div
                key={m.label}
                className={`rounded-lcars border ${c.border} ${c.bg} p-4`}
              >
                <div className="flex items-center justify-between">
                  <p className="text-[11px] uppercase tracking-wider text-lcars-muted">
                    {m.label}
                  </p>
                  <span className={`text-xs ${c.text}`}>{TREND_GLYPH[m.trend]}</span>
                </div>
                <p className={`mt-1 font-lcars text-2xl font-bold ${c.text}`}>
                  {m.value}
                </p>
              </div>
            );
          })}
        </div>
      </LCARSPanel>

      <LCARSPanel title="Recovery Guidance" accent="medical" eyebrow="Coaching">
        <ul className="flex flex-col gap-2 text-sm text-lcars-text/90">
          <li className="rounded-md border border-edge bg-space/40 p-3">
            Protect the afternoon focus block — strain trending down, recovery up.
          </li>
          <li className="rounded-md border border-edge bg-space/40 p-3">
            Maintain hydration and sleep window; both within target range.
          </li>
          <li className="rounded-md border border-edge bg-space/40 p-3">
            No wellness alerts active. Continue current recovery protocol.
          </li>
        </ul>
      </LCARSPanel>
    </div>
  );
}
