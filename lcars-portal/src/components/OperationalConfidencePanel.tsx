'use client';

import { Card } from '@/components/ui';
import type { OperationalConfidence } from '@/lib/operationalConfidence';

export function OperationalConfidencePanel({ confidence }: { confidence: OperationalConfidence }) {
  const label = confidence.score === null ? 'Confidence unavailable' : `${confidence.score}% operational confidence`;
  const tone = confidence.band === 'high' ? 'text-state-ok-on border-state-ok/50 bg-state-ok/10' : confidence.band === 'moderate' ? 'text-state-warn-on border-state-warn/50 bg-state-warn/10' : confidence.band === 'low' ? 'text-state-crit-on border-state-crit/50 bg-state-crit/10' : 'text-wb-ink2 border-wb-line';
  return <Card aria-labelledby="operational-confidence-title">
    <div className="flex flex-wrap items-baseline justify-between gap-2">
      <div><h2 id="operational-confidence-title" className="font-serif text-lg text-wb-ink">Operational confidence</h2><p className="text-[12px] text-wb-ink2">Based on source freshness and completeness. Sources with unknown or unavailable freshness count as not-fresh in the score, and a &ldquo;high&rdquo; rating is capped to &ldquo;moderate&rdquo; if more than 20% of sources have unknown/unavailable freshness, even when the underlying score would otherwise qualify.</p></div>
      <p className={`rounded border px-2 py-1 text-[13px] font-semibold ${tone}`} aria-label={label}>{label}</p>
    </div>
    <ul className="mt-3 space-y-1 text-[12px] text-wb-ink2">{confidence.reasons.map((reason) => <li key={reason}>• {reason}</li>)}</ul>
    <p className="mt-2 text-[11px] text-wb-ink2">Assessed {confidence.assessedSources} of {confidence.totalSources} sources. This score is a decision aid, not a replacement for source detail.</p>
  </Card>;
}
