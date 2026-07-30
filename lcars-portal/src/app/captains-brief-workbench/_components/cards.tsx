'use client';

// wb- equivalents of the LCARS ConfidenceIndicator / EscalationBanner /
// RecommendationCard used by the old (app)/captains-brief page. Semantics are
// preserved exactly — confidence thresholds (>=75 ok / >=50 warn / else crit),
// the 1/2/3 escalation levels (3 = Critical/crit, 1&2 = warn), and the same
// recommendation fields — only the tokens change (dept colours → wb-).

import type { Tone } from './types';
import { confidenceTone } from './types';

const TONE_CLASSES: Record<Tone, { text: string; border: string; bg: string; bar: string }> = {
  ok: { text: 'text-wb-ok-on', border: 'border-wb-ok', bg: 'bg-wb-ok/10', bar: 'bg-wb-ok' },
  warn: { text: 'text-wb-warn-on', border: 'border-wb-warn', bg: 'bg-wb-warn/10', bar: 'bg-wb-warn' },
  crit: { text: 'text-wb-crit-on', border: 'border-wb-crit', bg: 'bg-wb-crit/10', bar: 'bg-wb-crit' },
  unknown: { text: 'text-wb-ink2', border: 'border-wb-line', bg: 'bg-wb-line/40', bar: 'bg-wb-ink2' },
};

/** 0-100 confidence, or null (renders "No data"). Matches ConfidenceIndicator. */
export function ConfidenceMeter({ score, label }: { score: number | null; label?: string }) {
  const tone = confidenceTone(score);
  const c = TONE_CLASSES[tone];
  const pct = score ?? 0;
  const valueText = score != null ? `${Math.round(score)}%` : 'No data';
  return (
    <div className="flex w-full flex-col gap-1.5">
      <div className={`flex items-center gap-3 ${label ? 'justify-between' : 'justify-end'}`}>
        {label && <p className="text-[11px] uppercase tracking-[0.14em] text-wb-ink2">{label}</p>}
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider ${c.text} ${c.border} ${c.bg}`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${c.bar}`} />
          {valueText}
        </span>
      </div>
      <div className="h-2.5 overflow-hidden rounded-full bg-wb-line">
        <div className={`h-full rounded-full ${c.bar} transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export type EscalationLevel = 1 | 2 | 3;
const LEVEL_TONE: Record<EscalationLevel, Tone> = { 1: 'warn', 2: 'warn', 3: 'crit' };
const LEVEL_LABEL: Record<EscalationLevel, string> = { 1: 'Attention', 2: 'Low', 3: 'Critical' };

/** wb- escalation banner. Level→tone mapping preserved from EscalationBanner. */
export function WarningBanner({ level, message }: { level: EscalationLevel; message: string }) {
  const c = TONE_CLASSES[LEVEL_TONE[level]];
  const headline = LEVEL_LABEL[level];
  return (
    <div className={`rounded-md border ${c.border} ${c.bg} px-3 py-2`}>
      <div className="flex items-center gap-2">
        <span className={`shrink-0 text-xs font-bold uppercase tracking-widest ${c.text} ${level === 3 ? 'animate-pulse' : ''}`}>
          {level === 3 ? `⚠ ${headline}` : headline}
        </span>
        <span className="text-xs text-wb-ink/80">{message}</span>
      </div>
    </div>
  );
}

/** wb- recommendation/priority card. Same fields the LCARS RecommendationCard
 *  was fed on the old page (action / why / source / confidence / evidence). */
export function RecCard({
  action,
  why,
  source,
  confidence,
  evidence,
}: {
  action: string;
  why?: string;
  source?: string;
  confidence?: string;
  evidence?: string[];
}) {
  return (
    <div className="rounded-md border border-wb-line bg-wb-surface p-3">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[13px] font-medium text-wb-ink">{action}</p>
        {confidence && (
          <span className="shrink-0 rounded-full border border-wb-line px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-wb-ink2">
            {confidence}
          </span>
        )}
      </div>
      {why && <p className="mt-1 text-[12px] text-wb-ink2">{why}</p>}
      {source && (
        <p className="mt-1 text-[10px] uppercase tracking-[0.14em] text-wb-sage-deep">{source}</p>
      )}
      {evidence && evidence.length > 0 && (
        <ul className="mt-1.5 list-disc pl-4 text-[11px] text-wb-ink2/90">
          {evidence.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
