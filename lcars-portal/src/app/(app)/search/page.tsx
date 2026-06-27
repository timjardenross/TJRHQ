'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { LCARSPanel } from '@/components/LCARSPanel';
import { supabase } from '@/lib/supabase';

// ── Types ─────────────────────────────────────────────────────────────────────

interface SearchResult {
  type: 'mission' | 'log' | 'capture' | 'event';
  id: string;
  title: string;
  detail?: string;
  timestamp?: string;
  href?: string;
}

// ── Supabase search functions ─────────────────────────────────────────────────

async function searchMissions(q: string): Promise<SearchResult[]> {
  if (!supabase) return [];
  const { data } = await supabase
    .from('missions')
    .select('mission_id, title, status, domain, updated_at')
    .or(`title.ilike.%${q}%,mission_id.ilike.%${q}%,domain.ilike.%${q}%`)
    .order('updated_at', { ascending: false })
    .limit(6);
  return (data ?? []).map(r => ({
    type:      'mission' as const,
    id:        r.mission_id,
    title:     r.title,
    detail:    `${r.status} · ${r.domain ?? '—'}`,
    timestamp: r.updated_at,
    href:      '/missions',
  }));
}

async function searchLog(q: string): Promise<SearchResult[]> {
  if (!supabase) return [];
  const { data } = await supabase
    .from('captains_log_entries')
    .select('log_date, todays_intention, overall_note')
    .or(`todays_intention.ilike.%${q}%,overall_note.ilike.%${q}%`)
    .order('log_date', { ascending: false })
    .limit(4);
  return (data ?? []).map(r => ({
    type:      'log' as const,
    id:        r.log_date,
    title:     `Captain's Log — ${r.log_date}`,
    detail:    (r.todays_intention ?? r.overall_note ?? '').slice(0, 100),
    timestamp: r.log_date,
    href:      '/captains-log',
  }));
}

async function searchCaptures(q: string): Promise<SearchResult[]> {
  if (!supabase) return [];
  const { data } = await supabase
    .from('captured_items')
    .select('id, title, raw_text, item_type, processing_status, captured_at')
    .or(`title.ilike.%${q}%,raw_text.ilike.%${q}%`)
    .order('captured_at', { ascending: false })
    .limit(4);
  return (data ?? []).map(r => ({
    type:      'capture' as const,
    id:        r.id,
    title:     r.title ?? r.raw_text?.slice(0, 80) ?? '(captured item)',
    detail:    `${r.item_type} · ${r.processing_status}`,
    timestamp: r.captured_at,
    href:      '/captains-notebook',
  }));
}

async function searchEvents(q: string): Promise<SearchResult[]> {
  if (!supabase) return [];
  const { data } = await supabase
    .from('commander_events')
    .select('id, event_type, title, description, created_at')
    .or(`title.ilike.%${q}%,description.ilike.%${q}%`)
    .order('created_at', { ascending: false })
    .limit(4);
  return (data ?? []).map(r => ({
    type:      'event' as const,
    id:        String(r.id),
    title:     r.title ?? `Event: ${r.event_type}`,
    detail:    r.description?.slice(0, 100),
    timestamp: r.created_at,
    href:      '/missions',
  }));
}

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
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [timer, setTimer]     = useState<ReturnType<typeof setTimeout> | null>(null);

  const runSearch = useCallback(async (q: string) => {
    if (q.trim().length < 2) { setResults([]); setSearched(false); return; }
    setLoading(true);
    setSearched(true);
    try {
      const all = await Promise.allSettled([
        searchMissions(q),
        searchLog(q),
        searchCaptures(q),
        searchEvents(q),
      ]);
      const flat = all
        .filter((r): r is PromiseFulfilledResult<SearchResult[]> => r.status === 'fulfilled')
        .flatMap(r => r.value);
      flat.sort((a, b) => {
        if (!a.timestamp) return 1;
        if (!b.timestamp) return -1;
        return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
      });
      setResults(flat);
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

          {searched && !loading && results.length === 0 && (
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
                    <p className="text-sm font-medium text-foreground group-hover:text-science truncate">{r.title}</p>
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
