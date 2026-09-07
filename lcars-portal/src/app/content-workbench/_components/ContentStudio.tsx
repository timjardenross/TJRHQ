'use client';

// Content Studio (MSN-0363) — the single-item focused workspace brief §9
// asks for: one place with the editor, research/sources, governance, and
// AI actions, instead of the old cramped-column-into-a-Modal pattern.
//
// Deliberately NOT a fork of the stage logic: CaptureStageBody/
// ResearchStageBody/ContentPrepStageBody/ProofingStageBody all come from
// stageBodies.tsx unchanged — this component only supplies the surrounding
// layout (header, stepper, side intelligence panel) and picks which stage
// body to render, exactly like ContentBoard.tsx's ItemCard Modal already
// did. Both entry points (the legacy Board's Modal and this Studio) stay
// on one canonical implementation per stage.

import { useEffect, useState } from 'react';
import { Badge, Button, ProgressSteps } from '@/components/ui';
import {
  STAGE_LABEL,
  PILLAR_LABEL,
  rankBadgeStatus,
  type ContentItem,
} from './shared';
import {
  discard,
  CaptureStageBody,
  ResearchStageBody,
  ContentPrepStageBody,
  ProofingStageBody,
  stageStatusLine,
} from './stageBodies';

function progressSteps(item: ContentItem) {
  const captured = true;
  const researched = !!item.research_completed_at;
  const drafted = !!item.body;
  const reviewed = item.qa_status === 'qa_passed' || item.status === 'approved' || item.status === 'ready_to_publish';
  // GET /api/content-workbench only ever returns pre-published items (see
  // its own header comment) — Studio never actually sees status
  // 'published', so this step is always the "not yet" state here by
  // construction. Kept in the stepper for a shared, complete mental model.
  const published = false;
  return [
    { key: 'capture', label: 'Capture', complete: captured },
    { key: 'research', label: 'Research', complete: researched },
    { key: 'draft', label: 'Draft', complete: drafted },
    { key: 'review', label: 'Review', complete: reviewed },
    { key: 'publish', label: 'Publish', complete: published },
  ];
}

function ScheduleControl({ item, onChanged }: { item: ContentItem; onChanged: () => void }) {
  const [value, setValue] = useState(item.scheduled_for ? item.scheduled_for.slice(0, 16) : '');
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');

  async function save(nextValue: string | null) {
    setSaving(true);
    setMsg('');
    try {
      const res = await fetch(`/api/content-workbench/${item.id}/schedule`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scheduled_for: nextValue }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      const base = nextValue ? '✓ Scheduled' : '✓ Unscheduled';
      setMsg(d.calendar_synced === false && d.calendar_warning ? `${base} — ${d.calendar_warning}` : `${base}${d.calendar_synced ? ' (calendar event synced)' : ''}`);
      onChanged();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Error scheduling');
    } finally {
      setSaving(false);
    }
  }

  if (item.status !== 'approved' && item.status !== 'ready_to_publish') return null;

  return (
    <div className="space-y-2 rounded-lg border border-wb-line bg-wb-surface p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-wb-ink2">Schedule</p>
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="datetime-local"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="rounded-md border border-wb-line bg-wb-bg px-2 py-1.5 text-[12.5px] text-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep"
        />
        <Button size="sm" variant="secondary" onClick={() => save(value ? new Date(value).toISOString() : null)} disabled={saving || !value}>
          {saving ? 'Saving…' : 'Use This Time'}
        </Button>
        {item.scheduled_for && (
          <Button size="sm" variant="secondary" onClick={() => { setValue(''); save(null); }} disabled={saving}>
            Clear
          </Button>
        )}
      </div>
      <p className="min-h-[1lh] text-[11.5px] text-wb-ink2" role="status" aria-live="polite">{msg}</p>
    </div>
  );
}

export function ContentStudio({ item, onChanged, onClose }: { item: ContentItem; onChanged: () => void; onClose: () => void }) {
  const [pendingDiscard, setPendingDiscard] = useState(false);
  const [discarding, setDiscarding] = useState(false);

  async function confirmDiscard() {
    setDiscarding(true);
    try {
      const res = await discard(item.id);
      if (res.ok) { onChanged(); onClose(); }
    } finally {
      setDiscarding(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="secondary" onClick={onClose}>← Back</Button>
        <h2 className="text-[15px] font-semibold text-wb-ink">{item.title}</h2>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {item.rank_score !== null && <Badge status={rankBadgeStatus(item.rank_score)}>{item.rank_score.toFixed(0)} / 100</Badge>}
        {item.pillar && (
          <span className="rounded-full bg-wb-line px-2 py-0.5 text-[10.5px] font-medium text-wb-ink2">
            {PILLAR_LABEL[item.pillar] ?? item.pillar}
          </span>
        )}
        {item.captain_focus && <span className="rounded-full bg-wb-warn/15 px-2 py-0.5 text-[10.5px] font-semibold text-wb-warn-on">★ Captain Focus</span>}
        <span className="text-[11.5px] text-wb-ink2">{stageStatusLine(item)}</span>
      </div>

      <ProgressSteps steps={progressSteps(item)} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_280px]">
        <div className="min-w-0 rounded-xl border border-wb-line bg-wb-surface p-4">
          {item.stage === 'capture' && <CaptureStageBody item={item} onChanged={onChanged} />}
          {item.stage === 'research' && <ResearchStageBody item={item} onChanged={onChanged} />}
          {item.stage === 'content_prep' && <ContentPrepStageBody item={item} onChanged={onChanged} />}
          {item.stage === 'proofing' && <ProofingStageBody item={item} onChanged={onChanged} />}
        </div>

        <div className="space-y-3">
          <div className="space-y-1.5 rounded-lg border border-wb-line bg-wb-surface p-3 text-[12px]">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-wb-ink2">Content Intelligence</p>
            <p className="text-wb-ink2">Stage <span className="text-wb-ink">{STAGE_LABEL[item.stage]}</span></p>
            <p className="text-wb-ink2">Source <span className="text-wb-ink">{item.source_kind?.replace(/_/g, ' ') ?? '—'}</span></p>
          </div>

          <div className="space-y-1.5 rounded-lg border border-wb-line bg-wb-surface p-3 text-[12px]">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-wb-ink2">Research</p>
            <p className="text-wb-ink2">
              {(item.research_sources ?? []).length} source{(item.research_sources ?? []).length === 1 ? '' : 's'}
              {item.research_completed_at ? ' · Complete ✓' : ' · Not complete'}
            </p>
          </div>

          <div className="space-y-1.5 rounded-lg border border-wb-line bg-wb-surface p-3 text-[12px]">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-wb-ink2">Governance</p>
            {(['accuracy', 'brand_voice', 'compliance', 'links_checked'] as const).map((k) => {
              const checked = (item.qa_checklist as Record<string, unknown> | null)?.[k] === true;
              return (
                <p key={k} className="flex items-center justify-between text-wb-ink2">
                  <span>{k.replace(/_/g, ' ')}</span>
                  <span className={checked ? 'text-wb-ok-on' : 'text-wb-ink2'}>{checked ? '✓' : '○'}</span>
                </p>
              );
            })}
          </div>

          <ScheduleControl item={item} onChanged={onChanged} />

          <div className="border-t border-wb-line pt-3">
            {!pendingDiscard ? (
              <button type="button" onClick={() => setPendingDiscard(true)} className="text-[12px] text-wb-crit-on hover:underline">
                Discard this item
              </button>
            ) : (
              <div className="flex items-center gap-2 rounded-md border border-wb-crit/40 bg-wb-crit/5 p-2">
                <p className="flex-1 text-[12px] text-wb-crit-on">Archive — reversible, not deleted.</p>
                <Button size="sm" variant="secondary" onClick={confirmDiscard} disabled={discarding}>
                  {discarding ? 'Archiving…' : 'Confirm'}
                </Button>
                <Button size="sm" variant="secondary" onClick={() => setPendingDiscard(false)} disabled={discarding}>
                  Cancel
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/** Fetch-then-render wrapper so callers (Today/Queue/Library) can open
 * Studio with just an id, without each keeping its own full item fetch. */
export function ContentStudioById({ contentId, onChanged, onClose }: { contentId: string; onChanged: () => void; onClose: () => void }) {
  const [item, setItem] = useState<ContentItem | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const res = await fetch('/api/content-workbench');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'Failed to load item');
      const found = (data.items as ContentItem[]).find((i) => i.id === contentId);
      if (!found) { setError('Item not found — it may have been discarded or already advanced past this board.'); return; }
      setItem(found);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load item');
    }
  }

  useEffect(() => { load(); }, [contentId]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleChanged() {
    onChanged();
    load();
  }

  if (error) return <p className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">{error}</p>;
  if (!item) return <p className="text-sm text-wb-ink2">Loading…</p>;
  return <ContentStudio item={item} onChanged={handleChanged} onClose={onClose} />;
}
