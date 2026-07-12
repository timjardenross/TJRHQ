'use client';

import { useEffect, useState } from 'react';
import { STATUS_LABEL, STATUS_COLOUR, PILLAR_LABEL, DOMAIN_BADGE, NEXT_TRIGGER, type Domain } from './shared';

interface PipelineItem {
  id: string;
  title: string;
  pillar: string | null;
  status: string;
  notes: string | null;
  sensitive: boolean;
  domain: 'health' | 'operational';
  created_at: string;
}

const COLUMNS = ['opportunity', 'draft', 'review', 'approved', 'ready_to_publish'];

function PipelineCard({ item, onAdvance, busy }: { item: PipelineItem; onAdvance: (id: string, trigger: string) => void; busy: boolean }) {
  const next = NEXT_TRIGGER[item.status];
  return (
    <div className="rounded-lcars border border-[#d9e1f0] bg-white/40 p-3 space-y-2">
      <div className="flex flex-wrap gap-1.5 items-center">
        <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium ${DOMAIN_BADGE[item.domain]}`}>
          {item.domain === 'health' ? 'Health' : 'Ops'}
        </span>
        {item.pillar && <span className="text-[10px] text-[#61718c]">{PILLAR_LABEL[item.pillar] ?? item.pillar}</span>}
        {item.sensitive && (
          <span className="text-[10px] text-red-500 border border-red-500/30 bg-red-500/5 rounded px-1.5 py-0.5">⚠ Sensitive</span>
        )}
      </div>
      <p className="text-sm font-medium text-[#18223a] leading-snug">{item.title}</p>
      {next && (
        <button
          type="button"
          onClick={() => onAdvance(item.id, next.trigger)}
          disabled={busy}
          aria-label={`${next.label}: move "${item.title}" to next stage`}
          className="text-xs border border-[#243b7a]/40 rounded px-2 py-1 text-[#243b7a] hover:bg-[#243b7a]/10 disabled:opacity-50 transition-colors w-full"
        >
          {next.label} →
        </button>
      )}
    </div>
  );
}

function PipelineColumn({
  status,
  items,
  onAdvance,
  busyId,
}: {
  status: string;
  items: PipelineItem[];
  onAdvance: (id: string, trigger: string) => void;
  busyId: string | null;
}) {
  const cls = STATUS_COLOUR[status] ?? '';
  return (
    <div role="region" aria-label={`${STATUS_LABEL[status]} stage, ${items.length} item${items.length === 1 ? '' : 's'}`} className="flex-1 min-w-[220px] flex flex-col gap-2">
      <div className={`rounded border px-2 py-1 text-center ${cls}`}>
        <p className="text-xs font-semibold uppercase tracking-wide">{STATUS_LABEL[status]}</p>
        <p className="text-[10px]">{items.length} item{items.length === 1 ? '' : 's'}</p>
      </div>
      <div className="flex flex-col gap-2" role="list" aria-label={`Items in ${STATUS_LABEL[status]}`}>
        {items.map(item => (
          <PipelineCard key={item.id} item={item} onAdvance={onAdvance} busy={busyId === item.id} />
        ))}
        {items.length === 0 && <p className="text-[10px] text-[#61718c]/60 text-center py-4">Empty</p>}
      </div>
    </div>
  );
}

export function PipelineTab({ domain }: { domain: Domain }) {
  const [items, setItems] = useState<PipelineItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams();
      if (domain !== 'both') qs.set('domain', domain);
      const res = await fetch(`/api/comms?${qs}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'Failed to load pipeline');
      setItems((data.items ?? []).filter((i: PipelineItem) => i.status !== 'published'));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load pipeline');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [domain]);

  async function advance(id: string, trigger: string) {
    setBusyId(id);
    setMsg(null);
    try {
      const res = await fetch(`/api/comms/${id}/advance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trigger }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'Failed to advance');
      setMsg(data.proposed ? 'Submitted for your approval in Decide — not published yet.' : `Moved to ${STATUS_LABEL[data.to]}`);
      await load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Failed to advance');
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {loading && <p className="text-sm text-[#61718c]">Loading pipeline…</p>}
      {error && <p className="rounded-lcars border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-500">{error}</p>}
      {msg && <p className="text-xs text-[#61718c]" role="status" aria-live="polite">{msg}</p>}

      {!loading && !error && (
        <div className="flex gap-3 overflow-x-auto pb-2">
          {COLUMNS.map(status => (
            <PipelineColumn
              key={status}
              status={status}
              items={items.filter(i => i.status === status)}
              onAdvance={advance}
              busyId={busyId}
            />
          ))}
        </div>
      )}
    </div>
  );
}
