'use client';

// Universal Search — Mission 7 relocation (2026-09-19). Previously lived at
// app/(app)/search/page.tsx, inside the legacy (app) route group (its own
// LCARSHeader/LCARSNav chrome, a different design system entirely) with
// zero live inbound links anywhere in the app — a real, maintained,
// working cross-domain search with no way to reach it. All fetch/search
// logic below is untouched, byte-for-byte the same queries as the old
// page; only the outer shell and visual tokens changed (WorkbenchShell +
// wb-* design tokens, matching every other live workbench, instead of
// LCARSPanel + the old lcars-* tokens). The old route now redirects here.
//
// Two of its 4 result types ("Captain's Log", "Events") link to /timeline
// — relocated in the same pass (app/timeline/page.tsx) for exactly that
// reason: shipping this alone would just move the Captain from one
// orphaned page to another for those two categories.

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Search as SearchIcon } from 'lucide-react';
import { WorkbenchShell } from '@/components/ui';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { collectSourceOutcomes } from '@/lib/sourceResults';
import { EvidenceMeta } from '@/components/EvidenceMeta';
import { deriveLifecycleState, LIFECYCLE_FILTERS, type LifecycleFilter } from '@/lib/lifecycleFilters';

// ── Types ─────────────────────────────────────────────────────────────────────

interface SearchResult {
  type: 'mission' | 'log' | 'capture' | 'event';
  id: string;
  title: string;
  detail?: string;
  timestamp?: string;
  href?: string;
  attentionState?: 'needs-action' | 'normal';
  importance?: 'important' | 'normal';
  lifecycleState?: LifecycleFilter;
}

// MSN-0351: each searcher reports whether its Supabase read succeeded so a
// failed source surfaces an honest "couldn't check" note rather than being
// silently indistinguishable from "no matches".
interface SearchOutcome {
  ok: boolean;
  results: SearchResult[];
}

// ── Supabase search functions ─────────────────────────────────────────────────

// 2026-08-22: raw `q` was interpolated straight into every .or() ilike
// filter below with no escaping — `,` is the Supabase .or() clause
// separator, so a comma typed into the search box silently mangled the
// filter (a real, reachable bug, not hypothetical — confirmed live).
// Same escaping api/knowledge-library/documents/route.ts already uses.
function escapeIlike(term: string): string {
  return term.replace(/[%_,]/g, (c) => `\\${c}`);
}

async function searchMissions(q: string): Promise<SearchOutcome> {
  const supabase = createSupabaseBrowserClient();
  const term = escapeIlike(q);
  const { data, error } = await supabase
    .from('missions')
    .select('mission_id, title, status, description, updated_at')
    .or(`title.ilike.%${term}%,mission_id.ilike.%${term}%,description.ilike.%${term}%`)
    .order('updated_at', { ascending: false })
    .limit(6);
  const results = (data ?? []).map(r => ({
    type:      'mission' as const,
    id:        r.mission_id,
    title:     r.title,
    detail:    r.status,
    timestamp: r.updated_at,
    href:      `/missions/${r.mission_id}`,
  }));
  return { ok: !error, results };
}

async function searchLog(q: string): Promise<SearchOutcome> {
  const supabase = createSupabaseBrowserClient();
  const term = escapeIlike(q);
  const { data, error } = await supabase
    .from('captains_log_entries')
    .select('log_date, tomorrows_priority, overall_note')
    .or(`tomorrows_priority.ilike.%${term}%,overall_note.ilike.%${term}%`)
    .order('log_date', { ascending: false })
    .limit(4);
  const results = (data ?? []).map(r => ({
    type:      'log' as const,
    id:        r.log_date,
    title:     `Captain's Log — ${r.log_date}`,
    detail:    (r.tomorrows_priority ?? r.overall_note ?? '').slice(0, 100),
    timestamp: r.log_date,
    // /timeline renders past log entries chronologically — the real
    // destination for a past-date hit (captains_log_entries itself has
    // had no new rows since 2026-06-28, so this source is rarely the one
    // that actually matches — kept for completeness/history search).
    href:      '/timeline',
  }));
  return { ok: !error, results };
}

async function searchCaptures(q: string): Promise<SearchOutcome> {
  const supabase = createSupabaseBrowserClient();
  const term = escapeIlike(q);
  const { data, error } = await supabase
    .from('captured_items')
    .select('id, title, raw_text, item_type, processing_status, captured_at')
    .or(`title.ilike.%${term}%,raw_text.ilike.%${term}%`)
    .order('captured_at', { ascending: false })
    .limit(4);
  const results = (data ?? []).map(r => ({
    type:      'capture' as const,
    id:        r.id,
    title:     r.title ?? r.raw_text?.slice(0, 80) ?? '(captured item)',
    detail:    `${r.item_type} · ${r.processing_status}`,
    timestamp: r.captured_at,
    href:      '/capture-workbench?domain=inbox',
  }));
  return { ok: !error, results };
}

async function searchEvents(q: string): Promise<SearchOutcome> {
  const supabase = createSupabaseBrowserClient();
  const term = escapeIlike(q);
  const { data, error } = await supabase
    .from('mission_execution_events')
    .select('id, status, mission_id, created_at')
    .or(`status.ilike.%${term}%,mission_id.ilike.%${term}%`)
    .order('created_at', { ascending: false })
    .limit(4);
  const results = (data ?? []).map(r => ({
    type:      'event' as const,
    id:        String(r.id),
    title:     `${r.mission_id ?? 'System'}: ${r.status}`,
    detail:    undefined,
    timestamp: r.created_at,
    // No dedicated event-detail view exists anywhere in the app —
    // /timeline renders mission_execution_events chronologically, the
    // real existing destination.
    href:      '/timeline',
  }));
  return { ok: !error, results };
}

// Pair each searcher with its display label so failures can be named.
const SEARCHERS: { source: string; run: (q: string) => Promise<SearchOutcome> }[] = [
  { source: 'Missions',      run: searchMissions },
  { source: "Captain's Log", run: searchLog },
  { source: 'Captures',      run: searchCaptures },
  { source: 'Events',        run: searchEvents },
];

// ── Result meta ───────────────────────────────────────────────────────────────

const TYPE_LABEL: Record<string, string> = {
  mission: 'Missions',
  log:     "Captain's Log",
  capture: 'Captures',
  event:   'Events',
};

const TYPE_GLYPH: Record<string, string> = {
  mission: '🚀',
  log:     '📓',
  capture: '📥',
  event:   '⚡',
};

function relTs(iso?: string) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  const diff = Date.now() - d.getTime();
  const days = Math.floor(diff / 86400000);
  if (days === 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 7)  return `${days}d ago`;
  return iso.slice(0, 10);
}

// Stream E (USS-TJR-MSN-0395): Phase 16 flagged Search/Timeline as untested
// for CONTINUITY. Verified this session -- `query` was plain useState, no
// URL/storage sync, so it vanished on navigate-away-and-back exactly like
// Knowledge Workbench's search box did (Stream B). Same fix, same reasoning
// (per-visit, not worth a URL param): sessionStorage with the repo's
// established try/catch guard.
const SS_QUERY = 'search-query';

function readSession(key: string): string | null {
  try { return sessionStorage.getItem(key); } catch { return null; }
}

function writeSession(key: string, value: string) {
  try { sessionStorage.setItem(key, value); } catch { /* ignore */ }
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SearchPage() {
  const router = useRouter();
  const [query, setQuery]     = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [failedSources, setFailedSources] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [attentionView, setAttentionView] = useState<'all' | 'needs-action' | 'important'>('all');
  const [lifecycleFilter, setLifecycleFilter] = useState<LifecycleFilter | null>(null);
  const [timer, setTimer]     = useState<ReturnType<typeof setTimeout> | null>(null);

  const runSearch = useCallback(async (q: string) => {
    if (q.trim().length < 2) { setResults([]); setSearched(false); setFailedSources([]); return; }
    setLoading(true);
    setSearched(true);
    try {
      // A rejected promise is a failed source, same as an ok:false Supabase
      // error — neither may silently disappear from the results.
      const outcomes = await Promise.all(
        SEARCHERS.map(s =>
          s.run(q)
            .then(r => ({ source: s.source, ok: r.ok, items: r.results }))
            .catch(() => ({ source: s.source, ok: false, items: [] as SearchResult[] })),
        ),
      );
      const { items, failed } = collectSourceOutcomes(outcomes);
      items.sort((a, b) => {
        if (!a.timestamp) return 1;
        if (!b.timestamp) return -1;
        return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
      });
      setResults(items.map((item) => {
        const status = (item.detail ?? '').split(' · ').at(-1)?.toLowerCase();
        return {
          ...item,
          attentionState: ['blocked', 'failed', 'error', 'pending', 'review', 'queued', 'needs_review'].includes(status ?? '') ? 'needs-action' : 'normal',
          lifecycleState: deriveLifecycleState({ status }) ?? undefined,
          importance: item.type === 'mission' || item.type === 'event' ? 'important' : 'normal',
        };
      }));
      setFailedSources(failed);
    } finally {
      setLoading(false);
    }
  }, []);

  function handleInput(val: string) {
    setQuery(val);
    writeSession(SS_QUERY, val);
    if (timer) clearTimeout(timer);
    const t = setTimeout(() => runSearch(val), 300);
    setTimer(t);
  }

  // Restored from sessionStorage on mount, not a useState lazy initializer --
  // that ran server-side too (no sessionStorage there), producing a
  // server/client hydration mismatch that silently lost the restored value.
  // Re-runs the same search the input would have triggered live.
  useEffect(() => {
    const saved = readSession(SS_QUERY);
    if (saved && saved.trim().length >= 2) { setQuery(saved); runSearch(saved); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Group results by type
  const grouped = results.reduce<Record<string, SearchResult[]>>((acc, r) => {
    if (!acc[r.type]) acc[r.type] = [];
    acc[r.type].push(r);
    return acc;
  }, {});
  // These views consume the result contract rather than scanning prose. Until
  // every upstream query supplies explicit fields, the adapters below assign
  // conservative defaults; unknown results never become falsely urgent.
  const isNeedsAction = (r: SearchResult) => r.attentionState === 'needs-action';
  const isImportant = (r: SearchResult) => r.importance === 'important';
  const filteredResults = attentionView === 'needs-action' ? results.filter(isNeedsAction) : attentionView === 'important' ? results.filter(isImportant) : results;
  const lifecycleResults = lifecycleFilter ? filteredResults.filter(r => r.lifecycleState === lifecycleFilter) : filteredResults;
  const filteredGrouped = lifecycleResults.reduce<Record<string, SearchResult[]>>((acc, r) => { (acc[r.type] ??= []).push(r); return acc; }, {});

  return (
    <WorkbenchShell
      title="Search"
      eyebrow="Cross-domain"
      tagline="USS TJR · Search · Missions, Captain's Log, Captures, Events"
      back={{ href: '/workbenches', label: 'Workbenches' }}
      mode="focus"
    >
      <div className="flex flex-col gap-4">
        <div className="relative">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-wb-ink2" aria-hidden />
          <input
            type="text"
            value={query}
            onChange={e => handleInput(e.target.value)}
            placeholder="Search missions, log entries, captures, events…"
            autoFocus
            aria-label="Search"
            className="w-full rounded-md border border-wb-line bg-wb-surface py-3 pl-9 pr-4 text-sm text-wb-ink placeholder:text-wb-ink2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
          />
          {loading && (
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-wb-ink2 animate-pulse">
              Searching…
            </span>
          )}
        </div>
        <div role="group" aria-label="Attention view" className="flex flex-wrap gap-2">
          {([['all', 'All'], ['needs-action', 'Needs action'], ['important', 'Important only']] as const).map(([value, label]) => (
            <button key={value} type="button" onClick={() => setAttentionView(value)} aria-pressed={attentionView === value} className={`rounded-md border px-3 py-1 text-[11px] font-bold uppercase tracking-wider focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep ${attentionView === value ? 'border-wb-sage-deep/60 bg-wb-sage-deep/10 text-wb-sage-deep' : 'border-wb-line text-wb-ink2 hover:text-wb-ink'}`}>{label}</button>
          ))}
          {LIFECYCLE_FILTERS.map(({ value, label }) => (
            <button key={value} type="button" onClick={() => setLifecycleFilter(lifecycleFilter === value ? null : value)} aria-pressed={lifecycleFilter === value} className={`rounded-md border px-3 py-1 text-[11px] font-bold uppercase tracking-wider focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep ${lifecycleFilter === value ? 'border-wb-sage-deep/60 bg-wb-sage-deep/10 text-wb-sage-deep' : 'border-wb-line text-wb-ink2 hover:text-wb-ink'}`}>{label}</button>
          ))}
          <span className="self-center text-[10px] text-wb-ink2">{lifecycleResults.length} shown</span>
        </div>

        {!searched && (
          <p className="text-sm text-wb-ink2">
            Type 2 or more characters to search across all operational domains.
          </p>
        )}

        {/* MSN-0351: honest, quiet note when one or more sources failed —
            a source outage no longer looks identical to "no matches". */}
        {searched && !loading && failedSources.length > 0 && (
          <p className="text-xs text-wb-ink2">
            Couldn&rsquo;t check: {failedSources.join(', ')}. Results may be incomplete.
          </p>
        )}

        {/* Only claim a genuine empty result when every source succeeded. */}
        {searched && !loading && results.length === 0 && failedSources.length === 0 && (
          <p className="text-sm text-wb-ink2">No results for <span className="text-wb-ink">&ldquo;{query}&rdquo;</span></p>
        )}

        {searched && !loading && lifecycleResults.length === 0 && results.length > 0 && (
          <p className="text-sm text-wb-ink2">No {lifecycleFilter ? LIFECYCLE_FILTERS.find(f => f.value === lifecycleFilter)?.label.toLowerCase() : attentionView === 'needs-action' ? 'needs-action' : 'important'} results in the current search.</p>
        )}
        {Object.entries(filteredGrouped).map(([type, items]) => (
          <div key={type} className="flex flex-col gap-1">
            <p className="border-b border-wb-line pb-1 text-[10px] uppercase tracking-[0.2em] text-wb-ink2">
              {TYPE_LABEL[type] ?? type}
            </p>
            {items.map(r => (
              <button
                key={r.id}
                type="button"
                onClick={() => r.href && router.push(r.href)}
                className="group flex w-full items-start gap-3 rounded-md px-3 py-2.5 text-left transition-colors hover:bg-wb-surface-raised focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
              >
                <span className="mt-0.5 shrink-0 text-base" aria-hidden>{TYPE_GLYPH[r.type] ?? '•'}</span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-wb-ink group-hover:text-wb-sage-deep">{r.title}</p>
                  {r.detail && <p className="mt-0.5 truncate text-xs text-wb-ink2">{r.detail}</p>}
                  <EvidenceMeta source={TYPE_LABEL[r.type] ?? r.type} observedAt={r.timestamp} />
                </div>
                <span className="mt-1 shrink-0 text-[10px] text-wb-ink2">{relTs(r.timestamp)}</span>
              </button>
            ))}
          </div>
        ))}
      </div>
    </WorkbenchShell>
  );
}
