import Link from 'next/link';
import type { Mission } from '@/lib/types';
import { Badge } from '@/components/ui';
import { DEPARTMENTS } from '@/lib/departments';
import { statusToBadge } from './shared';

/**
 * Mission Workbench fork of components/MissionCard.tsx — same data shape,
 * same link target's data source (mission_id), wb-* look. See that file's
 * docstring for the upstream data-shape contract this must keep matching.
 */
export interface MissionCardProps {
  mission: Mission;
}

const PRIORITY_BADGE: Record<string, 'error' | 'warning' | 'info' | 'neutral'> = {
  P0: 'error',
  P1: 'warning',
  P2: 'info',
  P3: 'neutral',
};

export function MissionCard({ mission }: MissionCardProps) {
  const dept = mission.department ? DEPARTMENTS[mission.department] : DEPARTMENTS.command;
  return (
    <Link href={`/mission-workbench/${mission.mission_id}`} className="block">
      <article
        className="flex flex-col gap-2 rounded-lg border border-wb-line border-l-4 bg-wb-surface p-3
          transition-colors hover:border-wb-sage-deep/60"
        style={{ borderLeftColor: dept.hex }}
      >
        <div className="flex items-start justify-between gap-2">
          <span className="font-mono text-[11px] text-wb-ink2">{mission.mission_id}</span>
          <Badge status={PRIORITY_BADGE[mission.priority] ?? 'neutral'}>{mission.priority}</Badge>
        </div>
        <h3 className="text-[13px] font-medium text-wb-ink">{mission.title}</h3>
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-wb-ink2">
          <Badge status={statusToBadge(mission.status)}>{mission.status}</Badge>
          {mission.owner && <span>· {mission.owner}</span>}
          {mission.specialist && <span>· {mission.specialist}</span>}
        </div>
      </article>
    </Link>
  );
}
