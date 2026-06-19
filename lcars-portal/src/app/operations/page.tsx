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
                    className="rounded-md border border-edge px-2 py-1 text-[10px] uppercase tracking-[0.15em] text-lcars-muted hover:border-command hover:text-command transition-colors"
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
                      className="rounded-md border border-edge px-2 py-1 text-[10px] uppercase tracking-[0.15em] text-lcars-muted hover:border-operations hover:text-operations transition-colors"
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

      <DecisionsPanel decisions={decisions} />

      <EventsPanel events={events} />
    </div>
  );
}
