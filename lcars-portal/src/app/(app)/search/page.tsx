'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { LCARSPanel } from '@/components/LCARSPanel';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { collectSourceOutcomes } from '@/lib/sourceResults';

// ── Types ─────────────────────────────────────────────────────────────────────

interface SearchResult {
  type: 'mission' | 'log' | 'capture' | 'event';
  id: string;
  title: string;
  detail?: string;
  timestamp?: string;
  href?: string;
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
    // MSN-0328 (WP-C): /captains-log is a today-only entry form with no
    // history view at all — routing a past-date search hit there landed
    // on a blank form. /timeline already renders past log entries
    // chronologically (fetchLogEntries) — the real existing destination.
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
    // MSN-0328 (WP-C): /captains-notebook reads intelligence_notes, never
    // captured_items — this search queries captured_items, so a hit here
    // never appeared on the page it linked to. The Capture Workbench Inbox is
    // the real captured_items consumer.
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
    // MSN-0328 (WP-C): no dedicated event-detail view exists anywhere in
    // this app (bare /missions showed the registry list, not the event).
    // /timeline already renders mission_execution_events chronologically
    // (fetchCommanderEvents) — the real existing destination.
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

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SearchPage() {
  const router = useRouter();
  const [query, setQuery]     = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [failedSources, setFailedSources] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
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
      setResults(items);
      setFailedSources(failed);
    } finally {
      setLoading(false);
    }
  }, []);

  function handleInput(val: string) {
    setQuery(val);
    if (timer) clearTimeout(timer);
    const t = setTimeout(() => runSearch(val), 300);
    setTimer(t);
  }

  // Group results by type
  const grouped = results.reduce<Record<string, SearchResult[]>>((acc, r) => {
    if (!acc[r.type]) acc[r.type] = [];
    acc[r.type].push(r);
    return acc;
  }, {});

  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel title="Universal Search" accent="science" eyebrow="MSN-3A-001">
        <div className="flex flex-col gap-4">

          {/* Search input */}
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-lcars-muted text-sm select-none">🔍</span>
            <input
              type="text"
              value={query}
              onChange={e => handleInput(e.target.value)}
              placeholder="Search missions, log entries, captures, events…"
              autoFocus
              className="w-full rounded-lcars border border-edge bg-space pl-9 pr-4 py-3 text-sm text-foreground placeholder:text-lcars-muted focus:border-science/60 focus:outline-none focus:ring-1 focus:ring-science/30"
            />
            {loading && (
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-lcars-muted animate-pulse">
                Searching…
              </span>
            )}
          </div>

          {/* Results */}
          {!searched && (
            <p className="text-sm text-lcars-muted">
              Type 2 or more characters to search across all operational domains.
            </p>
          )}

          {/* MSN-0351: honest, quiet note when one or more sources failed —
              a source outage no longer looks identical to "no matches". */}
          {searched && !loading && failedSources.length > 0 && (
            <p className="text-xs text-lcars-muted/80">
              Couldn&rsquo;t check: {failedSources.join(', ')}. Results may be incomplete.
            </p>
          )}

          {/* Only claim a genuine empty result when every source succeeded. */}
          {searched && !loading && results.length === 0 && failedSources.length === 0 && (
            <p className="text-sm text-lcars-muted">No results for <span className="text-foreground">&ldquo;{query}&rdquo;</span></p>
          )}

          {Object.entries(grouped).map(([type, items]) => (
            <div key={type} className="flex flex-col gap-1">
              <p className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted pb-1 border-b border-edge">
                {TYPE_LABEL[type] ?? type}
              </p>
              {items.map(r => (
                <button
                  key={r.id}
                  onClick={() => r.href && router.push(r.href)}
                  className="flex items-start gap-3 rounded-lcars px-3 py-2.5 text-left hover:bg-science/10 transition-colors w-full group"
                >
                  <span className="text-base shrink-0 mt-0.5">{TYPE_GLYPH[r.type] ?? '•'}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground group-hover:text-science-on truncate">{r.title}</p>
                    {r.detail && <p className="text-xs text-lcars-muted truncate mt-0.5">{r.detail}</p>}
                  </div>
                  <span className="text-[10px] text-lcars-muted shrink-0 mt-1">{relTs(r.timestamp)}</span>
                </button>
              ))}
            </div>
          ))}
        </div>
      </LCARSPanel>
    </div>
  );
}
