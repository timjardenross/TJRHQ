'use client';

// Topic Detail — drill-down from My Evidence (Phase 2 mission spec).
// Evidence-grounded, hedged language only (spec §13): no medical advice,
// no overstated certainty. Evidence-base composition counts here ARE
// appropriate per the counts rule (§18) — they describe evidence quality,
// not machine workload.

import { useEffect, useState } from 'react';
import { Badge, Button, Card, toneToStatus } from '@/components/ui';
import {
  CONFIDENCE_LABEL, EVIDENCE_CONTRIBUTION_LABEL, STRENGTH_LABEL, TREND_LABEL,
  strengthTone, type EvidenceItem,
} from './shared';

interface TopicDetailPayload {
  topic_key: string;
  topic_label: string;
  strength: 'STRONG' | 'MODERATE' | 'LIMITED';
  trend: 'up' | 'down' | 'stable' | 'mixed' | 'unknown';
  last_changed: string | null;
  composition: { high: number; medium: number; low: number; unknown: number };
  recent_changes: EvidenceItem[];
  supports: EvidenceItem[];
  challenges: EvidenceItem[];
  safety: { items: EvidenceItem[]; clear: boolean };
  what_we_dont_know_yet: string[];
  recent_items: EvidenceItem[];
  gaps: { evidence_contribution_coverage: string; history_over_time: string };
}

function ItemRow({ item }: { item: EvidenceItem }) {
  return (
    <div className="border-b border-wb-line pb-2 text-[12.5px] last:border-0">
      <div className="font-semibold text-wb-ink">
        {item.source_url ? (
          <a href={item.source_url} target="_blank" rel="noreferrer" className="hover:underline">{item.title}</a>
        ) : item.title}
      </div>
      <div className="text-wb-ink2">
        {item.source_name}
        {item.study_design && <> · {item.study_design}</>}
        {item.sample_size ? <> · n={item.sample_size}</> : null}
        {item.evidence_contribution && <> · {EVIDENCE_CONTRIBUTION_LABEL[item.evidence_contribution] ?? item.evidence_contribution}</>}
      </div>
      {item.summary && <div className="mt-1 text-wb-ink2">{item.summary}</div>}
    </div>
  );
}

export function TopicDetail({ topicKey, onBack }: { topicKey: string; onBack: () => void }) {
  const [data, setData] = useState<TopicDetailPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/health-osint/topics/${encodeURIComponent(topicKey)}`)
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw new Error(d?.error || 'Failed to load');
        setData(d);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false));
  }, [topicKey]);

  if (loading) return <p className="text-sm text-wb-ink2">Loading…</p>;
  if (error) return <p className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">{error}</p>;
  if (!data) return null;

  const total = data.composition.high + data.composition.medium + data.composition.low + data.composition.unknown;

  return (
    <div className="space-y-6">
      <Button variant="secondary" size="sm" onClick={onBack}>← Back to My Evidence</Button>

      <Card>
        <h2 className="mb-2 font-serif text-lg text-wb-ink">{data.topic_label}</h2>
        <div className="flex flex-wrap items-center gap-2 text-[12.5px] text-wb-ink2">
          <Badge status={toneToStatus(strengthTone(data.strength))}>{STRENGTH_LABEL[data.strength]} evidence</Badge>
          <span>{TREND_LABEL[data.trend]}</span>
          {data.last_changed && <span>· Last changed {new Date(data.last_changed).toLocaleDateString()}</span>}
        </div>
        <p className="mt-3 max-w-[70ch] text-[12.5px] text-wb-ink2">
          {data.composition.high > 0
            ? `Current understanding is grounded primarily in ${data.composition.high} high-confidence finding${data.composition.high === 1 ? '' : 's'}, corroborated by ${data.composition.medium} moderate-confidence source${data.composition.medium === 1 ? '' : 's'}.`
            : data.composition.medium > 0
              ? `Current understanding rests on moderate-confidence evidence (${data.composition.medium} finding${data.composition.medium === 1 ? '' : 's'}) — treat conclusions here as provisional.`
              : 'Current evidence in this topic is limited or unclear — treat any single finding as preliminary, not settled.'}
        </p>
      </Card>

      {data.recent_changes.length > 0 && (
        <Card title="What Changed Recently">
          <div className="space-y-2">{data.recent_changes.map((i) => (<ItemRow key={i.signal_id} item={i} />))}</div>
        </Card>
      )}

      <Card title="Evidence Base">
        <div className="grid grid-cols-2 gap-3 text-[12.5px] text-wb-ink2 sm:grid-cols-4">
          <div><div className="text-lg font-semibold text-wb-ink">{data.composition.high}</div>Strong</div>
          <div><div className="text-lg font-semibold text-wb-ink">{data.composition.medium}</div>Moderate</div>
          <div><div className="text-lg font-semibold text-wb-ink">{data.composition.low}</div>Emerging</div>
          <div><div className="text-lg font-semibold text-wb-ink">{data.composition.unknown}</div>Unclear</div>
        </div>
        <p className="mt-2 text-[11px] text-wb-ink2">{total} sources considered in this topic over the last year.</p>
      </Card>

      {(data.supports.length > 0 || data.challenges.length > 0) && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {data.supports.length > 0 && (
            <Card title="Supports Current View">
              <div className="space-y-2">{data.supports.map((i) => (<ItemRow key={i.signal_id} item={i} />))}</div>
            </Card>
          )}
          {data.challenges.length > 0 && (
            <Card title="Challenges Current View">
              <div className="space-y-2">{data.challenges.map((i) => (<ItemRow key={i.signal_id} item={i} />))}</div>
            </Card>
          )}
        </div>
      )}

      {data.what_we_dont_know_yet.length > 0 && (
        <Card title="What We Don't Know Yet">
          <ul className="list-inside list-disc space-y-1 text-[12.5px] text-wb-ink2">
            {data.what_we_dont_know_yet.map((g, idx) => (<li key={idx}>{g}</li>))}
          </ul>
        </Card>
      )}

      <Card>
        <h2 className="mb-3 flex items-center gap-2 border-b border-wb-line pb-3 font-serif text-lg text-wb-ink">
          <span className={`inline-block h-2 w-2 rounded-full ${data.safety.clear ? 'bg-wb-ok' : 'bg-wb-crit'}`} aria-hidden />
          Safety Note
        </h2>
        {data.safety.clear ? (
          <p className="text-[13px] text-wb-ink2">✓ Nothing new requires attention in this topic.</p>
        ) : (
          <div className="space-y-2">{data.safety.items.map((i) => (<ItemRow key={i.signal_id} item={i} />))}</div>
        )}
      </Card>

      <details className="rounded-xl border border-wb-line bg-wb-surface p-3 text-[12px] text-wb-ink2">
        <summary className="cursor-pointer font-medium text-wb-ink">All recent items in this topic ({data.recent_items.length})</summary>
        <div className="mt-3 space-y-2">{data.recent_items.map((i) => (<ItemRow key={i.signal_id} item={i} />))}</div>
      </details>

      <p className="max-w-[70ch] text-[11px] italic text-wb-ink2">
        {data.gaps.evidence_contribution_coverage} {data.gaps.history_over_time}
      </p>
    </div>
  );
}
