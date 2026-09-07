'use client';

// Library — retained studies, evidence summaries, historical shifts,
// reference/background research (Phase 2 mission spec). Search + filter by
// topic/evidence-contribution/date/strength; does not default to browsing
// every ingested paper (server applies a 1-year lookback + page size cap
// when no explicit date range is given).

import { useEffect, useState } from 'react';
import { Select } from '@/components/ui';
import { EVIDENCE_CONTRIBUTION_LABEL, type EvidenceItem } from './shared';

const EVIDENCE_CONTRIBUTION_OPTIONS = Object.keys(EVIDENCE_CONTRIBUTION_LABEL);
const STRENGTH_OPTIONS = [
  { value: 'STRONG', label: 'Strong' },
  { value: 'MODERATE', label: 'Moderate' },
  { value: 'LIMITED', label: 'Limited' },
];

function Row({ item }: { item: EvidenceItem }) {
  return (
    <div className="border-b border-wb-line pb-2 text-[12.5px] last:border-0">
      <div className="font-semibold text-wb-ink">
        {item.source_url ? (
          <a href={item.source_url} target="_blank" rel="noreferrer" className="hover:underline">{item.title}</a>
        ) : item.title}
      </div>
      <div className="text-wb-ink2">
        {item.topic_label} · {item.source_name}
        {item.study_design && <> · {item.study_design}</>}
        {item.published_at && <> · Published {new Date(item.published_at).toLocaleDateString()}</>}
        {item.evidence_contribution && <> · {EVIDENCE_CONTRIBUTION_LABEL[item.evidence_contribution] ?? item.evidence_contribution}</>}
      </div>
      {item.summary && <div className="mt-1 max-w-[70ch] text-wb-ink2">{item.summary}</div>}
    </div>
  );
}

export function LibraryView() {
  const [q, setQ] = useState('');
  const [evidenceContribution, setEvidenceContribution] = useState('');
  const [strength, setStrength] = useState('');
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');
  const [page, setPage] = useState(0);
  const [items, setItems] = useState<EvidenceItem[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (q.trim()) params.set('q', q.trim());
    if (evidenceContribution) params.set('evidence_contribution', evidenceContribution);
    if (strength) params.set('strength', strength);
    if (since) params.set('since', new Date(since).toISOString());
    if (until) params.set('until', new Date(until).toISOString());
    params.set('page', String(page));

    const t = setTimeout(() => {
      fetch(`/api/health-osint/library?${params.toString()}`)
        .then(async (r) => {
          const d = await r.json();
          if (!r.ok) throw new Error(d?.error || 'Failed to load');
          setItems(d.items ?? []);
          setTotal(d.total ?? 0);
          setHasMore(!!d.has_more);
          setError(null);
        })
        .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
        .finally(() => setLoading(false));
    }, 250); // debounce free-text search
    return () => clearTimeout(t);
  }, [q, evidenceContribution, strength, since, until, page]);

  function resetPage<T>(setter: (v: T) => void) {
    return (v: T) => { setter(v); setPage(0); };
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={q}
          onChange={(e) => resetPage(setQ)(e.target.value)}
          placeholder="Search title or summary…"
          className="min-w-[200px] flex-1 rounded border border-wb-line bg-transparent px-2 py-1.5 text-[12.5px] text-wb-ink"
          aria-label="Search library"
        />
        <Select value={evidenceContribution} onChange={(e) => resetPage(setEvidenceContribution)(e.target.value)} aria-label="Filter by what changed">
          <option value="">All types</option>
          {EVIDENCE_CONTRIBUTION_OPTIONS.map((k) => (<option key={k} value={k}>{EVIDENCE_CONTRIBUTION_LABEL[k]}</option>))}
        </Select>
        <Select value={strength} onChange={(e) => resetPage(setStrength)(e.target.value)} aria-label="Filter by evidence strength">
          <option value="">All strengths</option>
          {STRENGTH_OPTIONS.map((o) => (<option key={o.value} value={o.value}>{o.label}</option>))}
        </Select>
        <input type="date" value={since} onChange={(e) => resetPage(setSince)(e.target.value)} className="rounded border border-wb-line bg-transparent px-2 py-1.5 text-[12px] text-wb-ink" aria-label="Since date" />
        <input type="date" value={until} onChange={(e) => resetPage(setUntil)(e.target.value)} className="rounded border border-wb-line bg-transparent px-2 py-1.5 text-[12px] text-wb-ink" aria-label="Until date" />
      </div>

      {error && <p className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">{error}</p>}

      <div className="rounded-xl border border-wb-line bg-wb-surface p-3">
        {loading ? (
          <p className="text-sm text-wb-ink2">Loading…</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-wb-ink2">No matching evidence. Try widening a filter.</p>
        ) : (
          <div className="space-y-2">{items.map((i) => (<Row key={i.signal_id} item={i} />))}</div>
        )}
      </div>

      <div className="flex items-center justify-between text-[12px] text-wb-ink2">
        <span>{total} total</span>
        <div className="flex gap-2">
          <button type="button" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))} className="rounded border border-wb-line px-2 py-1 disabled:opacity-40">Prev</button>
          <button type="button" disabled={!hasMore} onClick={() => setPage((p) => p + 1)} className="rounded border border-wb-line px-2 py-1 disabled:opacity-40">Next</button>
        </div>
      </div>
    </div>
  );
}
