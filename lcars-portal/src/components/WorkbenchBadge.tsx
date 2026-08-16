import type { StatusTone } from '@/lib/types';
import { toneClasses, inferTone } from '@/lib/departments';

/**
 * WorkbenchBadge — sibling of StatusBadge for *-workbench routes. Same
 * rendering logic (StatusBadge's own chrome was already token-neutral), but
 * a separate component so workbenches import nothing named/rooted in the
 * legacy LCARS system. Shares tone-inference via lib/departments.ts's
 * `inferTone`/`toneClasses`, not by importing StatusBadge itself.
 */
export interface WorkbenchBadgeProps {
  label: string;
  tone?: StatusTone;
  status?: string;
}

export function WorkbenchBadge({ label, tone, status }: WorkbenchBadgeProps) {
  const resolved = tone ?? inferTone(status ?? label);
  const c = toneClasses(resolved);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider ${c.text} ${c.border} ${c.bg}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${c.dot}`} />
      {label}
    </span>
  );
}
