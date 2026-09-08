'use client';

// Single brief-item row + its metrics line. Direct port of the LCARS page's
// ItemRow + MetricsLine (MSN-0328 Wave 3), reskinned to wb- tokens. Unknown
// metric keys still render (generic fallback) so a new domain metric is visible
// without a frontend change — behaviour preserved verbatim.
//
// `reason` is the Attention Engine's routing formula ("importance=90 >= 75
// AND confidence=80 >= 70") — a scoring trace, not what actually happened
// (see attention_engine.evaluate_event). The real content lives in
// `recommendation.description` (core_events.recommended_action, wired via
// captain_brief_contract.recommendation_from_event) — render that as the
// primary line when present, and demote `reason` to a caption so an
// Interrupt Now item is legible instead of showing only the routing formula.

import type { CaptainBriefItem } from './types';
import { METRIC_LABELS } from './types';

interface PriorityScoreMetric {
  total_score?: number;
  risk_score?: number;
  dominant_value_dimension?: string | null;
  explanation?: string;
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

// Generic fallback for a metric value that's itself an object (e.g. a
// nested score breakdown) — flattens it instead of falling through to
// `String(v)`, which renders as the unreadable "[object Object]".
function formatMetricValue(value: unknown): string {
  if (Array.isArray(value)) return value.join(', ');
  if (isPlainObject(value)) {
    return Object.entries(value)
      .filter(([, v]) => v !== null && v !== undefined && v !== '')
      .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : String(v)}`)
      .join(', ');
  }
  return String(value);
}

function MetricsLine({ metrics }: { metrics?: Record<string, unknown> }) {
  if (!metrics || Object.keys(metrics).length === 0) return null;
  const parts = Object.entries(metrics)
    // priority_score is a structured PriorityScore breakdown, not a scalar
    // metric — PriorityLine renders it separately, in context.
    .filter(([k, v]) => k !== 'priority_score' && v !== null && v !== undefined && v !== '')
    .map(([k, v]) => `${METRIC_LABELS[k] ?? k}: ${formatMetricValue(v)}`);
  if (!parts.length) return null;
  return <p className="mt-0.5 text-[10px] text-wb-ink2/80">{parts.join(' · ')}</p>;
}

// Priority Engine detail. Prefers the item's own priority_score/risk_score/
// priority_explanation fields (Wave 3 ranking pass); falls back to the
// metrics.priority_score breakdown attached at emission time
// (intelligence_store._priority_score_for_event) when those are absent —
// both carry the same PriorityScore shape.
function PriorityLine({ item }: { item: CaptainBriefItem }) {
  const metricScore = isPlainObject(item.metrics?.priority_score)
    ? (item.metrics!.priority_score as PriorityScoreMetric)
    : null;
  const score = item.priority_score ?? metricScore?.total_score ?? null;
  const risk = item.risk_score ?? metricScore?.risk_score ?? null;
  const dimension = metricScore?.dominant_value_dimension ?? null;
  const explanation = item.priority_explanation ?? metricScore?.explanation ?? null;

  if (score == null && risk == null && !explanation) return null;

  return (
    <p className="mt-0.5 text-[10px] text-wb-ink2/80">
      {score != null && <span>Priority {Math.round(score)}</span>}
      {risk != null && <span>{score != null ? ' · ' : ''}Risk {Math.round(risk)}</span>}
      {dimension && <span> · {dimension}</span>}
      {explanation && <span className="block text-wb-ink2/70">{explanation}</span>}
    </p>
  );
}

export function ItemRow({ item }: { item: CaptainBriefItem }) {
  const headline = item.recommendation?.description ?? item.reason;
  const showReasonCaption = headline !== item.reason;

  return (
    <li className="rounded-md border border-wb-line bg-wb-surface p-2">
      <p className="text-[10px] uppercase tracking-[0.14em] text-wb-ink2">
        {item.domain} · {item.event_type}
      </p>
      <p className="mt-0.5 text-xs text-wb-ink/90">{headline}</p>
      {showReasonCaption && <p className="mt-0.5 text-[10px] text-wb-ink2/70">{item.reason}</p>}
      <PriorityLine item={item} />
      <MetricsLine metrics={item.metrics} />
    </li>
  );
}
