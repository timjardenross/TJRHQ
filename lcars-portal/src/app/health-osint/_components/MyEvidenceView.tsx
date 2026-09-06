'use client';

// My Evidence — persistent per-topic evidence-position view (Phase 2
// Three-Workbench Simplification mission, "core long-term value"). Topics
// are derived from health_domain via lib/healthOsintTopics.ts, not a new
// taxonomy table (none exists) — see /api/health-osint/topics for detail.

import { useEffect, useState } from 'react';
import { Badge, toneToStatus } from '@/components/ui';
import { STRENGTH_LABEL, TREND_LABEL, strengthTone, type TopicSummary } from './shared';

interface Props {
  onOpenTopic: (topicKey: string) => void;
}

export function MyEvidenceView({ onOpenTopic }: Props) {
  const [topics, setTopics] = useState<TopicSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/health-osint/topics')
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw new Error(d?.error || 'Failed to load');
        setTopics(d.topics ?? []);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-sm text-wb-ink2">Loading…</p>;
  if (error) return <p className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">{error}</p>;
  if (!topics || topics.length === 0) {
    return <p className="rounded-xl border border-wb-line bg-wb-surface p-4 text-[13px] text-wb-ink2">No evidence recorded yet.</p>;
  }

  return (
    <div className="space-y-2">
      {topics.map((t) => (
        <button
          key={t.topic_key}
          type="button"
          onClick={() => onOpenTopic(t.topic_key)}
          className="flex w-full flex-col gap-1 rounded-xl border border-wb-line bg-wb-surface p-3 text-left transition-colors hover:border-wb-sage-deep sm:flex-row sm:items-center sm:justify-between"
        >
          <div className="flex items-center gap-2">
            <span className="text-[13.5px] font-medium text-wb-ink">{t.topic_label}</span>
            {t.safety_relevant && <Badge status="error">Safety</Badge>}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[12px] text-wb-ink2">
            <Badge status={toneToStatus(strengthTone(t.strength))}>{STRENGTH_LABEL[t.strength]}</Badge>
            <span>{TREND_LABEL[t.trend]}</span>
            {t.last_changed && <span>· Last changed {new Date(t.last_changed).toLocaleDateString()}</span>}
          </div>
        </button>
      ))}
    </div>
  );
}
