'use client';

// Stage-body logic for the Content Workbench (COMMS-002) — extracted from
// ContentBoard.tsx (MSN-0363, Content Studio uplift) so the existing Board
// and the new Content Studio single-item workspace both render the exact
// same capture/research/draft/proofing logic instead of forking it. No
// handler/endpoint/state behaviour changed in this move — see git history
// on ContentBoard.tsx for the pre-extraction version if a diff is needed.
//
// MSN-0363 addition (Proofing only): the AI-proposed revision now renders
// as Current Draft | AI Proposal side by side (desktop) / stacked (mobile)
// instead of only showing the proposal — brief §13 ("understand the
// proposed change before applying it"). Still no diff/highlight library;
// a plain two-column read is enough at this content length and avoids a
// new dependency.

import { useState } from 'react';
import { Badge, Button, Textarea, Select } from '@/components/ui';
import {
  STAGE_LABEL,
  QA_CHECKLIST_ITEMS,
  rankBadgeStatus,
  type ContentItem,
} from './shared';

export const FORMATS = [
  { key: 'linkedin_post', label: 'LinkedIn Post' },
  { key: 'executive_insight', label: 'Executive Insight' },
  { key: 'lessons_learned', label: 'Lessons Learned' },
  { key: 'case_study', label: 'Case Study' },
  { key: 'industry_commentary', label: 'Industry Commentary' },
  { key: 'article_draft', label: 'Article Draft' },
];

export function RankBadge({ score }: { score: number | null }) {
  if (score === null) return null;
  return <Badge status={rankBadgeStatus(score)}>{score.toFixed(1)}</Badge>;
}

export async function discard(id: string, currentTrigger: 'discard' = 'discard') {
  return fetch(`/api/comms/${id}/advance`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ trigger: currentTrigger }),
  });
}

// ── Capture stage body: research brief form ──────────────────────────────────

export function CaptureStageBody({ item, onChanged }: { item: ContentItem; onChanged: () => void }) {
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
      <p className="min-h-[1lh] text-[12px] text-wb-ink2" role="status" aria-live="polite">{msg}</p>
    </div>
  );
}

// ── Research stage body: confirmed brief + generate draft ────────────────────

export function ResearchStageBody({ item, onChanged }: { item: ContentItem; onChanged: () => void }) {
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
      <p className="min-h-[1lh] text-[12px] text-wb-ink2" role="status" aria-live="polite">{msg}</p>
    </div>
  );
}

// ── Content Prep stage body: draft editor + revision history + submit ────────

export function ContentPrepStageBody({ item, onChanged }: { item: ContentItem; onChanged: () => void }) {
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

  const words = body.trim() ? body.trim().split(/\s+/).length : 0;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-[11px] text-wb-ink2">
        <span>{words} word{words === 1 ? '' : 's'}</span>
      </div>
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
      <p className="min-h-[1lh] text-[12px] text-wb-ink2" role="status" aria-live="polite">{msg}</p>
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

export function ProofingStageBody({ item, onChanged }: { item: ContentItem; onChanged: () => void }) {
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
  const [suggestedBody, setSuggestedBody] = useState<string | null>(null);
  const [polishInstructions, setPolishInstructions] = useState('');
  const [polishBusy, setPolishBusy] = useState(false);
  const [polishMsg, setPolishMsg] = useState('');
  const [applyingSuggestion, setApplyingSuggestion] = useState(false);

  async function requestPolish() {
    setPolishBusy(true);
    setPolishMsg('');
    try {
      const res = await fetch(`/api/content-workbench/${item.id}/ai-polish`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instructions: polishInstructions || undefined }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      setSuggestedBody(d.suggested_body);
    } catch (e) {
      setPolishMsg(e instanceof Error ? e.message : 'AI revision failed');
    } finally {
      setPolishBusy(false);
    }
  }

  async function applySuggestion() {
    if (!suggestedBody) return;
    setApplyingSuggestion(true);
    setPolishMsg('');
    try {
      const res = await fetch(`/api/content-workbench/${item.id}/draft`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ body: suggestedBody }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      setSuggestedBody(null);
      setPolishInstructions('');
      // The applied text no longer matches whatever the checklist/AI review
      // was judged against — clear both so the human re-checks the new draft
      // rather than saving a stale pass/fail against text that changed.
      // Fleet Engineering Review 2026-08-11: this used to only be local
      // React state (setQaStatus('pending')) — the server's qa_status
      // (and the Approve button's own gate, which reads item.qa_status
      // from a fresh fetch, not this component's state) stayed whatever
      // it was before the revision, e.g. still qa_passed. Persist the
      // reset through the same /qa route saveQa() uses so a stale
      // approval can't survive a text swap.
      const resetChecklist = Object.fromEntries(QA_CHECKLIST_ITEMS.map((c) => [c.key, false]));
      setAiReview(null);
      setChecks(resetChecklist);
      const qaRes = await fetch(`/api/content-workbench/${item.id}/qa`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ qa_checklist: { ...resetChecklist, notes: qaNotes } }),
      });
      const qaData = await qaRes.json();
      setQaStatus(qaRes.ok ? qaData.qa_status : 'pending');
      setPolishMsg('✓ Revision applied — re-run AI review (or re-check manually) before approving.');
      onChanged();
    } catch (e) {
      setPolishMsg(e instanceof Error ? e.message : 'Error applying revision');
    } finally {
      setApplyingSuggestion(false);
    }
  }

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

  // Publishing used to be two separate Captain clicks (captain_confirmed
  // then mark_published) because mark_published briefly queued a Decide
  // approval on top of this same click. That gate never had a page behind
  // it, so it just stalled every item at ready_to_publish forever — see
  // api/comms/[id]/advance/route.ts's header comment. mark_published is a
  // direct flip again now, so this collapses to one button: from
  // 'approved' it fires captain_confirmed then mark_published back to
  // back; from 'ready_to_publish' (an item that reached that state under
  // the old two-step flow, pre-fix) it only needs the second call.
  async function publish() {
    setPublishBusy(true);
    setPublishMsg('');
    try {
      if (item.status === 'approved') {
        const r1 = await fetch(`/api/comms/${item.id}/advance`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ trigger: 'captain_confirmed' }),
        });
        const d1 = await r1.json();
        if (!r1.ok) throw new Error(d1.error);
      }
      const r2 = await fetch(`/api/comms/${item.id}/advance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trigger: 'mark_published' }),
      });
      const d2 = await r2.json();
      if (!r2.ok) throw new Error(d2.error);
      setPublishMsg('✓ Published');
      onChanged();
    } catch (e) {
      setPublishMsg(e instanceof Error ? e.message : 'Error publishing');
    } finally {
      setPublishBusy(false);
    }
  }

  if (item.status === 'approved' || item.status === 'ready_to_publish') {
    return (
      <div className="space-y-2 text-[13.5px]">
        <p className="flex flex-wrap items-center gap-1.5 text-wb-ok-on">
          <span className="rounded-full bg-wb-ok/15 px-2 py-0.5 font-semibold">✓ Approved</span>
          <span className="text-wb-ink2">
            {item.reviewed_by ? `by ${item.reviewed_by}` : ''}{item.reviewed_at ? ` · ${item.reviewed_at.slice(0, 10)}` : ''}
          </span>
        </p>
        <Button size="sm" onClick={publish} disabled={publishBusy} className="w-full">
          {publishBusy ? 'Publishing…' : 'Publish →'}
        </Button>
        <p className="min-h-[1lh] text-[12px] text-wb-ink2" role="status" aria-live="polite">{publishMsg}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3 text-[13.5px]">
      <div className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded-lg border border-wb-line bg-wb-bg p-3 leading-relaxed text-wb-ink">{item.body}</div>

      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed border-wb-sage/50 bg-wb-sage/5 p-2.5">
        <p className="text-[12px] text-wb-ink2">AI can take a first pass at the checklist below — you review and confirm.</p>
        <Button size="sm" variant="secondary" onClick={runAiReview} disabled={aiBusy} className="ml-auto">
          {aiBusy ? 'Reviewing…' : 'Run AI Review →'}
        </Button>
      </div>
      <p className="min-h-[1lh] text-[12px] text-wb-ink2" role="status" aria-live="polite">{aiMsg}</p>

      {!suggestedBody ? (
        <div className="space-y-1.5 rounded-lg border border-dashed border-wb-warn/50 bg-wb-warn/5 p-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <span aria-hidden className="text-[13px]">✎</span>
            <p className="text-[12px] text-wb-ink2">Or have AI propose a revised draft that addresses the concerns above.</p>
            <Button size="sm" variant="secondary" onClick={requestPolish} disabled={polishBusy} className="ml-auto">
              {polishBusy ? 'Revising…' : 'Ask AI to Revise Draft →'}
            </Button>
          </div>
          <input value={polishInstructions} onChange={(e) => setPolishInstructions(e.target.value)}
            placeholder="Optional: steer it — e.g. ‘tighten the close’, ‘cut the stat in paragraph 2’"
            className="w-full rounded-md border border-wb-line bg-wb-surface px-3 py-1.5 text-[12.5px] text-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep" />
        </div>
      ) : (
        <div className="space-y-2 rounded-lg border border-wb-warn/50 bg-wb-warn/5 p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-wb-warn-on">AI Proposes — You Decide</p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <div>
              <p className="mb-1 text-[10px] uppercase tracking-wide text-wb-ink2">Current Draft</p>
              <div className="max-h-64 overflow-y-auto whitespace-pre-wrap rounded-md border border-wb-line bg-wb-bg p-3 leading-relaxed text-wb-ink">{item.body}</div>
            </div>
            <div>
              <p className="mb-1 text-[10px] uppercase tracking-wide text-wb-ink2">AI Proposal</p>
              <div className="max-h-64 overflow-y-auto whitespace-pre-wrap rounded-md border border-wb-line bg-wb-surface p-3 leading-relaxed text-wb-ink">{suggestedBody}</div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={applySuggestion} disabled={applyingSuggestion}>
              {applyingSuggestion ? 'Applying…' : 'Apply as Revision →'}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setSuggestedBody(null)} disabled={applyingSuggestion}>
              Discard Suggestion
            </Button>
          </div>
        </div>
      )}
      <p className="min-h-[1lh] text-[12px] text-wb-ink2" role="status" aria-live="polite">{polishMsg}</p>

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
              {note && <p className="ml-6 mt-0.5 text-[11.5px] italic text-wb-ink2">AI · {note}</p>}
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
      <p className="min-h-[1lh] text-[12px] text-wb-ink2" role="status" aria-live="polite">{msg}</p>
    </div>
  );
}

/** Human-readable one-liner for Studio's stepper/header — not used by the
 * legacy Board (which uses STAGE_LABEL directly). */
export function stageStatusLine(item: ContentItem): string {
  if (item.status === 'ready_to_publish') return 'Approved — ready to publish';
  if (item.status === 'approved') return 'Approved — confirm to publish';
  if (item.stage === 'proofing') return item.qa_status === 'qa_passed' ? 'QA passed — ready for your decision' : 'In review — QA pending';
  return STAGE_LABEL[item.stage];
}
