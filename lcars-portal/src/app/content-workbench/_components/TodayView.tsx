'use client';

// Today — the default Content Workbench landing view (MSN-0363, brief §5).
// Answers "what needs me?" instead of defaulting to a 4-column board.
// Reads the same GET /api/content-workbench payload the Pipeline tab
// already uses — no new list endpoint, just a different client-side
// prioritisation of the same data. Never shows an empty stage merely
// because it exists (brief's own rule): every section here only renders
// when it has real content.

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui';
import { PILLAR_LABEL, rankBadgeStatus, type ContentItem, type Stage } from './shared';
import { Badge } from '@/components/ui';

interface Props {
  onOpenStudio: (contentId: string) => void;
  onOpenPipeline: () => void;
  refreshSignal: number;
}

function ReviewCard({ item, onOpen }: { item: ContentItem; onOpen: () => void }) {
  const checklist = (item.qa_checklist ?? {}) as Record<string, unknown>;
  const outstanding = (['accuracy', 'brand_voice', 'compliance', 'links_checked'] as const).filter((k) => checklist[k] !== true).length;
  return (
    <div className="space-y-1.5 rounded-xl border border-wb-warn/40 bg-wb-warn/5 p-3">
      <p className="text-[10.5px] font-semibold uppercase tracking-wide text-wb-warn-on">Review</p>
      <p className="text-[13.5px] font-medium leading-snug text-wb-ink">{item.title}</p>
      <p className="text-[12px] text-wb-ink2">
        {item.body ? 'Draft ready.' : 'Awaiting draft.'} {outstanding > 0 ? `${outstanding} QA item${outstanding === 1 ? '' : 's'} need attention.` : 'QA complete.'}
      </p>
      <Button size="sm" onClick={onOpen}>Review →</Button>
    </div>
  );
}

function DecideCard({ item, onOpen, kind }: { item: ContentItem; onOpen: () => void; kind: 'pursue' | 'publish' }) {
  return (
    <div className="space-y-1.5 rounded-xl border border-wb-sage/40 bg-wb-sage/5 p-3">
      <p className="text-[10.5px] font-semibold uppercase tracking-wide text-wb-sage-deep">Decide</p>
      <p className="text-[13.5px] font-medium leading-snug text-wb-ink">{item.title}</p>
      {kind === 'pursue' ? (
        <p className="text-[12px] text-wb-ink2">
          Opportunity score: {item.rank_score !== null ? item.rank_score.toFixed(0) : '—'} / 100
          {item.pillar && <> · {PILLAR_LABEL[item.pillar] ?? item.pillar}</>}
        </p>
      ) : (
        <p className="text-[12px] text-wb-ink2">Approved — ready to publish now or schedule.</p>
      )}
      <Button size="sm" onClick={onOpen}>Decide →</Button>
    </div>
  );
}

function stageOfCounts(items: ContentItem[]) {
  const counts: Record<Stage, number> = { capture: 0, research: 0, content_prep: 0, proofing: 0 };
  for (const i of items) counts[i.stage]++;
  return counts;
}

export function TodayView({ onOpenStudio, onOpenPipeline, refreshSignal }: Props) {
  const [items, setItems] = useState<ContentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/content-workbench');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'Failed to load');
      setItems(data.items ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [refreshSignal]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <p className="text-sm text-wb-ink2">Loading…</p>;
  if (error) return <p className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">{error}</p>;

  // Priority order (brief §5): blocked-on-TJR review items, then
  // high-value fresh opportunities awaiting pursue/ignore, then
  // ready-to-publish decisions.
  const reviewItems = items.filter((i) => i.stage === 'proofing' && i.status === 'review');
  const pursueItems = items
    .filter((i) => i.stage === 'capture' && i.status === 'opportunity' && !i.research_completed_at)
    .sort((a, b) => (b.rank_score ?? 0) - (a.rank_score ?? 0))
    .slice(0, 5);
  const publishItems = items.filter((i) => i.status === 'approved' || i.status === 'ready_to_publish');
  const scheduled = items
    .filter((i) => i.scheduled_for)
    .sort((a, b) => new Date(a.scheduled_for!).getTime() - new Date(b.scheduled_for!).getTime());

  const needsCount = reviewItems.length + pursueItems.length + publishItems.length;
  const counts = stageOfCounts(items);

  return (
    <div className="space-y-6">
      {needsCount === 0 && (
        <p className="rounded-xl border border-wb-line bg-wb-surface p-4 text-[13px] text-wb-ink2">
          Nothing needs you right now. Capture a new idea, or check Pipeline for in-progress work.
        </p>
      )}

      {needsCount > 0 && (
        <div>
          <p className="mb-2 text-[13px] font-semibold text-wb-ink">
            {needsCount} thing{needsCount === 1 ? '' : 's'} need{needsCount === 1 ? 's' : ''} you
          </p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {reviewItems.map((i) => (<ReviewCard key={i.id} item={i} onOpen={() => onOpenStudio(i.id)} />))}
            {pursueItems.map((i) => (<DecideCard key={i.id} item={i} kind="pursue" onOpen={() => onOpenStudio(i.id)} />))}
            {publishItems.map((i) => (<DecideCard key={i.id} item={i} kind="publish" onOpen={() => onOpenStudio(i.id)} />))}
          </div>
        </div>
      )}

      {scheduled.length > 0 && (
        <div>
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-wb-ink2">Coming Up</p>
          <div className="space-y-1.5 rounded-xl border border-wb-line bg-wb-surface p-3">
            {scheduled.slice(0, 5).map((i) => (
              <div key={i.id} className="flex items-center justify-between gap-2 text-[12.5px]">
                <span className="text-wb-ink">{i.title}</span>
                <span className="text-wb-ink2">
                  {new Date(i.scheduled_for!).toLocaleString('en-AU', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-wb-ink2">Pipeline Snapshot</p>
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-wb-line bg-wb-surface p-3 text-[12.5px] text-wb-ink2">
          <span>Ideas <Badge status={rankBadgeStatus(null)}>{counts.capture}</Badge></span>
          <span>Developing <Badge status={rankBadgeStatus(null)}>{counts.research + counts.content_prep}</Badge></span>
          <span>Review <Badge status={rankBadgeStatus(null)}>{counts.proofing}</Badge></span>
          <Button size="sm" variant="secondary" onClick={onOpenPipeline} className="ml-auto">Open Pipeline</Button>
        </div>
      </div>
    </div>
  );
}
