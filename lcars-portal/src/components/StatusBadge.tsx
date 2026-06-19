import type { StatusTone } from '@/lib/types';
import { toneClasses } from '@/lib/departments';

/**
 * StatusBadge — small pill conveying state. Either pass an explicit `tone`,
 * or pass a `status` string and let the badge infer a sensible tone.
 */
export interface StatusBadgeProps {
  label: string;
  tone?: StatusTone;
  status?: string;
}

/** Map common mission/service status strings to a department tone. */
export function inferTone(status: string): StatusTone {
  const s = status.toUpperCase();
  if (s.includes('BLOCK') || s.includes('OFFLINE') || s.includes('CRITICAL'))
    return 'operations';
  if (s.includes('REVIEW') || s.includes('DEGRADED') || s.includes('PENDING'))
    return 'command';
  if (
    s.includes('COMPLET') ||
    s.includes('OPERATIONAL') ||
    s.includes('GREEN') ||
    s.includes('DONE') ||
    s.includes('ON DUTY')
  )
    return 'status';
  if (s.includes('PROGRESS') || s.includes('ACTIVE') || s.includes('ASSIGNED'))
    return 'medical';
  return 'neutral';
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
