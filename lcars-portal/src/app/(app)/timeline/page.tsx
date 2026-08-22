'use client';

import { useState, useEffect } from 'react';
import { LCARSPanel } from '@/components/LCARSPanel';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { collectSourceOutcomes } from '@/lib/sourceResults';
import type { DepartmentKey } from '@/lib/types';

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

const SOURCE_META: Record<EventSource, { label: string; glyph: string; dept: DepartmentKey }> = {
  missions: { label: 'Missions',  glyph: '🚀', dept: 'command'     },
  health:   { label: 'Health',    glyph: '🩺', dept: 'medical'     },
  log:      { label: 'Log',       glyph: '📓', dept: 'command'     },
  events:   { label: 'Events',    glyph: '⚡', dept: 'operations'  },
  captures: { label: 'Captures',  glyph: '📥', dept: 'engineering' },
};

const DOT_COLOUR: Record<EventSource, string> = {
  missions: 'bg-command',
  health:   'bg-medical',
  log:      'bg-command/60',
  events:   'bg-operations',
  captures: 'bg-engineering',
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

// ── Page ──────────────────────────────────────────────────────────────────────

export default function TimelinePage() {
  const [events, setEvents]     = useState<TimelineEvent[]>([]);
  const [failedSources, setFailedSources] = useState<EventSource[]>([]);
  const [loading, setLoading]   = useState(true);
  const [days, setDays]         = useState(14);
  const [filter, setFilter]     = useState<EventSource | ''>('');

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

  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel
        title="Unified Timeline"
        accent="science"
        eyebrow="MSN-3A-002"
        actions={
          <div className="flex gap-1">
            {DAY_OPTIONS.map(d => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`rounded px-2 py-1 text-[10px] font-bold uppercase tracking-wider transition-colors ${
                  days === d
                    ? 'bg-science text-white'
                    : 'text-lcars-muted hover:text-science-on'
                }`}
              >
                {d}d
              </button>
            ))}
          </div>
        }
      >
        {/* Source filters */}
        <div className="flex flex-wrap gap-2 mb-4">
          <button
            onClick={() => setFilter('')}
            className={`rounded-lcars border px-3 py-1 text-[11px] font-bold uppercase tracking-wider transition-colors ${
              filter === ''
                ? 'border-science/60 bg-science/10 text-science-on'
                : 'border-edge text-lcars-muted hover:text-science-on hover:border-science/40'
            }`}
          >
            All
          </button>
          {ALL_SOURCES.map(s => (
            <button
              key={s}
              onClick={() => setFilter(s === filter ? '' : s)}
              className={`rounded-lcars border px-3 py-1 text-[11px] font-bold uppercase tracking-wider transition-colors ${
                filter === s
                  ? 'border-science/60 bg-science/10 text-science-on'
                  : 'border-edge text-lcars-muted hover:text-science-on hover:border-science/40'
              }`}
            >
              {SOURCE_META[s].glyph} {SOURCE_META[s].label}
            </button>
          ))}
          <span className="ml-auto text-[10px] text-lcars-muted self-center">
            {visible.length} event{visible.length !== 1 ? 's' : ''}
          </span>
        </div>

        {/* MSN-0351: honest, quiet note when one or more sources failed to
            load — an outage no longer masquerades as "no events". */}
        {!loading && failedSources.length > 0 && (
          <p className="mb-3 text-xs text-lcars-muted/80">
            Couldn&rsquo;t check: {failedSources.map(s => SOURCE_META[s].label).join(', ')}. Results may be incomplete.
          </p>
        )}

        {/* Event list */}
        {loading ? (
          <p className="text-sm text-lcars-muted animate-pulse">Loading timeline…</p>
        ) : visible.length === 0 ? (
          // Only claim a genuine empty result when every source actually
          // succeeded; if some failed, the note above already explains it.
          failedSources.length > 0 ? null : (
            <p className="text-sm text-lcars-muted">No events in the last {days} days.</p>
          )
        ) : (
          <div className="flex flex-col">
            {visible.map((e, i) => (
              <div key={e.id} className="flex gap-3 group">
                {/* Timeline spine */}
                <div className="flex flex-col items-center shrink-0 w-4">
                  <span className={`mt-1.5 h-2 w-2 rounded-full shrink-0 ${DOT_COLOUR[e.source]}`} />
                  {i < visible.length - 1 && (
                    <span className="w-px flex-1 bg-edge mt-1" />
                  )}
                </div>
                {/* Content */}
                <div className="flex-1 min-w-0 pb-3">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm text-foreground leading-snug">{e.title}</p>
                    <span className="text-[10px] text-lcars-muted shrink-0 mt-0.5">{relTs(e.timestamp)}</span>
                  </div>
                  {e.detail && (
                    <p className="text-xs text-lcars-muted mt-0.5 truncate">{e.detail}</p>
                  )}
                  <span className="text-[9px] uppercase tracking-[0.15em] text-lcars-muted/60 mt-1 block">
                    {SOURCE_META[e.source]?.label ?? e.source}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </LCARSPanel>
    </div>
  );
}
