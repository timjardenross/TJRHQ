'use client';

// Single brief-item row + its metrics line. Direct port of the LCARS page's
// ItemRow + MetricsLine (MSN-0328 Wave 3), reskinned to wb- tokens. Unknown
// metric keys still render (generic fallback) so a new domain metric is visible
// without a frontend change — behaviour preserved verbatim.

import type { CaptainBriefItem } from './types';
import { METRIC_LABELS } from './types';

function MetricsLine({ metrics }: { metrics?: Record<string, unknown> }) {
  if (!metrics || Object.keys(metrics).length === 0) return null;
  const parts = Object.entries(metrics)
    .filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => `${METRIC_LABELS[k] ?? k}: ${Array.isArray(v) ? v.join(', ') : String(v)}`);
  if (!parts.length) return null;
  return <p className="mt-0.5 text-[10px] text-wb-ink2/80">{parts.join(' · ')}</p>;
}

export function ItemRow({ item }: { item: CaptainBriefItem }) {
  return (
    <li className="rounded-md border border-wb-line bg-wb-surface p-2">
      <p className="text-[10px] uppercase tracking-[0.14em] text-wb-ink2">
        {item.domain} · {item.event_type}
      </p>
      <p className="mt-0.5 text-xs text-wb-ink/90">{item.reason}</p>
      <MetricsLine metrics={item.metrics} />
    </li>
  );
}
