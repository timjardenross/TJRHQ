'use client';

import { useEffect, useState } from 'react';
import { Badge, Button, Input, Modal, Select } from '@/components/ui';
import { PILLAR_LABEL, DOMAIN_BADGE, type Domain } from './shared';

interface Signal {
  event_id: string;
  raw_title: string;
  raw_summary: string | null;
  source_name: string | null;
  pillar_key: string;
  pillar_name: string | null;
  rank_score: number;
  captain_focus: boolean;
  suggested_angle: string | null;
  domain: 'health' | 'operational';
  canonical_url: string | null;
}

function RankBadge({ score }: { score: number }) {
  const status = score > 0.8 ? 'success' : score > 0.7 ? 'warning' : 'error';
  return <Badge status={status}>{score.toFixed(2)}</Badge>;
}

function SignalCard({ signal, selected, onToggle }: { signal: Signal; selected: boolean; onToggle: () => void }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-lg border border-wb-line bg-wb-surface p-3">
      <div className="flex items-start gap-3">
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          aria-label={`Select signal: ${signal.raw_title}`}
          className="mt-1 h-4 w-4 rounded border-wb-line text-wb-sage-deep focus-visible:outline
            focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
        />
        <button
          type="button"
          onClick={() => setOpen(v => !v)}
          aria-expanded={open}
          className="min-w-0 flex-1 text-left focus-visible:outline focus-visible:outline-2
            focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
        >
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <RankBadge score={signal.rank_score} />
            <Badge status={DOMAIN_BADGE[signal.domain]}>{signal.domain === 'health' ? 'Health' : 'Operational'}</Badge>
            <span className="text-[11px] text-wb-ink2">
              {PILLAR_LABEL[signal.pillar_key] ?? signal.pillar_name ?? signal.pillar_key}
            </span>
            {signal.captain_focus && <span className="text-[11px] text-wb-warn-on">⭐ Captain Priority</span>}
            <span className="ml-auto shrink-0 text-[10px] text-wb-ink2">{open ? '▲' : '▼'}</span>
          </div>
          <p className="text-[13px] font-medium leading-snug text-wb-ink">{signal.raw_title}</p>
          {signal.suggested_angle && !open && (
            <p className="mt-0.5 line-clamp-2 text-[12px] italic text-wb-ink2">{signal.suggested_angle}</p>
          )}
        </button>
      </div>

      {open && (
        <div className="ml-7 mt-2 space-y-2 border-t border-wb-line pt-2 text-[12px]">
          {signal.suggested_angle && (
            <div>
              <p className="mb-0.5 text-[10px] uppercase tracking-wide text-wb-ink2">Suggested Angle</p>
              <p className="italic text-wb-ink">{signal.suggested_angle}</p>
            </div>
          )}
          {signal.raw_summary && (
            <div>
              <p className="mb-0.5 text-[10px] uppercase tracking-wide text-wb-ink2">Summary</p>
              <p className="text-wb-ink">{signal.raw_summary}</p>
            </div>
          )}
          <p className="text-[11px] text-wb-ink2">
            Source: {signal.source_name ?? '—'}
            {signal.canonical_url && (
              <>
                {' · '}
                <a href={signal.canonical_url} target="_blank" rel="noopener noreferrer" className="text-wb-sage-deep hover:underline">
                  View source ↗
                </a>
              </>
            )}
          </p>
        </div>
      )}
    </div>
  );
}

function BatchPreviewModal({
  signalIds,
  onClose,
  onCreated,
}: {
  signalIds: string[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);

  async function handleCreate() {
    setBusy(true);
    try {
      const res = await fetch('/api/content/signals-to-opportunities', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ signal_ids: signalIds }),
      });
      const data = await res.json();
      setResult(data);
      if (data.status === 'completed') onCreated();
    } catch (e) {
      setResult({ status: 'failed', error: e instanceof Error ? e.message : 'Request failed' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} title={`Batch Create (${signalIds.length} signal${signalIds.length === 1 ? '' : 's'})`}>
      <p className="mb-3 text-[13px] text-wb-ink2">
        Creates {signalIds.length} comms_content opportunities from the selected signals. This is
        all-or-nothing — if any signal fails validation, nothing is created.
      </p>

      {!result && (
        <div className="flex gap-2">
          <Button onClick={handleCreate} disabled={busy}>{busy ? 'Creating…' : '✓ Create All'}</Button>
          <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
        </div>
      )}

      {result && result.status === 'completed' && (
        <div className="space-y-2">
          <p className="text-[13px] text-wb-ok-on">
            ✓ Created {result.created} opportunit{result.created === 1 ? 'y' : 'ies'}. Find them in the Pipeline tab.
          </p>
          <Button variant="secondary" onClick={onClose}>Close</Button>
        </div>
      )}

      {result && result.status !== 'completed' && (
        <div className="space-y-2">
          <p className="text-[13px] text-wb-crit-on">✗ Batch creation failed. Reason: {result.error ?? 'Unknown error'}</p>
          <p className="text-[11px] text-wb-ink2">Entire batch rolled back — 0 opportunities created.</p>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={handleCreate}>Retry</Button>
            <Button variant="secondary" onClick={onClose}>Close</Button>
          </div>
        </div>
      )}
    </Modal>
  );
}

export function SignalsTab({ domain }: { domain: Domain }) {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [minScore, setMinScore] = useState(0.7);
  const [pillarFilter, setPillarFilter] = useState('all');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showPreview, setShowPreview] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams({ view: 'content_signals', days: '30', limit: '50' });
      if (domain !== 'both') qs.set('domain', domain);
      const res = await fetch(`/api/intelligence?${qs}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'Failed to load signals');
      setSignals(data.signals ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load signals');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    setSelected(new Set());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [domain]);

  const filtered = signals.filter(
    s => s.rank_score >= minScore && (pillarFilter === 'all' || s.pillar_key === pillarFilter)
  );
  const pillars = [...new Set(signals.map(s => s.pillar_key))];

  function toggle(id: string) {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-3">
        <Input
          label="Min rank score"
          type="number"
          min={0}
          max={1}
          step={0.05}
          value={minScore}
          onChange={e => setMinScore(Number(e.target.value))}
          className="w-20"
        />
        <Select label="Pillar" value={pillarFilter} onChange={e => setPillarFilter(e.target.value)} className="w-auto">
          <option value="all">All pillars</option>
          {pillars.map(p => (
            <option key={p} value={p}>{PILLAR_LABEL[p] ?? p}</option>
          ))}
        </Select>
        <div className="flex-1" />
        <Button onClick={() => setShowPreview(true)} disabled={selected.size === 0} size="sm">
          ➕ Batch Create ({selected.size} selected)
        </Button>
        <Button variant="secondary" onClick={() => setSelected(new Set())} disabled={selected.size === 0} size="sm">
          Clear Selection
        </Button>
      </div>

      {loading && <p className="text-sm text-wb-ink2">Loading signals…</p>}
      {error && <p className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">{error}</p>}
      {!loading && !error && filtered.length === 0 && (
        <p className="text-sm text-wb-ink2">No signals at or above rank {minScore.toFixed(2)}.</p>
      )}

      <div className="flex flex-col gap-2">
        {filtered.map(s => (
          <SignalCard key={s.event_id} signal={s} selected={selected.has(s.event_id)} onToggle={() => toggle(s.event_id)} />
        ))}
      </div>

      {showPreview && (
        <BatchPreviewModal
          signalIds={[...selected]}
          onClose={() => setShowPreview(false)}
          onCreated={() => {
            setSelected(new Set());
            load();
          }}
        />
      )}
    </div>
  );
}
