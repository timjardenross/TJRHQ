import type { DepartmentKey } from '@/lib/types';
import { DEPARTMENTS } from '@/lib/departments';

/**
 * StatTile — a single dashboard metric card (big number + label). Used for
 * summary rows like the Knowledge Library's document counts.
 */
export interface StatTileProps {
  label: string;
  value: number | string;
  accent?: DepartmentKey;
  hint?: string;
}

export function StatTile({ label, value, accent = 'command', hint }: StatTileProps) {
  const dept = DEPARTMENTS[accent];
  return (
    <div className="rounded-lcars border border-edge bg-panel/60 p-4">
      <p className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted">{label}</p>
      <p className={`mt-1 text-3xl font-bold ${dept.text}`}>{value}</p>
      {hint && <p className="mt-1 text-[11px] text-lcars-muted">{hint}</p>}
    </div>
  );
}
