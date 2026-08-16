'use client';

/**
 * wb-native Engineering Queue sub-page (Captain's Chair). Rebuild of the
 * legacy `(app)/engineering-queue` page — same lib (`@/lib/engineering-queue`,
 * unchanged), wb-* markup + WorkbenchBadge instead of LCARS chrome +
 * StatusBadge. The legacy route now redirects here.
 *
 * Lifecycle → tone: reuses the same `toneClasses(LIFECYCLE_TONE[status])`
 * pattern captains-chair-workbench/page.tsx's own Engineering Queue panel
 * already uses for its counts-only view — here it also drives the filter
 * chips and the full-item badges. Genuine severity (blocked items,
 * approve/reject) stays on the separate, never-overridden state-tone system
 * (stateToneClasses ok/warn/crit) — see lib/departments.ts's own doctrine
 * comment: department/lifecycle identity and operational state are
 * deliberately two different colour systems.
 */

import { useEffect, useState } from 'react';
import { WorkbenchShell } from '@/components/ui';
import { WorkbenchBadge } from '@/components/WorkbenchBadge';
import { stateToneClasses, toneClasses } from '@/lib/departments';
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
      <div className={`rounded-lg border ${stateToneClasses('ok').border} ${stateToneClasses('ok').bg} p-4`}>
        <p className="text-[10px] uppercase tracking-[0.3em] text-wb-ink2">Next engineering action</p>
        <p className={`mt-1 font-serif text-lg font-bold ${stateToneClasses('ok').text}`}>Queue is clear</p>
        <p className="text-xs text-wb-ink2">Nothing is waiting on a decision right now.</p>
      </div>
    );
  }
  const urgent = item.blocked ? stateToneClasses('crit') : null;
  return (
    <div
      className={`rounded-lg border p-4 ${urgent ? `${urgent.border} ${urgent.bg}` : 'border-wb-line bg-wb-surface'}`}
    >
      <p className="text-[10px] uppercase tracking-[0.3em] text-wb-ink2">Next engineering action</p>
      <p className={`mt-1 font-serif text-lg font-bold leading-snug ${urgent ? urgent.text : 'text-wb-ink'}`}>
        {item.nextAction}
      </p>
      <p className="mt-1 text-sm text-wb-ink2">{item.title}</p>
      <div className="mt-2">
        <WorkbenchBadge label={LIFECYCLE_LABEL[item.lifecycle]} tone={LIFECYCLE_TONE[item.lifecycle]} />
      </div>
    </div>
  );
}

function Blockers({ data }: { data: EngineeringQueueData }) {
  if (!data.blockers.length) return null;
  const c = stateToneClasses('crit');
  return (
    <div className={`rounded-lg border ${c.border} ${c.bg} p-4`}>
      <p className={`mb-2 text-[10px] uppercase tracking-[0.3em] ${c.text}`}>Blockers</p>
      <ul className="flex flex-col gap-2">
        {data.blockers.map((b, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${c.dot}`} aria-hidden />
            <div>
              <p className={`font-semibold ${c.text}`}>{b.title}</p>
              <p className="text-xs text-wb-ink2">{b.detail}</p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ItemCard({
  item,
  acting,
  onDecision,
}: {
  item: QueueItem;
  acting: boolean;
  onDecision: (item: QueueItem, decision: 'approved' | 'rejected') => void;
}) {
  const canReview = item.lifecycle === 'awaiting_review' && item.source === 'build';
  const crit = stateToneClasses('crit');
  const ok = stateToneClasses('ok');
  return (
    <div className={`rounded-lg border p-3 ${item.blocked ? `${crit.border} ${crit.bg}` : 'border-wb-line bg-wb-surface'}`}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-semibold leading-snug text-wb-ink">{item.title}</p>
        <WorkbenchBadge
          label={item.blocked ? 'BLOCKED' : LIFECYCLE_LABEL[item.lifecycle]}
          tone={item.blocked ? 'operations' : LIFECYCLE_TONE[item.lifecycle]}
        />
      </div>
      {item.summary && <p className="mt-1 text-xs leading-relaxed text-wb-ink2">{item.summary}</p>}
      <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-wide text-wb-ink2">
        {item.priority && (
          <span className="rounded border border-wb-line px-1.5 py-0.5 font-mono">{item.priority.toUpperCase()}</span>
        )}
        {item.ageDays != null && <span>{item.ageDays}d old</span>}
        {item.prUrl && (
          <a
            href={item.prUrl}
            target="_blank"
            rel="noreferrer"
            className="text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep"
          >
            PR ↗
          </a>
        )}
        <span className="font-mono lowercase">{item.rawStatus}</span>
      </div>
      <p className="mt-2 text-xs text-wb-ink2">→ {item.nextAction}</p>
      {canReview && (
        <div className="mt-3 flex gap-2">
          <button
            disabled={acting}
            onClick={() => onDecision(item, 'approved')}
            className={`flex-1 rounded border ${ok.border} ${ok.bg} py-2 text-xs font-bold uppercase tracking-[0.15em] ${ok.text} transition-colors hover:bg-state-ok/20 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-state-ok`}
          >
            {acting ? 'Working…' : 'Approve'}
          </button>
          <button
            disabled={acting}
            onClick={() => onDecision(item, 'rejected')}
            className={`flex-1 rounded border ${crit.border} ${crit.bg} py-2 text-xs font-bold uppercase tracking-[0.15em] ${crit.text} transition-colors hover:bg-state-crit/20 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-state-crit`}
          >
            {acting ? 'Working…' : 'Reject'}
          </button>
        </div>
      )}
    </div>
  );
}

export default function CaptainsChairEngineeringQueuePage() {
  const [data, setData] = useState<EngineeringQueueData | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Lifecycle | 'all'>('all');
  const [actingId, setActingId] = useState<string | null>(null);
  const [flash, setFlash] = useState<{ message: string; ok: boolean } | null>(null);

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
    setActingId(item.id);
    const res = await setQueueItemStatus(item, decision);
    setActingId(null);
    setFlash({
      message: res.ok ? `${item.title} ${decision}.` : `Could not ${decision}: ${res.error}`,
      ok: res.ok,
    });
    setTimeout(() => setFlash(null), 3000);
    if (res.ok) load();
  }

  const items = data?.items ?? [];
  const visible = filter === 'all' ? items.filter((i) => i.lifecycle !== 'rejected') : items.filter((i) => i.lifecycle === filter);
  const flashTone = flash ? stateToneClasses(flash.ok ? 'ok' : 'crit') : null;

  const right = (
    <span className="text-[11px] text-wb-ink2">
      {loading ? 'Loading…' : data?.isLive ? '● Live · build inbox + delivery' : '○ No engineering data'}
    </span>
  );

  return (
    <WorkbenchShell
      title="Engineering Queue"
      eyebrow="Captain's Chair"
      tagline="USS TJR · Engineering Queue · build inbox + delivery — governed approve/reject, nothing auto-routes without your say."
      back={{ href: '/captains-chair-workbench', label: "Captain's Chair" }}
      right={right}
    >
      <div className="flex flex-col gap-4">
        <NextActionHero item={data?.nextAction ?? null} />
        {data && <Blockers data={data} />}

        {data && (
          <div className="flex gap-2 overflow-x-auto pb-1">
            <button
              onClick={() => setFilter('all')}
              className={`shrink-0 rounded-md border px-3 py-1.5 text-xs font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep ${
                filter === 'all' ? 'border-wb-sage-deep bg-wb-sage-deep/10 text-wb-sage-deep' : 'border-wb-line text-wb-ink2'
              }`}
            >
              All ({items.filter((i) => i.lifecycle !== 'rejected').length})
            </button>
            {LIFECYCLE_ORDER.map((lc) => {
              const c = toneClasses(LIFECYCLE_TONE[lc]);
              return (
                <button
                  key={lc}
                  onClick={() => setFilter(lc)}
                  className={`shrink-0 rounded-md border px-3 py-1.5 text-xs font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep ${
                    filter === lc ? `${c.border} ${c.bg} ${c.text}` : 'border-wb-line text-wb-ink2'
                  }`}
                >
                  {LIFECYCLE_LABEL[lc]} ({data.counts[lc]})
                </button>
              );
            })}
          </div>
        )}

        {flash && flashTone && (
          <div className={`rounded-lg border px-4 py-2.5 text-xs ${flashTone.border} ${flashTone.bg} ${flashTone.text}`}>
            {flash.message}
          </div>
        )}

        <div className="flex flex-col gap-2.5">
          {loading ? (
            <p className="text-sm italic text-wb-ink2">Loading queue…</p>
          ) : visible.length === 0 ? (
            <p className="rounded-lg border border-wb-line bg-wb-bg p-4 text-sm italic text-wb-ink2">
              Nothing in this view.
            </p>
          ) : (
            visible.map((it) => (
              <ItemCard key={it.id} item={it} acting={actingId === it.id} onDecision={onDecision} />
            ))
          )}
        </div>
      </div>
    </WorkbenchShell>
  );
}
