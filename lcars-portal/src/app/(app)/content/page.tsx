'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';

// ── Types ─────────────────────────────────────────────────────────────────────

type ContentStatus =
  | 'opportunity'
  | 'draft'
  | 'review'
  | 'approved'
  | 'ready_to_publish'
  | 'published'
  | 'archived';

interface ContentItem {
  id: string;
  title: string;
  pillar: string | null;
  status: ContentStatus;
  format: string | null;
  source_kind: string | null;
  signal_source_id: string | null;
  notes: string | null;
  body: string | null;
  sensitive: boolean;
  created_at: string;
  updated_at: string;
}

// ── Status config ─────────────────────────────────────────────────────────────

const STATUS_ORDER: ContentStatus[] = [
  'opportunity', 'draft', 'review', 'approved', 'ready_to_publish', 'published',
];

const STATUS_META: Record<ContentStatus, { label: string; colour: string }> = {
  opportunity:      { label: 'Opportunity',      colour: 'text-lcars-muted border-edge' },
  draft:            { label: 'Draft',            colour: 'text-science-on border-science/40' },
  review:           { label: 'Review',           colour: 'text-operations-on border-operations/40' },
  approved:         { label: 'Approved',         colour: 'text-status-on border-status/40' },
  ready_to_publish: { label: 'Ready to publish', colour: 'text-engineering-on border-engineering/40' },
  published:        { label: 'Published',        colour: 'text-command-on border-command/40' },
  archived:         { label: 'Archived',         colour: 'text-lcars-muted border-edge' },
};

const NEXT_STATUS: Partial<Record<ContentStatus, ContentStatus>> = {
  opportunity:      'draft',
  draft:            'review',
  review:           'approved',
  approved:         'ready_to_publish',
  ready_to_publish: 'published',
};

const ADVANCE_LABEL: Partial<Record<ContentStatus, string>> = {
  opportunity:      'Start draft →',
  draft:            'Send to review →',
  review:           'Approve →',
  approved:         'Mark ready →',
  ready_to_publish: 'Mark published →',
};

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' });
}

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: ContentStatus }) {
  const { label, colour } = STATUS_META[status] ?? STATUS_META.opportunity;
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${colour}`}>
      {label}
    </span>
  );
}

// ── Item card ─────────────────────────────────────────────────────────────────

function ContentCard({ item, onUpdated }: { item: ContentItem; onUpdated: () => void }) {
  const [expanded, setExpanded]   = useState(false);
  const [busy, setBusy]           = useState(false);
  const [editBody, setEditBody]   = useState(false);
  const [bodyDraft, setBodyDraft] = useState(item.body ?? '');
  const [err, setErr]             = useState<string | null>(null);

  const patch = useCallback(async (update: Record<string, unknown>) => {
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch(`/api/content/pipeline?id=${item.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(update),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json?.error ?? 'Update failed');
      onUpdated();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed');
    } finally {
      setBusy(false);
    }
  }, [item.id, onUpdated]);

  const nextStatus = NEXT_STATUS[item.status];
  const advanceLabel = ADVANCE_LABEL[item.status];

  return (
    <li className="flex flex-col rounded-lcars border border-edge bg-panel/40">
      {/* Header */}
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-panel/60 transition-colors"
      >
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-lcars-text leading-snug truncate">
            {item.sensitive && <span className="mr-1 text-operations-on">⚑</span>}
            {item.title}
          </p>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <StatusBadge status={item.status} />
            {item.pillar && (
              <span className="text-[10px] text-lcars-muted capitalize">
                {item.pillar.replace(/_/g, ' ')}
              </span>
            )}
            {item.body && (
              <span className="text-[10px] text-science-on">✎ draft</span>
            )}
            <span className="ml-auto text-[10px] text-lcars-muted shrink-0">
              {fmtDate(item.created_at)}
            </span>
          </div>
        </div>
        <span className="shrink-0 text-xs text-lcars-muted">{expanded ? '▲' : '▼'}</span>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-edge px-4 pb-4 pt-3 space-y-3">

          {/* Notes / signal angle */}
          {item.notes && (
            <p className="text-xs text-lcars-muted/80 italic whitespace-pre-wrap">{item.notes}</p>
          )}

          {/* Body (draft text) */}
          {editBody ? (
            <div className="space-y-2">
              <textarea
                value={bodyDraft}
                onChange={e => setBodyDraft(e.target.value)}
                rows={8}
                className="w-full rounded border border-edge bg-space px-3 py-2 text-sm text-lcars-text resize-y"
                placeholder="Write your draft here…"
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => patch({ body: bodyDraft }).then(() => setEditBody(false))}
                  className="rounded border border-status/50 bg-status/10 px-3 py-1 text-xs text-status-on hover:bg-status/20 disabled:opacity-40"
                >
                  Save draft
                </button>
                <button
                  type="button"
                  onClick={() => { setBodyDraft(item.body ?? ''); setEditBody(false); }}
                  className="rounded border border-edge bg-edge/20 px-3 py-1 text-xs text-lcars-muted hover:bg-edge/40"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div>
              {item.body ? (
                <div className="rounded border border-edge/40 bg-panel/20 px-3 py-2 mb-2">
                  <p className="text-xs text-lcars-muted whitespace-pre-wrap">{item.body}</p>
                </div>
              ) : null}
              <button
                type="button"
                onClick={() => setEditBody(true)}
                className="text-[10px] uppercase tracking-wide text-science-on hover:text-science-on/70 transition-colors"
              >
                {item.body ? '✎ Edit draft' : '+ Add draft text'}
              </button>
            </div>
          )}

          {err && <p className="text-xs text-operations-on">{err}</p>}

          {/* Actions */}
          <div className="flex flex-wrap gap-2">
            {nextStatus && advanceLabel && (
              <button
                type="button"
                disabled={busy}
                onClick={() => patch({ status: nextStatus })}
                className="rounded border border-status/50 bg-status/10 px-3 py-1 text-xs text-status-on hover:bg-status/20 disabled:opacity-40"
              >
                {advanceLabel}
              </button>
            )}
            {item.status !== 'published' && (
              <button
                type="button"
                disabled={busy}
                onClick={() => patch({ status: 'archived' })}
                className="rounded border border-edge bg-edge/20 px-3 py-1 text-xs text-lcars-muted hover:bg-edge/40 disabled:opacity-40"
              >
                Archive
              </button>
            )}
          </div>
        </div>
      )}
    </li>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ContentPipelinePage() {
  const [items, setItems]       = useState<ContentItem[]>([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<ContentStatus | 'all'>('all');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/content/pipeline');
      const json = await res.json();
      if (!res.ok) throw new Error(json?.error ?? 'Failed to load');
      setItems(json.items ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const visible = statusFilter === 'all'
    ? items
    : items.filter(i => i.status === statusFilter);

  const countByStatus = STATUS_ORDER.reduce<Record<string, number>>((acc, s) => {
    acc[s] = items.filter(i => i.status === s).length;
    return acc;
  }, {});

  return (
    <div className="min-h-screen bg-space px-4 py-6 max-w-2xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-1">
          <Link
            href="/intelligence"
            className="text-[10px] uppercase tracking-wider text-lcars-muted hover:text-lcars-text transition-colors"
          >
            ← Intel
          </Link>
        </div>
        <h1 className="text-xl font-bold text-lcars-text uppercase tracking-wide">
          Content Pipeline
        </h1>
        <p className="text-xs text-lcars-muted mt-0.5">
          {items.length} item{items.length !== 1 ? 's' : ''} across all stages
        </p>
      </div>

      {/* Stage filter pills */}
      <div className="flex flex-wrap gap-1.5 mb-5">
        <button
          type="button"
          onClick={() => setStatusFilter('all')}
          className={`rounded border px-2.5 py-1 text-[10px] uppercase tracking-wide transition-colors ${
            statusFilter === 'all'
              ? 'border-lcars-text bg-lcars-text/10 text-lcars-text'
              : 'border-edge text-lcars-muted hover:border-lcars-muted'
          }`}
        >
          All ({items.length})
        </button>
        {STATUS_ORDER.map(s => countByStatus[s] > 0 ? (
          <button
            key={s}
            type="button"
            onClick={() => setStatusFilter(s)}
            className={`rounded border px-2.5 py-1 text-[10px] uppercase tracking-wide transition-colors ${
              statusFilter === s
                ? `${STATUS_META[s].colour} bg-panel/60`
                : 'border-edge text-lcars-muted hover:border-lcars-muted'
            }`}
          >
            {STATUS_META[s].label} ({countByStatus[s]})
          </button>
        ) : null)}
      </div>

      {/* Content */}
      {loading && (
        <p className="text-sm text-lcars-muted animate-pulse">Loading…</p>
      )}
      {error && (
        <p className="text-sm text-operations-on">{error}</p>
      )}
      {!loading && !error && visible.length === 0 && (
        <div className="rounded-lcars border border-edge bg-panel/20 px-4 py-6 text-center">
          <p className="text-sm text-lcars-muted">No items in this stage.</p>
          <p className="text-xs text-lcars-muted/60 mt-1">
            Add opportunities from{' '}
            <Link href="/intelligence" className="text-science-on hover:underline">
              Intel → Content
            </Link>
          </p>
        </div>
      )}
      {!loading && visible.length > 0 && (
        <ul className="flex flex-col gap-3">
          {visible.map(item => (
            <ContentCard key={item.id} item={item} onUpdated={load} />
          ))}
        </ul>
      )}
    </div>
  );
}
