'use client';

// Portfolio — the "where finished content lives" view, brought into the
// Content Workbench so the old Communications Workbench (now unlisted from
// /workbenches) isn't the only place to see or export what's actually been
// published. Reads the same GET /api/comms?status=published every other
// published-content view already reads (comms_content is the single source
// of truth) — this is a read-only, additive second consumer of that route,
// not a fork of it. No domain toggle here on purpose: Content Workbench
// doesn't split health/operational, Portfolio here is just "everything
// published."

import { useEffect, useState } from 'react';
import { Badge, Button, Input, Select } from '@/components/ui';
import { PILLAR_LABEL, toMarkdown, toPlainText, download, type PublishedItem } from './shared';

function ExportMenu({ item }: { item: PublishedItem }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  async function copy(format: 'markdown' | 'text') {
    const content = format === 'markdown' ? toMarkdown(item) : toPlainText(item);
    await navigator.clipboard.writeText(content);
    setCopied(format);
    setTimeout(() => setCopied(null), 2000);
  }

  function exportFile(format: 'markdown' | 'text') {
    const content = format === 'markdown' ? toMarkdown(item) : toPlainText(item);
    const ext = format === 'markdown' ? 'md' : 'txt';
    download(content, `${item.id}.${ext}`);
  }

  if (!open) {
    return <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>Export</Button>;
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Button size="sm" variant="secondary" onClick={() => copy('text')}>📋 Copy text</Button>
      <Button size="sm" variant="secondary" onClick={() => copy('markdown')}>📋 Copy markdown</Button>
      <Button size="sm" variant="secondary" onClick={() => exportFile('text')}>💾 .txt</Button>
      <Button size="sm" variant="secondary" onClick={() => exportFile('markdown')}>💾 .md</Button>
      {copied && <span className="text-[11px] text-wb-ok-on" role="status">Copied {copied}</span>}
    </div>
  );
}

function PortfolioCard({ item }: { item: PublishedItem }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="space-y-1.5 rounded-xl border border-wb-line bg-wb-surface p-3 shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
      >
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge status="success">✓ Published</Badge>
          {item.pillar && (
            <span className="rounded-full bg-wb-line px-2 py-0.5 text-[10.5px] font-medium text-wb-ink2">
              {PILLAR_LABEL[item.pillar] ?? item.pillar}
            </span>
          )}
          <span className="text-[11px] text-wb-ink2/70">{item.updated_at.slice(0, 10)}</span>
          <span className="ml-auto text-[10px] text-wb-ink2">{open ? '▲' : '▼'}</span>
        </div>
        <p className="text-[13.5px] font-medium leading-snug text-wb-ink">{item.title}</p>
      </button>

      {open && item.body && (
        <div className="whitespace-pre-wrap rounded-md border border-wb-line bg-wb-bg p-3 text-[13px] leading-relaxed text-wb-ink">
          {item.body}
        </div>
      )}
      {open && !item.body && <p className="text-[12px] text-wb-ink2">No stored body for this item.</p>}

      <ExportMenu item={item} />
    </div>
  );
}

export function PortfolioTab() {
  const [items, setItems] = useState<PublishedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [pillarFilter, setPillarFilter] = useState('all');

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch('/api/comms?status=published');
        const data = await res.json();
        if (!res.ok) throw new Error(data.error ?? 'Failed to load portfolio');
        setItems(data.items ?? []);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load portfolio');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const pillars = [...new Set(items.map((i) => i.pillar).filter(Boolean))] as string[];
  const filtered = items.filter(
    (i) =>
      i.title.toLowerCase().includes(search.toLowerCase()) &&
      (pillarFilter === 'all' || i.pillar === pillarFilter),
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-2">
        <Input placeholder="Search by title…" value={search} onChange={(e) => setSearch(e.target.value)} className="min-w-[160px] flex-1" />
        <Select value={pillarFilter} onChange={(e) => setPillarFilter(e.target.value)} className="w-auto">
          <option value="all">All pillars</option>
          {pillars.map((p) => (
            <option key={p} value={p}>{PILLAR_LABEL[p] ?? p}</option>
          ))}
        </Select>
      </div>

      {loading && <p className="text-sm text-wb-ink2">Loading portfolio…</p>}
      {error && <p className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">{error}</p>}
      {!loading && !error && filtered.length === 0 && <p className="text-sm text-wb-ink2">No published content yet.</p>}

      <div className="flex flex-col gap-2">
        {filtered.map((item) => (
          <PortfolioCard key={item.id} item={item} />
        ))}
      </div>
    </div>
  );
}
