import Link from 'next/link';
import type { Mission } from '@/lib/types';
import { DEPARTMENTS } from '@/lib/departments';
import { StatusBadge } from './StatusBadge';

/**
 * MissionCard — compact mission readout. Shape matches the Command Centre
 * mission registry rows (mission-registry-reader.js), so live data drops in
 * without prop changes.
 */
export interface MissionCardProps {
  mission: Mission;
}

const PRIORITY_TONE: Record<string, string> = {
  P0: 'text-operations border-operations',
  P1: 'text-command border-command',
  P2: 'text-medical border-medical',
  P3: 'text-lcars-muted border-edge',
  '—': 'text-lcars-muted border-edge'
};

export function MissionCard({ mission }: MissionCardProps) {
  const dept = DEPARTMENTS[mission.department];
  return (
    <Link href={`/missions/${mission.mission_id}`} className="block">
    <article
      className="flex flex-col gap-2 rounded-lcars border border-edge border-l-4 bg-panel-2/60 p-3 hover:border-command/60 transition-colors cursor-pointer"
      style={{ borderLeftColor: dept.hex }}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="font-mono text-xs text-lcars-muted">
          {mission.mission_id}
        </span>
        <span
          className={`rounded-md border px-1.5 py-0.5 font-mono text-[11px] font-bold ${
            PRIORITY_TONE[mission.priority] ?? PRIORITY_TONE['—']
          }`}
        >
          {mission.priority}
        </span>
      </div>
      <h3 className="text-sm font-semibold normal-case tracking-normal text-lcars-text">
        {mission.title}
      </h3>
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-lcars-muted">
        <StatusBadge label={mission.status} status={mission.status} />
        <span>· {mission.owner}</span>
        {mission.specialist && <span>· {mission.specialist}</span>}
      </div>
    </article>
    </Link>
  );
}
