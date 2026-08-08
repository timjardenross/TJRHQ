'use client';

// The Content Workbench board (COMMS-002) — one card per comms_content
// opportunity, moving left to right through Capture -> Research ->
// Content Prep -> Proofing. Status transitions (draft->review, review->
// approved, approved->ready_to_publish, ready_to_publish->published) are
// all made through the single canonical POST /api/comms/[id]/advance —
// unchanged, unforked, same route comms-workbench's own Pipeline tab uses.
// This board never writes comms_content.status itself for anything except
// reading it back.
//
// Proofing now carries the flow through to publish submission: 'approved'
// and 'ready_to_publish' both render inside the Proofing column (see
// GET /api/content-workbench's stageOf()), each surfacing the next
// governed action. mark_published never flips status directly — it queues
// a publish_content proposal that only becomes real once the Captain
// approves it in Decide (see the advance route's own comment). This
// workbench now carries content all the way to "submitted for publish
// approval" without a detour through the Communications Workbench — the
// Captain still makes the final call, same as always. 'published' items
// still live in comms-workbench's Portfolio tab, not this active board.
//
// 2026-08 visual redesign (Content Workbench only, per user request — see
// STAGE_ACCENT in shared.ts): every function/handler below is unchanged
// from the pre-redesign version. This pass touches JSX structure and
// Tailwind classes on ItemCard/Column/the board wrapper, plus adds a
// pipeline-overview strip up top. Still constrained to WorkbenchShell's
// max-w-4xl (that's shared app chrome, not forked here).
//
// 2026-08 follow-up: the narrow 260px column was fine for scanning cards but
// unusable for actually writing/proofing in — a 9-row textarea at that width
// is a slot, not an editor. ItemCard now opens its stage body in the shared
// Modal primitive ('preview' variant, max-w-3xl) instead of expanding
// in-place; the collapsed card stays a compact preview in the column. Same
// stage-body components, same handlers, just rendered at a usable width.
// ProofingStageBody also gained an AI-assisted first pass over the QA
// checklist (POST .../ai-review) — advisory only, it pre-fills suggested
// checks/notes but never sets qa_status itself; the human still explicitly
// saves the checklist, same governance posture as the rest of this pipeline.

import { useEffect, useState } from 'react';
import { Badge, Button, Textarea, Select, Modal } from '@/components/ui';
import {
  STAGE_LABEL,
  STAGE_HINT,
  STAGE_ACCENT,
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
    <div className="space-y-3">
      <div>
        <p className="mb-1 text-[10px] uppercase tracking-wide text-wb-ink2">Framing angle</p>
        <input
          value={angle}
          onChange={(e) => setAngle(e.target.value)}
          placeholder="Suggested angle — confirm or rewrite"
          className="w-full rounded-md border border-wb-line bg-wb-surface px-3 py-2 text-[13.5px] text-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep"
        />
      </div>
      <div>
        <p className="mb-1 text-[10px] uppercase tracking-wide text-wb-ink2">Research notes</p>
        <Textarea rows={7} value={notes} onChange={(e) => setNotes(e.target.value)} className="text-[13.5px] leading-relaxed"
          aria-label={`Research notes for ${item.title}`} />
      </div>
      <div>
        <p className="mb-1 text-[10px] uppercase tracking-wide text-wb-ink2">Sources (one per line)</p>
        <Textarea rows={3} value={sourcesText} onChange={(e) => setSourcesText(e.target.value)} className="text-[13px] font-mono"
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
      {msg && <p className="text-[12px] text-wb-ink2" role="status" aria-live="polite">{msg}</p>}
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
    <div className="space-y-3 text-[13.5px]">
      {item.research_angle && (
        <div>
          <p className="mb-0.5 text-[10px] uppercase tracking-wide text-wb-ink2">Angle</p>
          <p className="italic leading-relaxed text-wb-ink">{item.research_angle}</p>
        </div>
      )}
      {item.research_notes && (
        <div>
          <p className="mb-0.5 text-[10px] uppercase tracking-wide text-wb-ink2">Research notes</p>
          <p className="whitespace-pre-wrap leading-relaxed text-wb-ink">{item.research_notes}</p>
        </div>
      )}
      {item.research_sources && item.research_sources.length > 0 && (
        <div>
          <p className="mb-0.5 text-[10px] uppercase tracking-wide text-wb-ink2">Sources</p>
          <ul className="list-inside list-disc leading-relaxed text-wb-ink">
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
      {msg && <p className="text-[12px] text-wb-ink2" role="status" aria-live="polite">{msg}</p>}
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
    <div className="space-y-3">
      <Textarea rows={16} value={body} onChange={(e) => setBody(e.target.value)} className="font-mono text-[13.5px] leading-relaxed"
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
        <div className="max-h-56 space-y-2 overflow-y-auto rounded-md border border-wb-line bg-wb-bg p-3">
          {revisions.length === 0 && <p className="text-[12px] text-wb-ink2">No revisions yet.</p>}
          {revisions.map((r) => (
            <div key={r.id} className="border-b border-wb-line/60 pb-2 text-[12px] last:border-0">
              <p className="text-wb-ink2">{new Date(r.created_at).toLocaleString('en-AU')} · {r.edited_by ?? '—'}</p>
              <p className="line-clamp-3 text-wb-ink">{r.body}</p>
            </div>
          ))}
        </div>
      )}
      {msg && <p className="text-[12px] text-wb-ink2" role="status" aria-live="polite">{msg}</p>}
    </div>
  );
}

// ── Proofing stage body: AI-assisted QA + approve + publish submission ───────

interface AiReview {
  accuracy: boolean | null; accuracy_note: string;
  brand_voice: boolean | null; brand_voice_note: string;
  compliance: boolean | null; compliance_note: string;
  links_checked: boolean | null; links_note: string;
  overall_notes: string;
}

const AI_NOTE_KEY: Record<string, keyof AiReview> = {
  accuracy: 'accuracy_note',
  brand_voice: 'brand_voice_note',
  compliance: 'compliance_note',
  links_checked: 'links_note',
};

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
  const [publishBusy, setPublishBusy] = useState(false);
  const [publishMsg, setPublishMsg] = useState('');
  const [aiReview, setAiReview] = useState<AiReview | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiMsg, setAiMsg] = useState('');

  async function runAiReview() {
    setAiBusy(true);
    setAiMsg('');
    try {
      const res = await fetch(`/api/content-workbench/${item.id}/ai-review`, { method: 'POST' });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      setAiReview(d.review);
      if (d.mode === 'llm') {
        setChecks((prev) => {
          const next = { ...prev };
          for (const c of QA_CHECKLIST_ITEMS) {
            const v = d.review[c.key];
            if (typeof v === 'boolean') next[c.key] = v;
          }
          return next;
        });
        setQaNotes((prev) => (prev ? prev : d.review.overall_notes ?? ''));
        setAiMsg('✓ AI review complete — checklist pre-filled, review before saving.');
      } else {
        setAiMsg(d.review.overall_notes || 'AI review unavailable — check manually.');
      }
    } catch (e) {
      setAiMsg(e instanceof Error ? e.message : 'AI review failed');
    } finally {
      setAiBusy(false);
    }
  }

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

  async function confirmReady() {
    setPublishBusy(true);
    setPublishMsg('');
    try {
      const res = await fetch(`/api/comms/${item.id}/advance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trigger: 'captain_confirmed' }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      onChanged();
    } catch (e) {
      setPublishMsg(e instanceof Error ? e.message : 'Error confirming');
    } finally {
      setPublishBusy(false);
    }
  }

  async function submitForPublish() {
    setPublishBusy(true);
    setPublishMsg('');
    try {
      const res = await fetch(`/api/comms/${item.id}/advance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trigger: 'mark_published' }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      setPublishMsg(d.proposed ? 'Submitted for your approval in Decide — not published yet.' : '✓ Published');
      onChanged();
    } catch (e) {
      setPublishMsg(e instanceof Error ? e.message : 'Error submitting');
    } finally {
      setPublishBusy(false);
    }
  }

  if (item.status === 'approved') {
    return (
      <div className="space-y-2 text-[13.5px]">
        <p className="flex flex-wrap items-center gap-1.5 text-wb-ok-on">
          <span className="rounded-full bg-wb-ok/15 px-2 py-0.5 font-semibold">✓ Approved</span>
          <span className="text-wb-ink2">
            {item.reviewed_by ? `by ${item.reviewed_by}` : ''}{item.reviewed_at ? ` · ${item.reviewed_at.slice(0, 10)}` : ''}
          </span>
        </p>
        <Button size="sm" onClick={confirmReady} disabled={publishBusy} className="w-full">
          {publishBusy ? 'Confirming…' : 'Confirm Ready to Publish →'}
        </Button>
        {publishMsg && <p className="text-[12px] text-wb-ink2" role="status" aria-live="polite">{publishMsg}</p>}
      </div>
    );
  }

  if (item.status === 'ready_to_publish') {
    return (
      <div className="space-y-2 text-[13.5px]">
        <p><span className="rounded-full bg-wb-ok/15 px-2 py-0.5 font-semibold text-wb-ok-on">✓ Ready to publish</span></p>
        <Button size="sm" onClick={submitForPublish} disabled={publishBusy} className="w-full">
          {publishBusy ? 'Submitting…' : 'Submit for Publish Approval →'}
        </Button>
        {publishMsg && <p className="text-[12px] text-wb-ink2" role="status" aria-live="polite">{publishMsg}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-3 text-[13.5px]">
      <div className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded-lg border border-wb-line bg-wb-bg p-3 leading-relaxed text-wb-ink">{item.body}</div>

      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed border-wb-sage/50 bg-wb-sage/5 p-2.5">
        <span aria-hidden className="text-[13px]">🤖</span>
        <p className="text-[12px] text-wb-ink2">AI can take a first pass at the checklist below — you review and confirm.</p>
        <Button size="sm" variant="secondary" onClick={runAiReview} disabled={aiBusy} className="ml-auto">
          {aiBusy ? 'Reviewing…' : 'Run AI Review →'}
        </Button>
      </div>
      {aiMsg && <p className="text-[12px] text-wb-ink2" role="status" aria-live="polite">{aiMsg}</p>}

      <div className="space-y-2 rounded-md border border-wb-line bg-wb-surface p-3">
        {QA_CHECKLIST_ITEMS.map((c) => {
          const note = aiReview?.[AI_NOTE_KEY[c.key]];
          return (
            <div key={c.key}>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={checks[c.key]} onChange={(e) => setChecks((prev) => ({ ...prev, [c.key]: e.target.checked }))}
                  className="h-4 w-4 rounded border-wb-line text-wb-sage-deep focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep" />
                {c.label}
              </label>
              {note && <p className="ml-6 mt-0.5 text-[11.5px] italic text-wb-ink2">🤖 {note}</p>}
            </div>
          );
        })}
        <input value={qaNotes} onChange={(e) => setQaNotes(e.target.value)} placeholder="QA notes (optional)"
          className="w-full rounded-md border border-wb-line bg-wb-bg px-3 py-2 text-[13px] text-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep" />
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
      {msg && <p className="text-[12px] text-wb-ink2" role="status" aria-live="polite">{msg}</p>}
    </div>
  );
}

// ── Card shell — collapsed preview + Modal detail view ───────────────────────

function ItemCard({ item, onChanged }: { item: ContentItem; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [confirmingDiscard, setConfirmingDiscard] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const accent = STAGE_ACCENT[item.stage];

  async function doDiscard() {
    setDiscarding(true);
    try {
      const res = await discard(item.id);
      if (res.ok) { setOpen(false); onChanged(); }
    } finally {
      setDiscarding(false);
    }
  }

  const chipRow = (
    <div className="flex flex-wrap items-center gap-1.5">
      <RankBadge score={item.rank_score} />
      {item.pillar && (
        <span className="rounded-full bg-wb-line px-2 py-0.5 text-[10.5px] font-medium text-wb-ink2">
          {PILLAR_LABEL[item.pillar] ?? item.pillar}
        </span>
      )}
      {item.captain_focus && <span className="rounded-full bg-wb-warn/15 px-2 py-0.5 text-[10.5px] font-semibold text-wb-warn-on">⭐ Priority</span>}
      {item.sensitive && <Badge status="error">⚠ Sensitive</Badge>}
    </div>
  );

  return (
    <>
      <div className="overflow-hidden rounded-xl border border-wb-line bg-wb-surface shadow-sm transition-all hover:shadow-md">
        <div className="flex">
          <span className={`w-[3px] shrink-0 ${accent.bar}`} aria-hidden />
          <button type="button" onClick={() => setOpen(true)}
            className="w-full space-y-1.5 p-3 text-left transition-colors hover:bg-wb-line/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
            <div className="flex flex-wrap items-center gap-1.5">
              {chipRow}
              <span aria-hidden className="ml-auto text-[13px] text-wb-ink2">⤢</span>
            </div>
            <p className="text-[13.5px] font-medium leading-snug text-wb-ink">{item.title}</p>
          </button>
        </div>
        <p className="border-t border-wb-line/70 px-3 py-1.5 text-[10px] text-wb-ink2">
          Created {item.created_at.slice(0, 10)}
          {item.source_kind && ` · ${item.source_kind.replace(/_/g, ' ')}`}
        </p>
      </div>

      <Modal open={open} onClose={() => { setOpen(false); setConfirmingDiscard(false); }} title={item.title} variant="preview">
        <div className="mb-4 space-y-2">
          {chipRow}
          <p className="text-[11px] uppercase tracking-wide text-wb-ink2">{STAGE_LABEL[item.stage]}</p>
        </div>

        {item.stage === 'capture' && <CaptureStageBody item={item} onChanged={onChanged} />}
        {item.stage === 'research' && <ResearchStageBody item={item} onChanged={onChanged} />}
        {item.stage === 'content_prep' && <ContentPrepStageBody item={item} onChanged={onChanged} />}
        {item.stage === 'proofing' && <ProofingStageBody item={item} onChanged={onChanged} />}

        <div className="mt-4 border-t border-wb-line pt-3">
          {!confirmingDiscard ? (
            <button type="button" onClick={() => setConfirmingDiscard(true)}
              className="text-[12px] text-wb-crit-on hover:underline" aria-label={`Discard "${item.title}"`}>
              Discard this item
            </button>
          ) : (
            <div className="flex items-center gap-2 rounded-md border border-wb-crit/40 bg-wb-crit/5 p-2">
              <p className="flex-1 text-[12px] text-wb-crit-on">Discard? It&rsquo;s removed from the board, not deleted.</p>
              <Button size="sm" variant="danger" onClick={doDiscard} disabled={discarding}>
                {discarding ? 'Discarding…' : 'Confirm'}
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setConfirmingDiscard(false)} disabled={discarding}>
                Cancel
              </Button>
            </div>
          )}
        </div>
      </Modal>
    </>
  );
}

// ── Column + board ─────────────────────────────────────────────────────────

function Column({ stage, items, onChanged }: { stage: Stage; items: ContentItem[]; onChanged: () => void }) {
  const accent = STAGE_ACCENT[stage];
  return (
    <div role="region" aria-label={`${STAGE_LABEL[stage]}, ${items.length} item${items.length === 1 ? '' : 's'}`}
      className={`flex min-w-[264px] flex-1 flex-col gap-2 rounded-xl ${accent.header} p-1.5`}>
      <div className="overflow-hidden rounded-lg border border-wb-line bg-wb-surface">
        <div className={`h-1 ${accent.bar}`} aria-hidden />
        <div className="flex items-center gap-1.5 px-2.5 py-1.5">
          <span aria-hidden className="text-[12px]">{accent.icon}</span>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-wb-ink">{STAGE_LABEL[stage]}</p>
          <span className={`ml-auto rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${accent.chip}`}>{items.length}</span>
        </div>
      </div>
      <p className="px-1 text-[9.5px] italic leading-tight text-wb-ink2/80">{STAGE_HINT[stage]}</p>
      <div className="flex flex-col gap-2" role="list" aria-label={`Items in ${STAGE_LABEL[stage]}`}>
        {items.map((item) => (<ItemCard key={item.id} item={item} onChanged={onChanged} />))}
        {items.length === 0 && <p className="py-4 text-center text-[10px] text-wb-ink2/60">Empty</p>}
      </div>
    </div>
  );
}

/** Compact funnel strip above the board — quick read of where volume sits. */
function PipelineOverview({ counts }: { counts: Record<Stage, number> }) {
  return (
    <div className="mb-3 flex items-center gap-1.5 overflow-x-auto rounded-lg border border-wb-line bg-wb-surface px-2.5 py-2">
      {STAGES.map((stage, i) => {
        const accent = STAGE_ACCENT[stage];
        return (
          <div key={stage} className="flex shrink-0 items-center gap-1.5">
            <div className="flex items-center gap-1.5 rounded-full py-1 pl-1 pr-2.5">
              <span className={`grid h-5 w-5 shrink-0 place-items-center rounded-full text-[10px] font-semibold text-white ${accent.bar}`} aria-hidden>
                {counts[stage]}
              </span>
              <span className="text-[11px] font-medium text-wb-ink2">{STAGE_LABEL[stage]}</span>
            </div>
            {i < STAGES.length - 1 && <span className="text-wb-ink2/40" aria-hidden>→</span>}
          </div>
        );
      })}
    </div>
  );
}

export function ContentBoard({ refreshSignal, onLoaded }: { refreshSignal: number; onLoaded?: (counts: Record<Stage, number>) => void }) {
  const [items, setItems] = useState<ContentItem[]>([]);
  const [counts, setCounts] = useState<Record<Stage, number> | null>(null);
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
      setCounts(data.counts ?? null);
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
        <>
          {counts && <PipelineOverview counts={counts} />}
          <div className="flex gap-3 overflow-x-auto pb-2">
            {STAGES.map((stage) => (
              <Column key={stage} stage={stage} items={items.filter((i) => i.stage === stage)} onChanged={load} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
