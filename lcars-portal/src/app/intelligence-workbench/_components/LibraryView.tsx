'use client';

// LIBRARY — historical assessments, past-briefed items, REFERENCE items and
// resolved watch items. Search + date range + sector + disposition filters,
// paginated (40/page) so this never becomes an unbounded raw dump. Links
// into brief/[id] (still live, unchanged by this uplift) where a brief_id
// exists.

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Badge, Button, Input, Select } from '@/components/ui';

interface LibraryItem {
  event_id: string;
  title: string;
  canonical_url: string | null;
  disposition: string;
  sector: string | null;
  geography: string | null;
  confidence_level: string;
  corroboration: number;
  published_at: string | null;
  brief_id: string | null;
}

const DISPOSITION_OPTIONS = [
  { value: '', label: 'All (excl. hidden)' },
  { value: 'BRIEF', label: 'Worth knowing' },
  { value: 'WATCH', label: 'Watching' },
  { value: 'REFERENCE', label: 'Background' },
  { value: 'UNCLASSIFIED', label: 'Unclassified (pre-backfill)' },
  { value: 'SUPPRESS', label: 'Hidden (debug)' },
];

function dispositionBadge(d: string) {
  if (d === 'ESCALATE') return <Badge status="error">Needs you</Badge>;
  if (d === 'BRIEF') return <Badge status="success">Worth knowing</Badge>;
  if (d === 'WATCH') return <Badge status="warning">Watching</Badge>;
  if (d === 'SUPPRESS') return <Badge status="neutral">Hidden</Badge>;
  if (d === 'UNCLASSIFIED') return <Badge status="neutral">Unclassified</Badge>;
  return <Badge status="info">Background</Badge>;
}

export function LibraryView() {
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [q, setQ] = useState('');
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');
  const [disposition, setDisposition] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const sp = new URLSearchParams();
    if (q) sp.set('q', q);
    if (since) sp.set('since', new Date(since).toISOString());
    if (until) sp.set('until', new Date(until).toISOString());
    if (disposition) sp.set('disposition', disposition);
    sp.set('page', String(page));
    fetch(`/api/intelligence-workbench/library?${sp.toString()}`)
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw new Error(d?.error || 'Failed to load');
        if (!cancelled) { setItems(d.items ?? []); setTotal(d.total ?? 0); setError(null); }
      })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, since, until, disposition, page]);

  const pageCount = Math.max(1, Math.ceil(total / 40));

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-4">
        <Input placeholder="Search title…" value={q} onChange={(e) => { setPage(0); setQ(e.target.value); }} />
        <Input type="date" value={since} onChange={(e) => { setPage(0); setSince(e.target.value); }} aria-label="Since date" />
        <Input type="date" value={until} onChange={(e) => { setPage(0); setUntil(e.target.value); }} aria-label="Until date" />
        <Select value={disposition} onChange={(e) => { setPage(0); setDisposition(e.target.value); }} aria-label="Status filter">
          {DISPOSITION_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </Select>
      </div>

      {loading && <p className="text-[13px] text-wb-ink2">Loading library…</p>}
      {error && <p className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-[13px] text-wb-crit-on">Unavailable: {error}</p>}

      {!loading && !error && items.length === 0 && (
        <p className="text-[13px] text-wb-ink2">No historical items match these filters.</p>
      )}

      {!loading && !error && items.length > 0 && (
        <>
          <div className="space-y-2">
            {items.map((it) => (
              <div key={it.event_id} className="flex flex-col gap-1 rounded-lg border border-wb-line bg-wb-surface p-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  {it.canonical_url ? (
                    <a href={it.canonical_url} target="_blank" rel="noopener noreferrer" className="block truncate text-[13px] font-medium text-wb-ink underline decoration-dotted hover:text-wb-sage-deep">
                      {it.title}
                    </a>
                  ) : (
                    <p className="truncate text-[13px] font-medium text-wb-ink">{it.title}</p>
                  )}
                  <p className="text-[11px] text-wb-ink2">
                    {it.sector ? it.sector.replace(/_/g, ' ') : 'Unknown sector'}
                    {it.geography ? ` · ${it.geography}` : ''}
                    {it.published_at ? ` · ${new Date(it.published_at).toLocaleDateString()}` : ''}
                    {it.corroboration > 0 ? ` · ${it.corroboration} source${it.corroboration === 1 ? '' : 's'}` : ''}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {dispositionBadge(it.disposition)}
                  {it.brief_id && (
                    <Link href={`/intelligence-workbench/brief/${it.brief_id}`} className="text-[11.5px] text-wb-sage-deep hover:underline">
                      Evidence →
                    </Link>
                  )}
                </div>
              </div>
            ))}
          </div>
          <div className="flex items-center justify-between text-[12px] text-wb-ink2">
            <span>Page {page + 1} of {pageCount}</span>
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>← Prev</Button>
              <Button size="sm" variant="secondary" disabled={page + 1 >= pageCount} onClick={() => setPage((p) => p + 1)}>Next →</Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
