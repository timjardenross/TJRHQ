'use client';

// The Content Workbench board (COMMS-002) — one card per comms_content
// opportunity, moving left to right through Capture -> Research ->
// Content Prep -> Proofing. Status transitions (draft->review, review->
// approved) are made through the single canonical
// POST /api/comms/[id]/advance — unchanged, unforked, same route
// comms-workbench's own Pipeline tab uses. This board never writes
// comms_content.status itself for anything except reading it back.
//
// Deliberately stops at 'approved'. ready_to_publish/published/archived are
// excluded server-side (see GET /api/content-workbench) — publishing is the
// Communications Workbench Pipeline tab's job, not this one's.

import { useEffect, useState } from 'react';
import { Badge, Button, Textarea, Select } from '@/components/ui';
import {
  STAGE_LABEL,
  STAGE_HINT,
  PILLAR_LABEL,
  QA_CHECKLIST_ITEMS,
  rankBadgeStatus,
  type Stage,
  type ContentItem,
} from './shared';

const STAGES: Stage[] = ['capture', 'research', 'content_prep', 'proofing'];

const FORMATS = [
  { key: 'linkedin_post', label: 'LinkedIn Post' },
  { key: 'executive_insight', label: 'Executive Insight' },
  { key: 'lessons_learned', label: 'Lessons Learned' },
  { key: 'case_study', label: 'Case Study' },
  { key: 'industry_commentary', label: 'Industry Commentary' },
  { key: 'article_draft', label: 'Article Draft' },
];

function RankBadge({ score }: { score: number | null }) {
  if (score === null) return null;
  return <Badge status={rankBadgeStatus(score)}>{score.toFixed(1)}</Badge>;
}

async function discard(id: string, currentTrigger: 'discard' = 'discard') {
  return fetch(`/api/comms/${id}/advance`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ trigger: currentTrigger }),
  });
}

// ── Capture stage body: research brief form ──────────────────────────────────

function CaptureStageBody({ item, onChanged }: { item: ContentItem; onChanged: () => void }) {
  const [angle, setAngle] = useState(item.research_angle ?? '');
  const [notes, setNotes] = useState(item.research_notes ?? '');
  const [sourcesText, setSourcesText] = useState(
    (item.research_sources ?? []).map((s) => s.url ?? s.label ?? '').join('\n'),
  );
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');

  async function save(complete: boolean) {
    setSaving(true);
    setMsg('');
    try {
      const sources = sourcesText.split('\n').map((l) => l.trim()).filter(Boolean).map((url) => ({ url }));
      const res = await fetch(`/api/content-workbench/${item.id}/research`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ research_notes: notes, research_angle: angle, research_sources: sources, complete }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      setMsg(complete ? '✓ Research complete — ready to draft' : '✓ Notes saved');
      if (complete) onChanged();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Error saving');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-2">
      <div>
        <p className="mb-1 text-[10px] uppercase tracking-wide text-wb-ink2">Framing angle</p>
        <input
          value={angle}
          onChange={(e) => setAngle(e.target.value)}
          placeholder="Suggested angle — confirm or rewrite"
          className="w-full rounded-md border border-wb-line bg-wb-surface px-2 py-1.5 text-[12px] text-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep"
        />
      </div>
      <div>
        <p className="mb-1 text-[10px] uppercase tracking-wide text-wb-ink2">Research notes</p>
        <Textarea rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} className="text-[12px]"
          aria-label={`Research notes for ${item.title}`} />
      </div>
      <div>
        <p className="mb-1 text-[10px] uppercase tracking-wide text-wb-ink2">Sources (one per line)</p>
        <Textarea rows={2} value={sourcesText} onChange={(e) => setSourcesText(e.target.value)} className="text-[12px] font-mono"
          aria-label={`Sources for ${item.title}`} />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" onClick={() => save(false)} disabled={saving}>
          {saving ? 'Saving…' : 'Save Notes'}
        </Button>
        <Button size="sm" onClick={() => save(true)} disabled={saving || !notes.trim()}>
          Mark Research Complete →
        </Button>
      </div>
      {msg && <p className="text-[11px] text-wb-ink2" role="status" aria-live="polite">{msg}</p>}
    </div>
  );
}

// ── Research stage body: confirmed brief + generate draft ────────────────────

function ResearchStageBody({ item, onChanged }: { item: ContentItem; onChanged: () => void }) {
  const [format, setFormat] = useState('linkedin_post');
  const [generating, setGenerating] = useState(false);
  const [msg, setMsg] = useState('');

  async function generate() {
    setGenerating(true);
    setMsg('Generating draft…');
    try {
      const res = await fetch(`/api/content-workbench/${item.id}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      setMsg(d.mode === 'llm' ? '✓ Draft generated' : '✓ Scaffold created (LLM unavailable)');
      onChanged();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Error generating draft');
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="space-y-2 text-[12px]">
      {item.research_angle && (
        <div>
          <p className="mb-0.5 text-[10px] uppercase tracking-wide text-wb-ink2">Angle</p>
          <p className="italic text-wb-ink">{item.research_angle}</p>
        </div>
      )}
      {item.research_notes && (
        <div>
          <p className="mb-0.5 text-[10px] uppercase tracking-wide text-wb-ink2">Research notes</p>
          <p className="whitespace-pre-wrap text-wb-ink">{item.research_notes}</p>
        </div>
      )}
      {item.research_sources && item.research_sources.length > 0 && (
        <div>
          <p className="mb-0.5 text-[10px] uppercase tracking-wide text-wb-ink2">Sources</p>
          <ul className="list-inside list-disc text-wb-ink">
            {item.research_sources.map((s, i) => (
              <li key={i}>{s.url ?? s.label}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="flex flex-wrap items-end gap-2 pt-1">
        <Select label="Format" value={format} onChange={(e) => setFormat(e.target.value)} className="w-auto">
          {FORMATS.map((f) => (<option key={f.key} value={f.key}>{f.label}</option>))}
        </Select>
        <Button size="sm" onClick={generate} disabled={generating}>
          {generating ? 'Generating…' : '✍ Generate Draft →'}
        </Button>
      </div>
      {msg && <p className="text-[11px] text-wb-ink2" role="status" aria-live="polite">{msg}</p>}
    </div>
  );
}

// ── Content Prep stage body: draft editor + revision history + submit ────────

function ContentPrepStageBody({ item, onChanged }: { item: ContentItem; onChanged: () => void }) {
  const [body, setBody] = useState(item.body ?? '');
  const [saving, setSaving] = useState(false);
  const [advancing, setAdvancing] = useState(false);
  const [msg, setMsg] = useState('');
  const [showHistory, setShowHistory] = useState(false);
  const [revisions, setRevisions] = useState<Array<{ id: string; body: string; edited_by: string | null; created_at: string }>>([]);

  async function saveEdit() {
    setSaving(true);
    setMsg('');
    try {
      const res = await fetch(`/api/content-workbench/${item.id}/draft`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ body }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      setMsg('✓ Saved (revision recorded)');
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Error saving');
    } finally {
      setSaving(false);
    }
  }

  async function loadHistory() {
    setShowHistory((v) => !v);
    if (!showHistory) {
      const res = await fetch(`/api/content-workbench/${item.id}/revisions`);
      const d = await res.json();
      setRevisions(d.revisions ?? []);
    }
  }

  async function submitForReview() {
    setAdvancing(true);
    setMsg('');
    try {
      const res = await fetch(`/api/comms/${item.id}/advance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trigger: 'officer_submitted' }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      setMsg('✓ Submitted for review');
      onChanged();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Error submitting');
    } finally {
      setAdvancing(false);
    }
  }

  return (
    <div className="space-y-2">
      <Textarea rows={9} value={body} onChange={(e) => setBody(e.target.value)} className="font-mono text-[12px]"
        aria-label={`Draft body for ${item.title}`} />
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" onClick={saveEdit} disabled={saving}>
          {saving ? 'Saving…' : 'Save Edit'}
        </Button>
        <Button size="sm" variant="secondary" onClick={loadHistory}>
          {showHistory ? 'Hide' : 'Show'} Revision History
        </Button>
        <Button size="sm" onClick={submitForReview} disabled={advancing} className="ml-auto">
          {advancing ? 'Submitting…' : 'Submit for Review →'}
        </Button>
      </div>
      {showHistory && (
        <div className="max-h-40 space-y-1.5 overflow-y-auto rounded-md border border-wb-line bg-wb-bg p-2">
          {revisions.length === 0 && <p className="text-[11px] text-wb-ink2">No revisions yet.</p>}
          {revisions.map((r) => (
            <div key={r.id} className="border-b border-wb-line/60 pb-1 text-[11px] last:border-0">
              <p className="text-wb-ink2">{new Date(r.created_at).toLocaleString('en-AU')} · {r.edited_by ?? '—'}</p>
              <p className="line-clamp-2 text-wb-ink">{r.body}</p>
            </div>
          ))}
        </div>
      )}
      {msg && <p className="text-[11px] text-wb-ink2" role="status" aria-live="polite">{msg}</p>}
    </div>
  );
}

// ── Proofing stage body: QA checklist + approve ───────────────────────────────

function ProofingStageBody({ item, onChanged }: { item: ContentItem; onChanged: () => void }) {
  const existing = (item.qa_checklist ?? {}) as Record<string, unknown>;
  const [checks, setChecks] = useState<Record<string, boolean>>(
    Object.fromEntries(QA_CHECKLIST_ITEMS.map((c) => [c.key, existing[c.key] === true])),
  );
  const [qaNotes, setQaNotes] = useState(typeof existing.notes === 'string' ? existing.notes : '');
  const [saving, setSaving] = useState(false);
  const [approving, setApproving] = useState(false);
  const [msg, setMsg] = useState('');
  const [qaStatus, setQaStatus] = useState(item.qa_status);

  async function saveQa() {
    setSaving(true);
    setMsg('');
    try {
      const res = await fetch(`/api/content-workbench/${item.id}/qa`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ qa_checklist: { ...checks, notes: qaNotes } }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      setQaStatus(d.qa_status);
      setMsg(d.qa_status === 'qa_passed' ? '✓ QA passed — ready to approve' : d.qa_status === 'qa_failed' ? 'QA incomplete — check remaining items' : '✓ Saved');
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Error saving QA');
    } finally {
      setSaving(false);
    }
  }

  async function approve() {
    setApproving(true);
    setMsg('');
    try {
      const res = await fetch(`/api/comms/${item.id}/advance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trigger: 'captain_approved' }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      setMsg('✓ Approved');
      onChanged();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Error approving');
    } finally {
      setApproving(false);
    }
  }

  if (item.status === 'approved') {
    return (
      <div className="space-y-1.5 text-[12px]">
        <p className="text-wb-ok-on">✓ Approved{item.reviewed_by ? ` by ${item.reviewed_by}` : ''}{item.reviewed_at ? ` · ${item.reviewed_at.slice(0, 10)}` : ''}.</p>
        <p className="text-wb-ink2">Ready to publish — advance it from the Communications Workbench Pipeline tab. Publishing stays out of this workbench.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2 text-[12px]">
      <div className="whitespace-pre-wrap rounded-md border border-wb-line bg-wb-bg p-2 text-[12px] text-wb-ink">{item.body}</div>
      <div className="space-y-1.5">
        {QA_CHECKLIST_ITEMS.map((c) => (
          <label key={c.key} className="flex items-center gap-2">
            <input type="checkbox" checked={checks[c.key]} onChange={(e) => setChecks((prev) => ({ ...prev, [c.key]: e.target.checked }))}
              className="h-4 w-4 rounded border-wb-line text-wb-sage-deep focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep" />
            {c.label}
          </label>
        ))}
        <input value={qaNotes} onChange={(e) => setQaNotes(e.target.value)} placeholder="QA notes (optional)"
          className="w-full rounded-md border border-wb-line bg-wb-surface px-2 py-1.5 text-[12px] text-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep" />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="secondary" onClick={saveQa} disabled={saving}>
          {saving ? 'Saving…' : 'Save QA Checklist'}
        </Button>
        {qaStatus === 'qa_passed' && (
          <Button size="sm" onClick={approve} disabled={approving}>
            {approving ? 'Approving…' : 'Approve →'}
          </Button>
        )}
        {qaStatus === 'qa_failed' && <Badge status="warning">QA incomplete</Badge>}
      </div>
      {msg && <p className="text-[11px] text-wb-ink2" role="status" aria-live="polite">{msg}</p>}
    </div>
  );
}

// ── Card shell ─────────────────────────────────────────────────────────────

function ItemCard({ item, onChanged }: { item: ContentItem; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [confirmingDiscard, setConfirmingDiscard] = useState(false);
  const [discarding, setDiscarding] = useState(false);

  async function doDiscard() {
    setDiscarding(true);
    try {
      const res = await discard(item.id);
      if (res.ok) onChanged();
    } finally {
      setDiscarding(false);
    }
  }

  return (
    <div className="rounded-lg border border-wb-line bg-wb-surface">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
        className="w-full space-y-1.5 rounded-lg p-3 text-left transition-colors hover:bg-wb-line/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
        <div className="flex flex-wrap items-center gap-1.5">
          <RankBadge score={item.rank_score} />
          {item.pillar && <span className="text-[11px] text-wb-ink2">{PILLAR_LABEL[item.pillar] ?? item.pillar}</span>}
          {item.captain_focus && <span className="text-[11px] text-wb-warn-on">⭐ Captain Priority</span>}
          {item.sensitive && <Badge status="error">⚠ Sensitive</Badge>}
          <span className="ml-auto text-[10px] text-wb-ink2">{open ? '▲' : '▼'}</span>
        </div>
        <p className="text-[13px] font-medium leading-snug text-wb-ink">{item.title}</p>
      </button>

      {open && (
        <div className="space-y-3 border-t border-wb-line px-3 py-3">
          {item.stage === 'capture' && <CaptureStageBody item={item} onChanged={onChanged} />}
          {item.stage === 'research' && <ResearchStageBody item={item} onChanged={onChanged} />}
          {item.stage === 'content_prep' && <ContentPrepStageBody item={item} onChanged={onChanged} />}
          {item.stage === 'proofing' && <ProofingStageBody item={item} onChanged={onChanged} />}

          {!confirmingDiscard ? (
            <button type="button" onClick={() => setConfirmingDiscard(true)}
              className="text-[11px] text-wb-crit-on hover:underline" aria-label={`Discard "${item.title}"`}>
              Discard this item
            </button>
          ) : (
            <div className="flex items-center gap-2 rounded-md border border-wb-crit/40 bg-wb-crit/5 p-2">
              <p className="flex-1 text-[11px] text-wb-crit-on">Discard? It&rsquo;s removed from the board, not deleted.</p>
              <Button size="sm" variant="danger" onClick={doDiscard} disabled={discarding}>
                {discarding ? 'Discarding…' : 'Confirm'}
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setConfirmingDiscard(false)} disabled={discarding}>
                Cancel
              </Button>
            </div>
          )}

          <p className="text-[10px] text-wb-ink2">
            Created {item.created_at.slice(0, 10)}
            {item.source_kind && ` · ${item.source_kind.replace(/_/g, ' ')}`}
          </p>
        </div>
      )}
    </div>
  );
}

// ── Column + board ─────────────────────────────────────────────────────────

function Column({ stage, items, onChanged }: { stage: Stage; items: ContentItem[]; onChanged: () => void }) {
  return (
    <div role="region" aria-label={`${STAGE_LABEL[stage]}, ${items.length} item${items.length === 1 ? '' : 's'}`}
      className="flex min-w-[260px] flex-1 flex-col gap-2">
      <div className="rounded-md border border-wb-line bg-wb-surface px-2 py-1.5 text-center">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-wb-ink">{STAGE_LABEL[stage]}</p>
        <p className="text-[10px] text-wb-ink2">{items.length} item{items.length === 1 ? '' : 's'}</p>
        <p className="mt-0.5 text-[9px] italic text-wb-ink2/80">{STAGE_HINT[stage]}</p>
      </div>
      <div className="flex flex-col gap-2" role="list" aria-label={`Items in ${STAGE_LABEL[stage]}`}>
        {items.map((item) => (<ItemCard key={item.id} item={item} onChanged={onChanged} />))}
        {items.length === 0 && <p className="py-4 text-center text-[10px] text-wb-ink2/60">Empty</p>}
      </div>
    </div>
  );
}

export function ContentBoard({ refreshSignal, onLoaded }: { refreshSignal: number; onLoaded?: (counts: Record<Stage, number>) => void }) {
  const [items, setItems] = useState<ContentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/content-workbench');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'Failed to load board');
      setItems(data.items ?? []);
      if (onLoaded) onLoaded(data.counts);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load board');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshSignal]);

  return (
    <div className="flex flex-col gap-3">
      {loading && <p className="text-sm text-wb-ink2">Loading board…</p>}
      {error && <p className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">{error}</p>}
      {!loading && !error && (
        <div className="flex gap-3 overflow-x-auto pb-2">
          {STAGES.map((stage) => (
            <Column key={stage} stage={stage} items={items.filter((i) => i.stage === stage)} onChanged={load} />
          ))}
        </div>
      )}
    </div>
  );
}
