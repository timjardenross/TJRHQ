import type { Alert } from '@/lib/types';
import { LCARSPanel } from './LCARSPanel';

/**
 * AlertPanel — stacked alert list. Maps to GET /api/v1/health/alerts.
 */
export interface AlertPanelProps {
  alerts: Alert[];
  title?: string;
}

const LEVEL_STYLE: Record<
  Alert['level'],
  { text: string; border: string; bg: string; label: string }
> = {
  critical: {
    text: 'text-operations',
    border: 'border-operations',
    bg: 'bg-operations/10',
    label: 'CRITICAL'
  },
  warning: {
    text: 'text-command',
    border: 'border-command',
    bg: 'bg-command/10',
    label: 'WARNING'
  },
  info: {
    text: 'text-medical',
    border: 'border-medical',
    bg: 'bg-medical/10',
    label: 'INFO'
  },
  nominal: {
    text: 'text-status',
    border: 'border-status',
    bg: 'bg-status/10',
    label: 'NOMINAL'
  }
};

function formatTime(ts: string): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toUTCString().replace('GMT', 'UTC');
}

export function AlertPanel({ alerts, title = 'Alerts' }: AlertPanelProps) {
  return (
    <LCARSPanel title={title} accent="operations" eyebrow="Ship Systems">
      {alerts.length === 0 ? (
        <p className="text-sm text-lcars-muted">No active alerts. All systems nominal.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {alerts.map((a) => {
            const s = LEVEL_STYLE[a.level];
            return (
              <li
                key={a.id}
                className={`rounded-lcars border-l-4 ${s.border} ${s.bg} p-3`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className={`text-xs font-bold uppercase tracking-wider ${s.text}`}>
                    {s.label}
                  </span>
                  <span className="font-mono text-[10px] text-lcars-muted">
                    {formatTime(a.timestamp)}
                  </span>
                </div>
                <p className="mt-1 text-sm font-semibold text-lcars-text">{a.title}</p>
                <p className="text-xs text-lcars-muted">{a.detail}</p>
                <p className="mt-1 font-mono text-[10px] text-lcars-muted">
                  SRC · {a.source}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </LCARSPanel>
  );
}
