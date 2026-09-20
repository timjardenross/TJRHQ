import type { StatusTone, StateTone } from '@/lib/types';
import { toneClasses, inferTone, stateToneClasses } from '@/lib/departments';

/**
 * StatusBadge — small pill conveying either department identity (`tone`/
 * `status`, the original `StatusTone` system) or operational risk/WIP state
 * (`stateTone`, the `StateTone` system — see `stateToneClasses()`'s doc
 * comment in `lib/departments.ts`). These are two independent signals; do
 * not repurpose `tone` to mean state (that conflation was the bug in
 * `DeliveryPanel.tsx`, found MSN-0394 Phase 9, fixed Phase 12 — see this
 * mission's §6 Reporting). Precedence when both are somehow passed:
 * `stateTone` wins, since it's the more specific, explicitly-requested
 * signal.
 */
export interface StatusBadgeProps {
  label: string;
  tone?: StatusTone;
  status?: string;
  /** Operational risk/WIP/confidence state — independent of department
   *  identity. Use this, not `tone`, for anything communicating live/
   *  health/risk/escalation state. */
  stateTone?: StateTone;
}

export function StatusBadge({ label, tone, status, stateTone }: StatusBadgeProps) {
  if (stateTone) {
    // Mandatory pairing per stateToneClasses()'s doc comment: `on` (the
    // high-contrast text variant) is always rendered alongside `bg`/
    // `border` from the same call, never as a bare text colour.
    const s = stateToneClasses(stateTone);
    return (
      <span
        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider ${s.on} ${s.border} ${s.bg}`}
      >
        <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
        {label}
      </span>
    );
  }

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
