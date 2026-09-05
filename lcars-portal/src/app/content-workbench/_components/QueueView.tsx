'use client';

// Queue — the default Pipeline sub-view (MSN-0363, brief §18): one
// priority-sorted flat list instead of the 4-column Board. Reads the same
// GET /api/content-workbench payload as Board/Today; Board (ContentBoard)
// is retained unchanged as the secondary "Board" toggle for anyone who
// wants the column view back.

import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui';
import { PILLAR_LABEL, STAGE_LABEL, rankBadgeStatus, type ContentItem, type Stage } from './shared';

const STAGE_PRIORITY: Record<Stage, number> = { proofing: 0, content_prep: 1, research: 2, capture: 3 };

function priorityScore(item: ContentItem): number {
  const stageWeight = STAGE_PRIORITY[item.stage] * 1000;
  const focusBoost = item.captain_focus ? -50 : 0;
  const rank = -(item.rank_score ?? 0);
  return stageWeight + focusBoost + rank;
}

function QueueRow({ item, onOpen }: { item: ContentItem; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-center gap-3 rounded-xl border border-wb-line bg-wb-surface p-3 text-left transition-colors hover:bg-wb-line/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
    >
      {item.rank_score !== null && <Badge status={rankBadgeStatus(item.rank_score)}>{item.rank_score.toFixed(0)}</Badge>}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          {item.pillar && <span className="text-[10.5px] font-medium uppercase tracking-wide text-wb-ink2">{PILLAR_LABEL[item.pillar] ?? item.pillar}</span>}
          <span className="text-[10px] text-wb-ink2">· {STAGE_LABEL[item.stage]}</span>
          {item.captain_focus && <span className="rounded-full bg-wb-warn/15 px-1.5 py-0.5 text-[10px] font-semibold text-wb-warn-on">★</span>}
        </div>
        <p className="truncate text-[13.5px] font-medium text-wb-ink">{item.title}</p>
      </div>
      <span aria-hidden className="text-[13px] text-wb-ink2">→</span>
    </button>
  );
}

export function QueueView({ refreshSignal, onOpenStudio }: { refreshSignal: number; onOpenStudio: (id: string) => void }) {
  const [items, setItems] = useState<ContentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch('/api/content-workbench');
        const data = await res.json();
        if (!res.ok) throw new Error(data.error ?? 'Failed to load queue');
        setItems(data.items ?? []);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load queue');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [refreshSignal]);

  if (loading) return <p className="text-sm text-wb-ink2">Loading queue…</p>;
  if (error) return <p className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">{error}</p>;
  if (items.length === 0) return <p className="text-sm text-wb-ink2">Nothing in the pipeline.</p>;

  const sorted = [...items].sort((a, b) => priorityScore(a) - priorityScore(b));

  return (
    <div className="flex flex-col gap-2">
      {sorted.map((item) => (<QueueRow key={item.id} item={item} onOpen={() => onOpenStudio(item.id)} />))}
    </div>
  );
}
