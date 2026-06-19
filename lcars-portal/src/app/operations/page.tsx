import { LCARSPanel } from '@/components/LCARSPanel';
import { AlertPanel } from '@/components/AlertPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { alerts, services } from '@/lib/mockData';

export const metadata = { title: 'Operations · LCARS Portal' };

const STATE_TONE = {
  operational: 'status',
  degraded: 'command',
  offline: 'operations'
} as const;

export default function OperationsPage() {
  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel
        title="Operations — Integration Status"
        accent="operations"
        eyebrow="Ship Systems"
      >
        <p className="text-sm text-lcars-text/90">
          Live status of the core integrations the portal must not disrupt:
          Dashy, Slack bot, Commander backend, Context Assembly and Supabase.
        </p>
        <ul className="mt-4 flex flex-col divide-y divide-edge overflow-hidden rounded-lcars border border-edge">
          {services.map((s) => (
            <li
              key={s.name}
              className="flex items-center justify-between gap-3 bg-panel-2/50 p-3"
            >
              <div>
                <p className="text-sm font-semibold normal-case text-lcars-text">
                  {s.name}
                </p>
                <p className="text-xs text-lcars-muted">{s.detail}</p>
              </div>
              <StatusBadge label={s.state} tone={STATE_TONE[s.state]} />
            </li>
          ))}
        </ul>
      </LCARSPanel>

      <AlertPanel alerts={alerts} title="Operational Alerts" />
    </div>
  );
}
