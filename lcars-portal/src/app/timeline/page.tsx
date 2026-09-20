'use client';

// Unified Timeline — Mission 7 relocation (2026-09-19), companion to
// app/search/page.tsx's relocation (see that file's header comment for
// why both moved together: 2 of Search's 4 result types link here). All
// fetch logic below is untouched, byte-for-byte the same queries as the
// old app/(app)/timeline/page.tsx; only the outer shell and visual tokens
// changed. The old route now redirects here.
//
// The 5-colour per-department dot system the old page used (bg-command/
// bg-medical/bg-operations/bg-engineering) has no equivalent in the wb-*
// design system and was simplified to one consistent dot colour — each
// row's glyph + label already identify its source; the colour coding was
// decorative on top of that, not the only way to tell sources apart.

import { useEffect, useState } from 'react';
import { WorkbenchShell } from '@/components/ui';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { collectSourceOutcomes } from '@/lib/sourceResults';

// ── Types ─────────────────────────────────────────────────────────────────────

type EventSource = 'missions' | 'health' | 'log' | 'events' | 'captures';

interface TimelineEvent {
  id: string;
  source: EventSource;
  title: string;
  detail?: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

// MSN-0351: each fetcher reports whether its Supabase read succeeded, so a
// failed source can surface an honest "couldn't check" note rather than
// silently vanishing into an empty timeline that looks like "no events".
interface SourceResult {
  ok: boolean;
  events: TimelineEvent[];
}

// ── Source fetchers (direct Supabase) ─────────────────────────────────────────

async function fetchMissionTransitions(days: number): Promise<SourceResult> {
  const supabase = createSupabaseBrowserClient();
  const since = new Date(Date.now() - days * 86400000).toISOString();
  const { data, error } = await supabase
    .from('mission_state_transitions')
    .select('id, mission_id, from_state, to_state, actor, created_at')
    .gte('created_at', since)
    .order('created_at', { ascending: false })
    .limit(30);
  const events = (data ?? []).map(r => ({
    id:        `mst-${r.id}`,
    source:    'missions' as const,
    title:     `${r.mission_id}: ${r.from_state ?? '?'} → ${r.to_state}`,
    detail:    r.actor ? `by ${r.actor}` : undefined,
    timestamp: r.created_at,
    metadata:  { from: r.from_state, to: r.to_state },
  }));
  return { ok: !error, events };
}

async function fetchCapacityCheckins(days: number): Promise<SourceResult> {
  const supabase = createSupabaseBrowserClient();
  const since = new Date(Date.now() - days * 86400000).toISOString();
  const { data, error } = await supabase
    .from('capacity_checkins')
    // Realigned 2026-08-22 (recovery_pulses -> capacity_checkins, MY
    // CAPACITY TODAY). No pulse_type slot exists in the new model — the
    // title reads by checkin_type + date instead of a morning/midday/
    // evening bucket.
    .select('id, log_date, checkin_type, pain_score, capacity_state, regulation_state, captured_at')
    .gte('captured_at', since)
    .order('captured_at', { ascending: false })
    .limit(30);
  const events = (data ?? []).map(r => {
    const parts: string[] = [];
    if (r.pain_score != null)    parts.push(`pain ${r.pain_score}`);
    if (r.capacity_state)        parts.push(`capacity ${r.capacity_state}`);
    if (r.regulation_state)      parts.push(`regulation ${r.regulation_state}`);
    return {
      id:        `cc-${r.id ?? r.log_date + r.checkin_type}`,
      source:    'health' as const,
      title:     r.checkin_type === 'evening' ? `Evening reflection (${r.log_date})` : `Capacity check-in (${r.log_date})`,
      detail:    parts.join(' · ') || undefined,
      timestamp: r.captured_at ?? `${r.log_date}T00:00:00Z`,
    };
  });
  return { ok: !error, events };
}

async function fetchLogEntries(days: number): Promise<SourceResult> {
  const supabase = createSupabaseBrowserClient();
  const since = new Date(Date.now() - days * 86400000).toISOString().slice(0, 10);
  const { data, error } = await supabase
    .from('captains_log_entries')
    .select('log_date, tomorrows_priority, captain_capacity_rating')
    .gte('log_date', since)
    .order('log_date', { ascending: false })
    .limit(14);
  const events = (data ?? []).map(r => ({
    id:        `log-${r.log_date}`,
    source:    'log' as const,
    title:     `Captain's Log filed — ${r.log_date}`,
    detail:    r.tomorrows_priority?.slice(0, 100),
    timestamp: `${r.log_date}T00:00:00Z`,
    metadata:  { capacity: r.captain_capacity_rating },
  }));
  return { ok: !error, events };
}

async function fetchCommanderEvents(days: number): Promise<SourceResult> {
  const supabase = createSupabaseBrowserClient();
  const since = new Date(Date.now() - days * 86400000).toISOString();
  const { data, error } = await supabase
    .from('mission_execution_events')
    .select('id, status, mission_id, created_at')
    .gte('created_at', since)
    .order('created_at', { ascending: false })
    .limit(20);
  const events = (data ?? []).map(r => ({
    id:        `ev-${r.id}`,
    source:    'events' as const,
    title:     `${r.mission_id ?? 'System'}: ${r.status}`,
    detail:    undefined,
    timestamp: r.created_at,
  }));
  return { ok: !error, events };
}

async function fetchCaptures(days: number): Promise<SourceResult> {
  const supabase = createSupabaseBrowserClient();
  const since = new Date(Date.now() - days * 86400000).toISOString();
  const { data, error } = await supabase
    .from('captured_items')
    .select('id, title, item_type, processing_status, captured_at')
    .gte('captured_at', since)
    .order('captured_at', { ascending: false })
    .limit(20);
  const events = (data ?? []).map(r => ({
    id:        `cap-${r.id}`,
    source:    'captures' as const,
    title:     r.title ?? '(captured item)',
    detail:    `${r.item_type} · ${r.processing_status}`,
    timestamp: r.captured_at,
  }));
  return { ok: !error, events };
}

// Pair each fetcher with its source key so failures can be labelled.
const TIMELINE_FETCHERS: { source: EventSource; run: (days: number) => Promise<SourceResult> }[] = [
  { source: 'missions', run: fetchMissionTransitions },
  { source: 'health',   run: fetchCapacityCheckins },
  { source: 'log',      run: fetchLogEntries },
  { source: 'events',   run: fetchCommanderEvents },
  { source: 'captures', run: fetchCaptures },
];

// ── Display helpers ───────────────────────────────────────────────────────────

const SOURCE_META: Record<EventSource, { label: string; glyph: string }> = {
  missions: { label: 'Missions',  glyph: '🚀' },
  health:   { label: 'Health',    glyph: '🩺' },
  log:      { label: 'Log',       glyph: '📓' },
  events:   { label: 'Events',    glyph: '⚡' },
  captures: { label: 'Captures',  glyph: '📥' },
};

function relTs(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60)   return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24)   return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 7)    return `${d}d ago`;
  return iso.slice(0, 10);
}

const DAY_OPTIONS = [7, 14, 30];
const ALL_SOURCES: EventSource[] = ['missions', 'health', 'log', 'events', 'captures'];

// Stream E (USS-TJR-MSN-0395): same CONTINUITY gap as Search (see that
// file's header comment) -- `days`/`filter` were plain useState, lost on
// navigate-away-and-back. Same sessionStorage fix.
const SS_DAYS = 'timeline-days';
const SS_FILTER = 'timeline-filter';

function readSession(key: string): string | null {
  try { return sessionStorage.getItem(key); } catch { return null; }
}

function writeSession(key: string, value: string) {
  try { sessionStorage.setItem(key, value); } catch { /* ignore */ }
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function TimelinePage() {
  const [events, setEvents]     = useState<TimelineEvent[]>([]);
  const [failedSources, setFailedSources] = useState<EventSource[]>([]);
  const [loading, setLoading]   = useState(true);
  const [days, setDaysState]    = useState(14);
  const [filter, setFilterState] = useState<EventSource | ''>('');
  const [attentionView, setAttentionView] = useState<'all' | 'needs-action' | 'important'>('all');

  const setDays = (d: number) => { setDaysState(d); writeSession(SS_DAYS, String(d)); };
  const setFilter = (f: EventSource | '') => { setFilterState(f); writeSession(SS_FILTER, f); };

  // Restored from sessionStorage on mount, not a useState lazy initializer --
  // that ran server-side too (no sessionStorage there), producing a
  // server/client hydration mismatch that silently lost the restored value
  // (see MemoryView.tsx / search/page.tsx for the same fix).
  useEffect(() => {
    const savedDays = Number(readSession(SS_DAYS));
    if (DAY_OPTIONS.includes(savedDays)) setDaysState(savedDays);
    const savedFilter = readSession(SS_FILTER);
    if (savedFilter && (ALL_SOURCES as string[]).includes(savedFilter)) setFilterState(savedFilter as EventSource);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    // A rejected promise (network/throw) is treated as a failed source, same
    // as an ok:false Supabase error — neither may silently disappear.
    Promise.all(
      TIMELINE_FETCHERS.map(f =>
        f.run(days)
          .then(r => ({ source: f.source, ok: r.ok, items: r.events }))
          .catch(() => ({ source: f.source, ok: false, items: [] as TimelineEvent[] })),
      ),
    ).then(outcomes => {
      if (cancelled) return;
      const { items, failed } = collectSourceOutcomes(outcomes);
      items.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
      setEvents(items);
      setFailedSources(failed as EventSource[]);
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, [days]);

  const visible = filter ? events.filter(e => e.source === filter) : events;
  const isNeedsAction = (e: TimelineEvent) => /blocked|failed|error|needs|review|pending|action/i.test(`${e.title} ${e.detail ?? ''}`);
  const isImportant = (e: TimelineEvent) => e.source === 'missions' || e.source === 'events' || /critical|urgent|important|red/i.test(`${e.title} ${e.detail ?? ''}`);
  const attentionVisible = attentionView === 'needs-action' ? visible.filter(isNeedsAction) : attentionView === 'important' ? visible.filter(isImportant) : visible;

  const daySelector = (
    <div role="group" aria-label="Date range" className="flex gap-1">
      {DAY_OPTIONS.map(d => (
        <button
          key={d}
          type="button"
          onClick={() => setDays(d)}
          aria-pressed={days === d}
          className={`rounded-md px-2 py-1 text-[10px] font-bold uppercase tracking-wider transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep ${
            days === d
              ? 'bg-wb-sage-deep text-white'
              : 'text-wb-ink2 hover:text-wb-ink'
          }`}
        >
          {d}d
        </button>
      ))}
    </div>
  );

  const sourceFilters = (
    <div role="group" aria-label="Filter by source" className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={() => setFilter('')}
        aria-pressed={filter === ''}
        className={`rounded-md border px-3 py-1 text-[11px] font-bold uppercase tracking-wider transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep ${
          filter === ''
            ? 'border-wb-sage-deep/60 bg-wb-sage-deep/10 text-wb-sage-deep'
            : 'border-wb-line text-wb-ink2 hover:border-wb-sage-deep/40 hover:text-wb-ink'
        }`}
      >
        All
      </button>
      {ALL_SOURCES.map(s => (
        <button
          key={s}
          type="button"
          onClick={() => setFilter(s === filter ? '' : s)}
          aria-pressed={filter === s}
          className={`rounded-md border px-3 py-1 text-[11px] font-bold uppercase tracking-wider transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep ${
            filter === s
              ? 'border-wb-sage-deep/60 bg-wb-sage-deep/10 text-wb-sage-deep'
              : 'border-wb-line text-wb-ink2 hover:border-wb-sage-deep/40 hover:text-wb-ink'
          }`}
        >
          {SOURCE_META[s].glyph} {SOURCE_META[s].label}
        </button>
      ))}
      <span className="ml-auto text-[10px] text-wb-ink2">
        {visible.length} event{visible.length !== 1 ? 's' : ''}
      </span>
    </div>
  );
  const attentionFilters = (
    <div role="group" aria-label="Attention view" className="flex flex-wrap items-center gap-2">
      {([['all', 'All'], ['needs-action', 'Needs action'], ['important', 'Important only']] as const).map(([value, label]) => (
        <button key={value} type="button" onClick={() => setAttentionView(value)} aria-pressed={attentionView === value} className={`rounded-md border px-3 py-1 text-[11px] font-bold uppercase tracking-wider focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep ${attentionView === value ? 'border-wb-sage-deep/60 bg-wb-sage-deep/10 text-wb-sage-deep' : 'border-wb-line text-wb-ink2 hover:text-wb-ink'}`}>{label}</button>
      ))}
      <span className="text-[10px] text-wb-ink2">{attentionVisible.length} shown</span>
    </div>
  );

  return (
    <WorkbenchShell
      title="Timeline"
      eyebrow="Cross-domain"
      tagline="USS TJR · Timeline · Missions, health, log, events, captures"
      back={{ href: '/workbenches', label: 'Workbenches' }}
      right={daySelector}
      tabs={<div className="flex flex-col gap-2">{attentionFilters}{sourceFilters}</div>}
      mode="focus"
    >
      {/* MSN-0351: honest, quiet note when one or more sources failed to
          load — an outage no longer masquerades as "no events". */}
      {!loading && failedSources.length > 0 && (
        <p className="mb-3 text-xs text-wb-ink2">
          Couldn&rsquo;t check: {failedSources.map(s => SOURCE_META[s].label).join(', ')}. Results may be incomplete.
        </p>
      )}

      {loading ? (
        <p className="text-sm text-wb-ink2 animate-pulse">Loading timeline…</p>
      ) : attentionVisible.length === 0 ? (
        // Only claim a genuine empty result when every source actually
        // succeeded; if some failed, the note above already explains it.
        failedSources.length > 0 ? null : (
          <p className="text-sm text-wb-ink2">{attentionView === 'all' ? `No events in the last ${days} days.` : `No ${attentionView === 'needs-action' ? 'needs-action' : 'important'} events in the current view.`}</p>
        )
      ) : (
        <div className="flex flex-col">
          {attentionVisible.map((e, i) => (
            <div key={e.id} className="group flex gap-3">
              <div className="flex w-4 shrink-0 flex-col items-center">
                <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-wb-sage-deep" aria-hidden />
                {i < visible.length - 1 && (
                  <span className="mt-1 w-px flex-1 bg-wb-line" />
                )}
              </div>
              <div className="min-w-0 flex-1 pb-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm leading-snug text-wb-ink">{e.title}</p>
                  <span className="mt-0.5 shrink-0 text-[10px] text-wb-ink2">{relTs(e.timestamp)}</span>
                </div>
                {e.detail && (
                  <p className="mt-0.5 truncate text-xs text-wb-ink2">{e.detail}</p>
                )}
                <span className="mt-1 block text-[9px] uppercase tracking-[0.15em] text-wb-ink2/70">
                  {SOURCE_META[e.source]?.label ?? e.source}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </WorkbenchShell>
  );
}
