import type { StateTone } from '@/lib/types';
import { stateToneClasses } from '@/lib/departments';

export type EscalationLevel = 1 | 2 | 3;

/**
 * Canonical escalation banner (MSN-0315 Phase 1B). Consolidates
 * RecoveryConfidencePanel's leveled banner and HumanSystemsPanel's red-flag
 * block onto the state.* tokens.
 *
 * Fixes a real severity-inversion bug found during consolidation:
 * RecoveryConfidencePanel previously rendered level 3 ("Critical") in the
 * `medical` department colour (blue) and level 2 ("Low") in `operations`
 * (red) — the more severe level read as calmer than the less severe one.
 * Levels now map monotonically: 1/2 -> warn, 3 -> crit.
 */
const LEVEL_TONE: Record<EscalationLevel, StateTone> = { 1: 'warn', 2: 'warn', 3: 'crit' };
const LEVEL_LABEL: Record<EscalationLevel, string> = { 1: 'Attention', 2: 'Low', 3: 'Critical' };

export interface EscalationBannerProps {
  level: EscalationLevel;
  message: string;
  /** Optional third line, e.g. a disclaimer — rendered smaller/muted below `message`. */
  footnote?: string;
  /** Overrides the default level label (e.g. a domain-specific headline). */
  label?: string;
}

export function EscalationBanner({ level, message, footnote, label }: EscalationBannerProps) {
  const tone = LEVEL_TONE[level];
  const c = stateToneClasses(tone);
  const headline = label ?? LEVEL_LABEL[level];

  return (
    <div className={`rounded-md border ${c.border} ${c.bg} px-3 py-2`}>
      <div className="flex items-center gap-2">
        <span
          className={`text-xs font-bold uppercase tracking-widest shrink-0 ${c.text} ${level === 3 ? 'animate-pulse' : ''}`}
        >
          {level === 3 ? `⚠ ${headline}` : headline}
        </span>
        <span className="text-xs text-lcars-text/80">{message}</span>
      </div>
      {footnote && <p className="mt-1 text-[11px] text-lcars-muted">{footnote}</p>}
    </div>
  );
}
