'use client';

import { useEffect, useState } from 'react';
import { StatusBadge } from '@/components/StatusBadge';
import {
  fetchEngineeringQueue,
  setQueueItemStatus,
  LIFECYCLE_ORDER,
  LIFECYCLE_LABEL,
  LIFECYCLE_TONE,
  type EngineeringQueueData,
  type Lifecycle,
  type QueueItem,
} from '@/lib/engineering-queue';

function NextActionHero({ item }: { item: QueueItem | null }) {
  if (!item) {
    return (
      <div className="rounded-lcars border border-status/40 bg-status/5 p-4">
        <p className="text-[10px] uppercase tracking-[0.3em] text-lcars-muted">Next engineering action</p>
        <p className="mt-1 font-sans text-lg font-bold text-status">Queue is clear</p>
        <p className="text-xs text-lcars-muted">Nothing is waiting on a decision right now.</p>
      </div>
    );
  }
  return (
    <div className="rounded-lcars border border-engineering/50 bg-engineering/5 p-4">
      <p className="text-[10px] uppercase tracking-[0.3em] text-lcars-muted">Next engineering action</p>
      <p className="mt-1 font-sans text-lg font-bold text-engineering leading-snug">{item.nextAction}</p>
      <p className="mt-1 text-sm text-lcars-text/80">{item.title}</p>
      <div className="mt-2">
        <StatusBadge label={LIFECYCLE_LABEL[item.lifecycle]} tone={LIFECYCLE_TONE[item.lifecycle]} />
      </div>
    </div>
  );
}

function Blockers({ data }: { data: EngineeringQueueData }) {
  if (!data.blockers.length) return null;
  return (
    <div className="rounded-lcars border border-operations/40 bg-operations/10 p-4">
      <p className="mb-2 text-[10px] uppercase tracking-[0.3em] text-operations">Blockers</p>
      <ul className="flex flex-col gap-2">
        {data.blockers.map((b, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-operations" />
            <div>
              <p className="font-semibold text-operations">{b.title}</p>
              <p className="text-xs text-lcars-muted">{b.detail}</p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ItemCard({ item, onDecision }: { item: QueueItem; onDecision: (i: QueueItem, d: 'approved' | 'rejected') => void }) {
  const canReview = item.lifecycle === 'awaiting_review' && item.source === 'build';
  return (
    <div className={`rounded-lcars border ${item.blocked ? 'border-operations/50' : 'border-edge'} bg-panel-2/60 p-3`}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-semibold text-lcars-text leading-snug">{item.title}</p>
        <StatusBadge label={item.blocked ? 'BLOCKED' : LIFECYCLE_LABEL[item.lifecycle]} tone={item.blocked ? 'operations' : LIFECYCLE_TONE[item.lifecycle]} />
      </div>
      {item.summary && <p className="mt-1 text-xs text-lcars-muted leading-relaxed">{item.summary}</p>}
      <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-wide text-lcars-muted">
        {item.priority && <span className="rounded border border-edge px-1.5 py-0.5 font-mono">{item.priority.toUpperCase()}</span>}
        {item.ageDays != null && <span>{item.ageDays}d old</span>}
        {item.prUrl && (
          <a href={item.prUrl} target="_blank" rel="noreferrer" className="text-medical hover:underline">PR ↗</a>
        )}
        <span className="font-mono lowercase">{item.rawStatus}</span>
      </div>
      <p className="mt-2 text-xs text-engineering/90">→ {item.nextAction}</p>
      {canReview && (
        <div className="mt-3 flex gap-2">
          <button
            onClick={() => onDecision(item, 'approved')}
            className="flex-1 rounded-lcars border border-status/50 bg-status/10 py-2 text-xs font-bold uppercase tracking-[0.15em] text-status hover:bg-status/20"
          >
            Approve
          </button>
          <button
            onClick={() => onDecision(item, 'rejected')}
            className="flex-1 rounded-lcars border border-operations/50 bg-operations/10 py-2 text-xs font-bold uppercase tracking-[0.15em] text-operations hover:bg-operations/20"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  );
}

export default function EngineeringQueuePage() {
  const [data, setData] = useState<EngineeringQueueData | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Lifecycle | 'all'>('all');
  const [flash, setFlash] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    const d = await fetchEngineeringQueue();
    setData(d);
    setLoading(false);
  }
  useEffect(() => {
    load();
  }, []);

  async function onDecision(item: QueueItem, decision: 'approved' | 'rejected') {
    const res = await setQueueItemStatus(item, decision);
    setFlash(res.ok ? `${item.title} ${decision}.` : `Could not ${decision}: ${res.error}`);
    setTimeout(() => setFlash(null), 3000);
    if (res.ok) load();
  }

  const items = data?.items ?? [];
  const visible = filter === 'all' ? items.filter((i) => i.lifecycle !== 'rejected') : items.filter((i) => i.lifecycle === filter);

  return (
    <div className="mx-auto flex max-w-[640px] flex-col gap-4">
      <header>
        <p className="text-[10px] uppercase tracking-[0.3em] text-lcars-muted">Engineering</p>
        <h1 className="font-sans text-2xl font-bold text-engineering">Engineering Queue</h1>
        <p className="text-xs text-lcars-muted">
          {loading ? 'Loading…' : data?.isLive ? '● Live · build inbox + delivery' : '○ No engineering data'}
        </p>
      </header>

      <NextActionHero item={data?.nextAction ?? null} />
      {data && <Blockers data={data} />}

      {/* Lifecycle counts / filter */}
      {data && (
        <div className="flex gap-2 overflow-x-auto pb-1">
          <button
            onClick={() => setFilter('all')}
            className={`shrink-0 rounded-lcars border px-3 py-1.5 text-xs font-semibold ${filter === 'all' ? 'border-engineering bg-engineering/20 text-engineering' : 'border-edge text-lcars-muted'}`}
          >
            All ({items.filter((i) => i.lifecycle !== 'rejected').length})
          </button>
          {LIFECYCLE_ORDER.map((lc) => (
            <button
              key={lc}
              onClick={() => setFilter(lc)}
              className={`shrink-0 rounded-lcars border px-3 py-1.5 text-xs font-semibold ${filter === lc ? 'border-engineering bg-engineering/20 text-engineering' : 'border-edge text-lcars-muted'}`}
            >
              {LIFECYCLE_LABEL[lc]} ({data.counts[lc]})
            </button>
          ))}
        </div>
      )}

      {flash && (
        <div className="rounded-lcars border border-command/40 bg-command/10 px-4 py-2.5 text-xs text-command">{flash}</div>
      )}

      {/* Items */}
      <div className="flex flex-col gap-2.5">
        {loading ? (
          <p className="text-sm text-lcars-muted italic">Loading queue…</p>
        ) : visible.length === 0 ? (
          <p className="rounded-lcars border border-edge bg-panel/40 p-4 text-sm text-lcars-muted italic">
            Nothing in this view.
          </p>
        ) : (
          visible.map((it) => <ItemCard key={it.id} item={it} onDecision={onDecision} />)
        )}
      </div>
    </div>
  );
}
