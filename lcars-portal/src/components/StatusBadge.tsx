import type { StatusTone } from '@/lib/types';
import { toneClasses, inferTone } from '@/lib/departments';

/**
 * StatusBadge — small pill conveying state. Either pass an explicit `tone`,
 * or pass a `status` string and let the badge infer a sensible tone.
 */
export interface StatusBadgeProps {
  label: string;
  tone?: StatusTone;
  status?: string;
}

export function StatusBadge({ label, tone, status }: StatusBadgeProps) {
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
