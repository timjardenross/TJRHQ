'use client';

import { useEffect, useState } from 'react';
import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import type { StatusTone } from '@/lib/types';

// ── Types ─────────────────────────────────────────────────────────────────────

interface CapturedItem {
  id: string;
  title: string | null;
  item_type: string | null;
  classification: string | null;
  importance: string | null;
  summary: string | null;
  processing_status: string | null;
  review_status: string | null;
  created_at: string;
}

interface Decision {
  id: string;
  mission_id: string | null;
  decision_type: string | null;
  outcome: string | null;
  timestamp: string | null;
}

interface CommanderEvent {
  id: string;
  source: string | null;
  event_type: string | null;
  message_text: string | null;
  status: string | null;
  created_at: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(ts: string | null | undefined): string {
  if (!ts) return '—';
  return new Date(ts).toLocaleString('en-AU', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false,
  });
}

function importanceTone(imp: string | null): StatusTone {
  switch (imp?.toLowerCase()) {
    case 'high':   return 'operations';
    case 'medium': return 'command';
    case 'low':    return 'neutral';
    default:       return 'neutral';
  }
}

function processingTone(status: string | null): StatusTone {
  switch (status) {
    case 'completed': return 'status';
    case 'pending':   return 'command';
    case 'failed':    return 'operations';
    default:          return 'neutral';
  }
}

// ── Captured Items ────────────────────────────────────────────────────────────

function CapturedItemsPanel({ items }: { items: CapturedItem[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (!items.length) {
    return <p className="text-xs text-lcars-muted italic">No captured items.</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      {items.map((item) => {
        const isOpen = expanded === item.id;
        return (
          <div key={item.id} className="rounded-lcars border border-edge bg-panel-2/60">
            <div className="flex flex-wrap items-start gap-3 p-3">
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-lcars-text leading-snug line-clamp-1">
                  {item.title ?? 'Untitled'}
                </p>
                <div className="flex flex-wrap gap-2 mt-1 text-[10px] text-lcars-muted">
                  {item.item_type && <span className="uppercase">{item.item_type.replace('_', ' ')}</span>}
                  <span>·</span>
                  <span>{fmt(item.created_at)}</span>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <StatusBadge
                  label={item.processing_status?.toUpperCase() ?? 'PENDING'}
                  tone={processingTone(item.processing_status)}
                />
                {item.importance && (
                  <StatusBadge
                    label={item.importance.toUpperCase()}
                    tone={importanceTone(item.importance)}
                  />
                )}
                {item.summary && (
                  <button
                    type="button"
                    onClick={() => setExpanded(isOpen ? null : item.id)}
                    className="rounded-md border border-edge px-2 py-1 text-[10px] uppercase tracking-[0.15em] text-lcars-muted hover:border-command hover:text-command-on transition-colors"
                  >
                    {isOpen ? 'Less' : 'More'}
                  </button>
                )}
              </div>
            </div>
            {isOpen && item.summary && (
              <div className="border-t border-edge px-3 pb-3 pt-2">
                <p className="text-xs leading-relaxed text-lcars-text/80">{item.summary}</p>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Decisions ─────────────────────────────────────────────────────────────────

function DecisionsPanel({ decisions }: { decisions: Decision[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (!decisions.length) return null;

  return (
    <LCARSPanel title="Recent Decisions" accent="operations" eyebrow={`${decisions.length} decision records`}>
      <div className="flex flex-col gap-2">
        {decisions.map((d) => {
          const isOpen = expanded === d.id;
          return (
            <div key={d.id} className="rounded-lcars border border-edge bg-panel-2/60">
              <div className="flex flex-wrap items-start gap-3 p-3">
                <div className="flex-1 min-w-0">
                  <p className="font-mono text-[10px] text-lcars-muted">{d.mission_id ?? '—'}</p>
                  <p className="text-xs text-lcars-text/80 mt-0.5 line-clamp-2">
                    {d.outcome ?? 'No outcome recorded.'}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {d.decision_type && (
                    <StatusBadge label={d.decision_type.toUpperCase()} tone="neutral" />
                  )}
                  {d.outcome && d.outcome.length > 80 && (
                    <button
                      type="button"
                      onClick={() => setExpanded(isOpen ? null : d.id)}
                      className="rounded-md border border-edge px-2 py-1 text-[10px] uppercase tracking-[0.15em] text-lcars-muted hover:border-operations hover:text-operations-on transition-colors"
                    >
                      {isOpen ? 'Less' : 'More'}
                    </button>
                  )}
                </div>
              </div>
              {isOpen && d.outcome && (
                <div className="border-t border-edge px-3 pb-3 pt-2">
                  <p className="text-xs leading-relaxed text-lcars-text/80">{d.outcome}</p>
                  <p className="text-[10px] text-lcars-muted mt-2">{fmt(d.timestamp)}</p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </LCARSPanel>
  );
}

// ── Friction Sources (D-055) ──────────────────────────────────────────────────

function FrictionPanel({ items, events }: { items: CapturedItem[]; events: CommanderEvent[] }) {
  // Identify friction signals: failed items, high-importance unreviewed, failed events
  const failedItems   = items.filter(i => i.processing_status === 'failed');
  const unreviewedHigh = items.filter(i => i.review_status === 'unreviewed' && i.importance === 'high');
  const failedEvents  = events.filter(e => e.status === 'failed' || e.status === 'error');
  const resolvedItems = items.filter(i => i.processing_status === 'completed' && i.review_status === 'reviewed');

  const frictionCount = failedItems.length + unreviewedHigh.length + failedEvents.length;

  return (
    <LCARSPanel
      title="Friction Sources"
      accent="operations"
      eyebrow="D-055 · Identify and remove recurring energy drains"
      actions={
        frictionCount > 0
          ? <StatusBadge label={`${frictionCount} signals`} tone="operations" />
          : <StatusBadge label="Clear" tone="status" />
      }
    >
      <p className="mb-4 text-xs text-lcars-muted leading-relaxed">
        Operations Officer mandate: identify and remove recurring sources of friction, inefficiency,
        and energy drain. Below are active signals requiring attention.
      </p>

      <div className="grid gap-3 sm:grid-cols-3 mb-4">
        <div className={`rounded-lcars border p-3 text-center ${failedItems.length > 0 ? 'border-operations/40 bg-operations/5' : 'border-edge bg-space/40'}`}>
          <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Failed processing</p>
          <p className={`font-lcars text-2xl font-bold mt-0.5 ${failedItems.length > 0 ? 'text-operations-on' : 'text-status-on'}`}>
            {failedItems.length}
          </p>
        </div>
        <div className={`rounded-lcars border p-3 text-center ${unreviewedHigh.length > 0 ? 'border-command/40 bg-command/5' : 'border-edge bg-space/40'}`}>
          <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Unreviewed (high)</p>
          <p className={`font-lcars text-2xl font-bold mt-0.5 ${unreviewedHigh.length > 0 ? 'text-command-on' : 'text-status-on'}`}>
            {unreviewedHigh.length}
          </p>
        </div>
        <div className="rounded-lcars border border-status/40 bg-status/5 p-3 text-center">
          <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Friction removed</p>
          <p className="font-lcars text-2xl font-bold text-status-on mt-0.5">{resolvedItems.length}</p>
        </div>
      </div>

      {failedItems.length > 0 && (
        <div className="mb-3">
          <p className="text-[10px] uppercase tracking-wider text-operations-on mb-1.5">Failed items — require attention</p>
          <div className="flex flex-col gap-1.5">
            {failedItems.slice(0, 3).map(item => (
              <div key={item.id} className="flex items-center gap-2 rounded-lcars border border-operations/30 bg-operations/5 px-3 py-2">
                <span className="text-operations-on text-xs shrink-0">▲</span>
                <span className="text-xs text-lcars-text/80 truncate">{item.title ?? 'Untitled'}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {frictionCount === 0 && (
        <p className="text-sm text-status-on">No active friction signals. Operations are flowing.</p>
      )}
    </LCARSPanel>
  );
}

// ── Commander Events ──────────────────────────────────────────────────────────

function EventsPanel({ events }: { events: CommanderEvent[] }) {
  if (!events.length) return null;

  return (
    <LCARSPanel title="Commander Events" accent="operations" eyebrow="Recent command stream">
      <div className="flex flex-col gap-2">
        {events.map((ev) => (
          <div key={ev.id} className="flex flex-wrap gap-3 rounded-lcars border border-edge bg-panel-2/60 px-3 py-2">
            <div className="flex-1 min-w-0">
              {ev.event_type && (
                <p className="text-[10px] uppercase tracking-wider text-lcars-muted mb-0.5">
                  {ev.event_type.replace(/_/g, ' ')}
                </p>
              )}
              <p className="text-xs text-lcars-text/80 leading-relaxed line-clamp-2">
                {ev.message_text ?? '—'}
              </p>
            </div>
            <div className="flex flex-col items-end gap-1 shrink-0 text-[10px] text-lcars-muted">
              {ev.source && <span>{ev.source}</span>}
              <span>{fmt(ev.created_at)}</span>
            </div>
          </div>
        ))}
      </div>
    </LCARSPanel>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function OperationsPage() {
  const [items,     setItems]     = useState<CapturedItem[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [events,    setEvents]    = useState<CommanderEvent[]>([]);
  const [isLive,    setIsLive]    = useState(false);
  const [loading,   setLoading]   = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const supabase = createSupabaseBrowserClient();
        const [itemRes, decRes, evRes] = await Promise.all([
          supabase
            .from('captured_items')
            .select('id, title, item_type, classification, importance, summary, processing_status, review_status, created_at')
            .order('created_at', { ascending: false })
            .limit(10),
          supabase
            .from('decisions')
            .select('id, mission_id, decision_type, outcome, timestamp')
            .order('timestamp', { ascending: false })
            .limit(10),
          supabase
            .from('commander_events')
            .select('id, source, event_type, message_text, status, created_at')
            .order('created_at', { ascending: false })
            .limit(8),
        ]);
        if (itemRes.data?.length) { setItems(itemRes.data as CapturedItem[]); setIsLive(true); }
        if (decRes.data?.length)  setDecisions(decRes.data as Decision[]);
        if (evRes.data?.length)   setEvents(evRes.data as CommanderEvent[]);
      } catch {
        // fall through
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const pendingItems = items.filter((i) => i.review_status === 'unreviewed');

  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel
        title="Operations"
        accent="operations"
        eyebrow="Captured Items · Decisions · Command Stream"
      >
        <p className="text-xs text-lcars-muted">
          Items captured from Slack, URLs, and other sources — plus the live decision log and recent command stream events.
        </p>
        <p className="mt-2 text-[10px] uppercase tracking-wider text-lcars-muted">
          {loading ? 'Loading…' : isLive ? '● Live · Supabase' : '○ No data'}
        </p>
      </LCARSPanel>

      <LCARSPanel
        title="Captured Items"
        accent="operations"
        eyebrow={loading ? 'Loading…' : `${items.length} items · ${pendingItems.length} unreviewed`}
      >
        <CapturedItemsPanel items={items} />
      </LCARSPanel>

      <FrictionPanel items={items} events={events} />

      <DecisionsPanel decisions={decisions} />

      <EventsPanel events={events} />
    </div>
  );
}
