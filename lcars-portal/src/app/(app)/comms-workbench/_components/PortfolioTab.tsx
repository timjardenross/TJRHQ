'use client';

import { useEffect, useState } from 'react';
import { PILLAR_LABEL, DOMAIN_BADGE, toMarkdown, toPlainText, download, type Domain } from './shared';

interface PublishedItem {
  id: string;
  title: string;
  pillar: string | null;
  body: string | null;
  domain: 'health' | 'operational';
  updated_at: string;
}

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
    return (
      <button type="button" onClick={() => setOpen(true)} className="text-xs border border-[#d9e1f0] rounded px-2 py-1 text-[#61718c] hover:text-[#18223a] transition-colors">
        Export
      </button>
    );
  }

  return (
    <div className="flex flex-wrap gap-1.5 items-center">
      <button type="button" onClick={() => copy('text')} className="text-xs border border-[#d9e1f0] rounded px-2 py-1 text-[#61718c] hover:text-[#18223a] transition-colors">
        📋 Copy text
      </button>
      <button type="button" onClick={() => copy('markdown')} className="text-xs border border-[#d9e1f0] rounded px-2 py-1 text-[#61718c] hover:text-[#18223a] transition-colors">
        📋 Copy markdown
      </button>
      <button type="button" onClick={() => exportFile('text')} className="text-xs border border-[#d9e1f0] rounded px-2 py-1 text-[#61718c] hover:text-[#18223a] transition-colors">
        💾 .txt
      </button>
      <button type="button" onClick={() => exportFile('markdown')} className="text-xs border border-[#d9e1f0] rounded px-2 py-1 text-[#61718c] hover:text-[#18223a] transition-colors">
        💾 .md
      </button>
      {copied && <span className="text-[10px] text-green-600" role="status">Copied {copied}</span>}
    </div>
  );
}

export function PortfolioTab({ domain }: { domain: Domain }) {
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
        const qs = new URLSearchParams({ status: 'published' });
        if (domain !== 'both') qs.set('domain', domain);
        const res = await fetch(`/api/comms?${qs}`);
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
  }, [domain]);

  const pillars = [...new Set(items.map(i => i.pillar).filter(Boolean))] as string[];
  const filtered = items.filter(
    i =>
      i.title.toLowerCase().includes(search.toLowerCase()) &&
      (pillarFilter === 'all' || i.pillar === pillarFilter)
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2 items-center">
        <input
          type="text"
          placeholder="Search by title…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="rounded border border-[#d9e1f0] bg-white/40 px-2 py-1 text-xs text-[#18223a] flex-1 min-w-[160px]"
        />
        <select
          value={pillarFilter}
          onChange={e => setPillarFilter(e.target.value)}
          className="rounded border border-[#d9e1f0] bg-white/40 px-2 py-1 text-xs text-[#18223a]"
        >
          <option value="all">All pillars</option>
          {pillars.map(p => (
            <option key={p} value={p}>{PILLAR_LABEL[p] ?? p}</option>
          ))}
        </select>
      </div>

      {loading && <p className="text-sm text-[#61718c]">Loading portfolio…</p>}
      {error && <p className="rounded-lcars border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-500">{error}</p>}
      {!loading && !error && filtered.length === 0 && <p className="text-sm text-[#61718c]">No published content yet.</p>}

      <div className="flex flex-col gap-2">
        {filtered.map(item => (
          <div key={item.id} className="rounded-lcars border border-[#d9e1f0] bg-white/30 p-3 space-y-1.5">
            <div className="flex flex-wrap gap-1.5 items-center">
              <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium ${DOMAIN_BADGE[item.domain]}`}>
                {item.domain === 'health' ? 'Health' : 'Ops'}
              </span>
              {item.pillar && <span className="text-[10px] text-[#61718c]">{PILLAR_LABEL[item.pillar] ?? item.pillar}</span>}
              <span className="text-[10px] text-[#61718c]/70">{item.updated_at.slice(0, 10)}</span>
            </div>
            <p className="text-sm font-medium text-[#18223a]">{item.title}</p>
            <ExportMenu item={item} />
          </div>
        ))}
      </div>
    </div>
  );
}
