import type { StateTone } from '@/lib/types';
import { stateToneClasses } from '@/lib/departments';

/**
 * Canonical score → state-tone mapping for confidence displays (MSN-0315
 * Phase 1B). Decoupled from department colour — previously each duplicate
 * (RecoveryConfidencePanel, HumanSystemsPanel, WellnessInsightPanel) mapped
 * confidence onto an arbitrary department colour (e.g. "operations"/red for a
 * *mid* score), which conflated department identity with operational state.
 */
export function confidenceStateTone(score: number | null): StateTone {
  if (score == null) return 'unknown';
  if (score >= 75) return 'ok';
  if (score >= 50) return 'warn';
  return 'crit';
}

export interface ConfidenceIndicatorProps {
  /** 0-100, or null when there is no data yet (renders as unknown/no-data). */
  score: number | null;
  /** Omit when the caller already renders its own label above the indicator. */
  label?: string;
  /** Compact renders a slim inline bar + badge for use inside dense rows. */
  compact?: boolean;
}

export function ConfidenceIndicator({ score, label, compact = false }: ConfidenceIndicatorProps) {
  const tone = confidenceStateTone(score);
  const c = stateToneClasses(tone);
  const pct = score ?? 0;
  const valueText = score != null ? `${score}%` : 'No data';

  const badge = (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider ${c.text} ${c.border} ${c.bg}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${c.dot}`} />
      {valueText}
    </span>
  );

  if (compact) {
    return (
      <div className="flex items-center gap-3">
        <div className="h-2 flex-1 rounded-full bg-edge/30 overflow-hidden">
          <div className={`h-full rounded-full ${c.dot} transition-all`} style={{ width: `${pct}%` }} />
        </div>
        <span className={`font-sans text-sm font-bold shrink-0 ${c.text}`}>{valueText}</span>
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col gap-1.5">
      <div className={`flex items-center gap-3 ${label ? 'justify-between' : 'justify-end'}`}>
        {label && <p className="text-[10px] uppercase tracking-wider text-lcars-muted">{label}</p>}
        {badge}
      </div>
      <div className="h-3 rounded-full bg-edge/30 overflow-hidden">
        <div className={`h-full rounded-full ${c.dot} transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
