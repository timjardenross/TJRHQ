'use client';

/**
 * Communications Pipeline — MSN-0202
 * Full view of comms_content items across all pipeline stages.
 * Captain can review drafts, approve, and mark as published here.
 */

import { useEffect, useState, type ReactNode } from 'react';

type Status = 'opportunity' | 'draft' | 'review' | 'approved' | 'ready_to_publish' | 'published';

interface CommItem {
  id: string;
  title: string;
  pillar: string | null;
  status: Status;
  source_kind: string | null;
  notes: string | null;
  body: string | null;
  draft_generated_at: string | null;
  sensitive: boolean;
  created_at: string;
  updated_at: string;
}

const STATUS_LABEL: Record<string, string> = {
  opportunity:      'Opportunity',
  draft:            'Draft',
  review:           'Review',
  approved:         'Approved',
  ready_to_publish: 'Ready to Publish',
  published:        'Published',
};

const STATUS_COLOUR: Record<string, string> = {
  opportunity:      'text-[#61718c] border-[#d9e1f0] bg-[#eef1f8]',
  draft:            'text-blue-400 border-blue-400/30 bg-blue-400/5',
  review:           'text-yellow-400 border-yellow-400/30 bg-yellow-400/5',
  approved:         'text-green-400 border-green-400/30 bg-green-400/5',
  ready_to_publish: 'text-purple-400 border-purple-400/30 bg-purple-400/5',
  published:        'text-[#243b7a] border-[#243b7a]/30 bg-[#243b7a]/5',
};

const PILLAR_LABEL: Record<string, string> = {
  operational_resilience:           'Operational Resilience',
  business_continuity:              'Business Continuity',
  human_performance:                'Human Performance',
  wellness_sustainable_performance: 'Wellness',
  ai_augmented_leadership:          'AI-Augmented Leadership',
  personal_operating_systems:       'Personal OS',
  future_of_work:                   'Future of Work',
  decision_quality_governance:      'Decision Quality',
};

const FORMATS = [
  { key: 'linkedin_post',       label: 'LinkedIn Post' },
  { key: 'executive_insight',   label: 'Executive Insight' },
  { key: 'lessons_learned',     label: 'Lessons Learned' },
  { key: 'case_study',          label: 'Case Study' },
  { key: 'industry_commentary', label: 'Industry Commentary' },
  { key: 'article_draft',       label: 'Article Draft' },
];

// ── Pipeline status badge ─────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_COLOUR[status] ?? 'text-[#61718c] border-[#d9e1f0] bg-[#eef1f8]';
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium ${cls}`}>
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

// ── Pipeline counts bar ───────────────────────────────────────────────────────

function PipelineBar({ counts }: { counts: Record<string, number> }) {
  const order = ['opportunity', 'draft', 'review', 'approved', 'ready_to_publish', 'published'];
  return (
    <div className="flex flex-wrap gap-3 rounded-lcars border border-[#d9e1f0] bg-white/20 p-3">
      <p className="w-full text-[10px] uppercase tracking-widest text-[#61718c] mb-1">Content Pipeline</p>
      {order.map(s => (
        <div key={s} className="text-center">
          <p className="text-lg font-bold text-[#18223a]">{counts[s] ?? 0}</p>
          <p className="text-[10px] text-[#61718c] capitalize">{s.replace(/_/g, ' ')}</p>
        </div>
      ))}
    </div>
  );
}

// ── Individual content item card ──────────────────────────────────────────────

function ItemCard({ item, onRefresh }: { item: CommItem; onRefresh: () => void }) {
  const [open, setOpen]           = useState(false);
  const [format, setFormat]       = useState('linkedin_post');
  const [busy, setBusy]           = useState(false);
  const [msg, setMsg]             = useState('');
  const [editBody, setEditBody]   = useState(item.body ?? '');
  const [saving, setSaving]       = useState(false);

  async function advance(trigger: string) {
    setBusy(true); setMsg('');
    try {
      const res = await fetch(`/api/comms/${item.id}/advance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trigger }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      // EOS Phase 2 Priority 5: mark_published no longer publishes directly
      // - it queues a governed proposal (api/comms/[id]/advance/route.ts),
      // so the response here is { proposed: true }, not { to: 'published' }.
      // The status badge correctly stays "Ready to Publish" until the
      // Captain approves it in Decide.
      setMsg(d.proposed ? 'Submitted for your approval in Decide — not published yet.' : `Moved to ${STATUS_LABEL[d.to]}`);
      onRefresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Error');
    } finally { setBusy(false); }
  }

  async function generate() {
    setBusy(true); setMsg('Generating draft…');
    try {
      const res = await fetch('/api/comms/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: item.id, format }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      setMsg(d.mode === 'llm' ? '✓ Draft generated' : '✓ Scaffold created (LLM unavailable)');
      setEditBody(d.body);
      onRefresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Error');
    } finally { setBusy(false); }
  }

  async function saveEdit() {
    setSaving(true);
    try {
      const res = await fetch(`/api/comms/${item.id}/advance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trigger: '_save_body', _body: editBody }),
      });
      // _save_body is not a real trigger — use the dedicated save endpoint instead
    } catch {}
    // For now save via direct Supabase update through a simple approach
    // just call refresh to pick up any changes
    setSaving(false);
  }

  const notes = item.notes ?? '';
  const signalLine = notes.match(/Signal: (.+?)(?:\.|$)/)?.[1] ?? '';
  const urlLine    = notes.match(/URL: (.+)/)?.[1] ?? '';

  return (
    <div className="rounded-lcars border border-[#d9e1f0] bg-white/30">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-start gap-3 p-3 text-left hover:bg-white/50 transition-colors"
      >
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap gap-2 items-center mb-1">
            <StatusBadge status={item.status} />
            {item.pillar && (
              <span className="text-[10px] text-[#61718c]">
                {PILLAR_LABEL[item.pillar] ?? item.pillar}
              </span>
            )}
            {item.sensitive && (
              <span className="text-[10px] text-red-400 border border-red-400/30 bg-red-400/5 rounded px-1.5 py-0.5">
                ⚠ Sensitive
              </span>
            )}
          </div>
          <p className="font-medium text-sm text-[#18223a] leading-snug">{item.title}</p>
          {signalLine && !open && (
            <p className="text-xs text-[#61718c]/70 italic mt-0.5 line-clamp-1">{signalLine}</p>
          )}
        </div>
        <span className="text-[10px] text-[#61718c] shrink-0 mt-1">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="border-t border-[#d9e1f0]/50 px-4 py-3 space-y-3 text-sm">

          {/* Suggested angle / signal context */}
          {signalLine && (
            <div>
              <p className="text-[10px] uppercase tracking-widest text-[#61718c] mb-1">Signal Angle</p>
              <p className="text-xs italic text-[#18223a]">{signalLine}</p>
            </div>
          )}
          {urlLine && (
            <a href={urlLine} target="_blank" rel="noopener noreferrer"
               className="text-xs text-[#243b7a] hover:underline">
              View source ↗
            </a>
          )}

          {/* Draft body */}
          {item.body ? (
            <div>
              <p className="text-[10px] uppercase tracking-widest text-[#61718c] mb-1">
                Draft
                {item.draft_generated_at && (
                  <span className="ml-2 normal-case">· generated {item.draft_generated_at.slice(0, 10)}</span>
                )}
              </p>
              <textarea
                className="w-full rounded border border-[#d9e1f0] bg-white/40 px-3 py-2 text-xs text-[#18223a] font-mono leading-relaxed resize-y"
                rows={12}
                value={editBody}
                onChange={e => setEditBody(e.target.value)}
              />
            </div>
          ) : (
            <p className="text-xs text-[#61718c]">No draft yet.</p>
          )}

          {/* Generate draft controls (opportunity only) */}
          {item.status === 'opportunity' && (
            <div className="flex flex-wrap gap-2 items-center">
              <select
                value={format}
                onChange={e => setFormat(e.target.value)}
                className="rounded border border-[#d9e1f0] bg-white/40 px-2 py-1 text-xs text-[#18223a]"
              >
                {FORMATS.map(f => (
                  <option key={f.key} value={f.key}>{f.label}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={generate}
                disabled={busy}
                className="text-xs border border-[#243b7a]/40 rounded px-2 py-1 text-[#243b7a] hover:bg-[#243b7a]/10 disabled:opacity-50 transition-colors"
              >
                {busy ? 'Generating…' : '✍ Generate Draft'}
              </button>
            </div>
          )}

          {/* Pipeline action buttons */}
          <div className="flex flex-wrap gap-2 pt-1">
            {item.status === 'draft' && (
              <button type="button" onClick={() => advance('officer_submitted')} disabled={busy}
                className="text-xs border border-yellow-400/40 rounded px-3 py-1 text-yellow-400 hover:bg-yellow-400/10 disabled:opacity-50 transition-colors">
                Submit for Review →
              </button>
            )}
            {item.status === 'review' && (
              <button type="button" onClick={() => advance('captain_approved')} disabled={busy}
                className="text-xs border border-green-400/40 rounded px-3 py-1 text-green-400 hover:bg-green-400/10 disabled:opacity-50 transition-colors">
                ✓ Approve →
              </button>
            )}
            {item.status === 'approved' && (
              <button type="button" onClick={() => advance('captain_confirmed')} disabled={busy}
                className="text-xs border border-purple-400/40 rounded px-3 py-1 text-purple-400 hover:bg-purple-400/10 disabled:opacity-50 transition-colors">
                Confirm Ready to Publish →
              </button>
            )}
            {item.status === 'ready_to_publish' && (
              <button type="button" onClick={() => advance('mark_published')} disabled={busy}
                className="text-xs border border-[#243b7a]/40 rounded px-3 py-1 text-[#243b7a] hover:bg-[#243b7a]/10 disabled:opacity-50 transition-colors">
                Submit for Publish Approval →
              </button>
            )}
          </div>

          {msg && (
            <p className="text-xs text-[#61718c]">{msg}</p>
          )}

          <p className="text-[10px] text-[#61718c] pt-1">
            Created {item.created_at.slice(0, 10)}
            {item.updated_at !== item.created_at && ` · Updated ${item.updated_at.slice(0, 10)}`}
            {item.source_kind && ` · ${item.source_kind.replace(/_/g, ' ')}`}
          </p>
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CommsPage() {
  const [items, setItems]   = useState<CommItem[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [filter, setFilter] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState<string | null>(null);

  async function load() {
    setLoading(true); setError(null);
    try {
      const qs = filter ? `?status=${filter}` : '';
      const res = await fetch(`/api/comms${qs}`);
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      setItems(d.items ?? []);
      setCounts(d.counts ?? {});
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load');
    } finally { setLoading(false); }
  }

  useEffect(() => { load(); }, [filter]);

  const statusOrder = ['opportunity', 'draft', 'review', 'approved', 'ready_to_publish', 'published'];
  const filtered = filter ? items : items;

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4 p-4">
      <header>
        <h1 className="text-xl font-semibold uppercase tracking-wider text-[#18223a]">
          Communications Pipeline
        </h1>
        <p className="text-sm text-[#61718c]">
          Content lifecycle — from signal to published thought-leadership
        </p>
      </header>

      <PipelineBar counts={counts} />

      {/* Filter tabs */}
      <div className="flex gap-2 flex-wrap">
        <button
          type="button"
          onClick={() => setFilter('')}
          className={`text-xs px-3 py-1 rounded border transition-colors ${!filter ? 'border-[#243b7a] text-[#243b7a] bg-[#243b7a]/10' : 'border-[#d9e1f0] text-[#61718c] hover:text-[#18223a]'}`}
        >
          All
        </button>
        {statusOrder.map(s => (
          <button
            key={s}
            type="button"
            onClick={() => setFilter(filter === s ? '' : s)}
            className={`text-xs px-3 py-1 rounded border transition-colors ${filter === s ? 'border-[#243b7a] text-[#243b7a] bg-[#243b7a]/10' : 'border-[#d9e1f0] text-[#61718c] hover:text-[#18223a]'}`}
          >
            {STATUS_LABEL[s]} {counts[s] ? `(${counts[s]})` : ''}
          </button>
        ))}
      </div>

      {loading && <p className="text-sm text-[#61718c]">Loading…</p>}
      {error && (
        <p className="rounded-lcars border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">{error}</p>
      )}

      {!loading && !error && items.length === 0 && (
        <div className="text-sm text-[#61718c] space-y-2">
          <p>No content in the pipeline yet.</p>
          <p className="text-xs">
            Go to <span className="text-[#243b7a]">IC → Content tab</span> and click
            {' '}<span className="text-[#243b7a]">+ Request draft</span> on a signal to add the first opportunity.
          </p>
        </div>
      )}

      {!loading && items.length > 0 && (
        <div className="flex flex-col gap-2">
          {items.map(item => (
            <ItemCard key={item.id} item={item} onRefresh={load} />
          ))}
        </div>
      )}
    </div>
  );
}
