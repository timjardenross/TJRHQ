'use client';

import { useEffect, useState } from 'react';
import { StatusBadge } from '@/components/StatusBadge';
import { DEPARTMENTS, toneClasses } from '@/lib/departments';
import { knowledgeArticles as mockArticles } from '@/lib/mockData';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import type { KnowledgeArticle } from '@/lib/types';

// Map Supabase knowledge_documents to KnowledgeArticle shape
function mapDoc(doc: Record<string, string>): KnowledgeArticle {
  return {
    id: doc.id ?? doc.title,
    title: doc.title ?? '(untitled)',
    category: doc.category ?? 'General',
    owner: doc.owner ?? doc.created_by ?? '—',
    updated: doc.updated_at ? new Date(doc.updated_at).toLocaleDateString('en-AU') : '—',
    excerpt: doc.summary ?? doc.description ?? '',
    department: (doc.department as KnowledgeArticle['department']) ?? 'command',
  };
}

// ── Shared primitives ─────────────────────────────────────────────────────────

function Panel({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-lcars border border-edge bg-panel/60 p-3 ${className}`}>
      {children}
    </div>
  );
}

function SectionHeader({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="text-[11px] font-bold uppercase tracking-[0.25em] text-lcars-muted">{title}</h2>
      {action}
    </div>
  );
}

// ── Category sidebar ──────────────────────────────────────────────────────────

const CATEGORY_TONE: Record<string, string> = {
  'Architecture Decision Record': 'text-command border-command',
  'Governance': 'text-operations border-operations',
  'Engineering': 'text-engineering border-engineering',
  'Science': 'text-science border-science',
  'Operations': 'text-operations border-operations',
  'Medical': 'text-medical border-medical',
};

function CategoryList({
  articles,
  activeCategory,
  onSelect,
}: {
  articles: KnowledgeArticle[];
  activeCategory: string | null;
  onSelect: (cat: string | null) => void;
}) {
  const map = new Map<string, number>();
  for (const a of articles) {
    map.set(a.category, (map.get(a.category) ?? 0) + 1);
  }

  return (
    <Panel>
      <SectionHeader title="Categories" />
      <ul className="flex flex-col gap-2">
        <li>
          <button
            onClick={() => onSelect(null)}
            className={`w-full flex items-center justify-between rounded-md border px-3 py-2 text-left transition-colors ${
              activeCategory === null
                ? 'border-command bg-command/10 text-command'
                : 'border-edge bg-panel-2/60 text-lcars-muted hover:border-edge/80'
            }`}
          >
            <span className="text-[11px] font-semibold uppercase tracking-wide">All</span>
            <span className="font-mono text-xs font-bold">{articles.length}</span>
          </button>
        </li>
        {Array.from(map.entries()).map(([cat, count]) => {
          const cls = CATEGORY_TONE[cat] ?? 'text-lcars-muted border-edge';
          const active = activeCategory === cat;
          return (
            <li key={cat}>
              <button
                onClick={() => onSelect(active ? null : cat)}
                className={`w-full flex items-center justify-between rounded-md border px-3 py-2 text-left transition-colors ${
                  active
                    ? `${cls.split(' ')[1]} bg-space/60`
                    : 'border-edge bg-panel-2/60 hover:border-edge/80'
                }`}
              >
                <span className={`text-[11px] font-semibold uppercase tracking-wide ${cls.split(' ')[0]}`}>
                  {cat}
                </span>
                <span className={`font-mono text-xs font-bold ${cls.split(' ')[0]}`}>{count}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

// ── Article card (expandable) ─────────────────────────────────────────────────

function ArticleCard({ article }: { article: KnowledgeArticle }) {
  const [expanded, setExpanded] = useState(false);
  const dept = DEPARTMENTS[article.department] ?? DEPARTMENTS.command;

  return (
    <article
      className="flex flex-col gap-2 rounded-lcars border border-edge bg-panel-2/60 p-3 transition-colors hover:border-edge/80"
      style={{ borderLeftColor: dept.hex, borderLeftWidth: 4 }}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="font-mono text-xs text-lcars-muted">{article.id}</span>
        <span className={`text-[10px] uppercase tracking-wider ${dept.text}`}>
          {article.category}
        </span>
      </div>
      <h3 className="text-sm font-semibold normal-case text-lcars-text">{article.title}</h3>

      {article.excerpt && (
        <>
          <p className={`text-xs leading-relaxed text-lcars-muted ${expanded ? '' : 'line-clamp-2'}`}>
            {article.excerpt}
          </p>
          {article.excerpt.length > 120 && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="self-start text-[10px] uppercase tracking-[0.15em] text-command hover:opacity-70"
            >
              {expanded ? 'Show less' : 'Read more'}
            </button>
          )}
        </>
      )}

      <div className="mt-auto flex items-center justify-between text-[10px] text-lcars-muted">
        <span>{article.owner}</span>
        <span className="font-mono">Updated {article.updated}</span>
      </div>
    </article>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function KnowledgeBasePage() {
  const [articles, setArticles]         = useState<KnowledgeArticle[]>(mockArticles);
  const [isLive, setIsLive]             = useState(false);
  const [activeCategory, setCategory]   = useState<string | null>(null);
  const [search, setSearch]             = useState('');

  useEffect(() => {
    async function load() {
      const supabase = createSupabaseBrowserClient();
      const { data } = await supabase
        .from('knowledge_documents')
        .select('*')
        .order('updated_at', { ascending: false })
        .limit(50);

      if (data && data.length > 0) {
        setArticles(data.map(mapDoc));
        setIsLive(true);
      }
    }
    load();
  }, []);

  const filtered = articles
    .filter((a) => !activeCategory || a.category === activeCategory)
    .filter((a) => !search || a.title.toLowerCase().includes(search.toLowerCase()) || a.excerpt?.toLowerCase().includes(search.toLowerCase()));

  const recentlySorted = [...articles].sort(
    (a, b) => new Date(b.updated).getTime() - new Date(a.updated).getTime()
  );

  return (
    <div className="flex flex-col gap-4">

      {/* Stats */}
      <Panel>
        <div className="flex flex-wrap items-center gap-0 divide-x divide-edge">
          <div className="flex flex-col pr-6">
            <span className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">Total Entries</span>
            <span className="font-lcars text-2xl font-bold leading-none text-science mt-0.5">
              {articles.length}
            </span>
          </div>
          <div className="flex flex-col px-6">
            <span className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">Categories</span>
            <span className="font-lcars text-2xl font-bold leading-none text-command mt-0.5">
              {new Set(articles.map((a) => a.category)).size}
            </span>
          </div>
          <div className="flex flex-col pl-6 flex-1">
            <span className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted mb-1">
              {isLive ? '● Live · Supabase' : '○ Mock data'}
            </span>
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search articles…"
              className="rounded-lcars border border-edge bg-space px-3 py-1.5 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-command focus:outline-none"
            />
          </div>
        </div>
      </Panel>

      <div className="grid gap-4 xl:grid-cols-[220px_1fr]">
        <div className="flex flex-col gap-4">
          <CategoryList
            articles={articles}
            activeCategory={activeCategory}
            onSelect={setCategory}
          />

          {/* Recent updates */}
          <Panel>
            <SectionHeader title="Recently Updated" />
            <ul className="flex flex-col gap-2">
              {recentlySorted.slice(0, 5).map((a) => {
                const dept = DEPARTMENTS[a.department] ?? DEPARTMENTS.command;
                return (
                  <li key={a.id} className="flex items-center gap-3 rounded-md border border-edge bg-panel-2/60 p-2">
                    <span className={`h-2 w-2 shrink-0 rounded-full ${dept.bg}`} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[11px] font-medium text-lcars-text">{a.title}</p>
                      <p className="text-[10px] text-lcars-muted">{a.owner}</p>
                    </div>
                    <span className="shrink-0 font-mono text-[10px] text-lcars-muted">{a.updated}</span>
                  </li>
                );
              })}
            </ul>
          </Panel>
        </div>

        {/* Article grid */}
        <Panel>
          <SectionHeader
            title={activeCategory ?? 'All Articles'}
            action={<StatusBadge label={`${filtered.length} entries`} tone="science" />}
          />
          {filtered.length === 0 ? (
            <p className="text-sm text-lcars-muted italic">No articles match.</p>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {filtered.map((a) => (
                <ArticleCard key={a.id} article={a} />
              ))}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
