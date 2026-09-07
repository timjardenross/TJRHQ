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
// Proofing now carries the flow through to actual publish: 'approved' and
// 'ready_to_publish' both render inside the Proofing column (see
// GET /api/content-workbench's stageOf()) behind a single "Publish"
// button (ProofingStageBody's publish()) — the Captain is the one
// clicking Approve, QA, and Publish in this same modal already, so
// there's no second party for an extra confirmation step to gate
// against (see the advance route's own comment for why the earlier
// two-click propose/approve version of this got reverted). 'published'
// items show up in this workbench's own Portfolio tab.
//
// 2026-08 visual redesign (Content Workbench only, per user request — see
// STAGE_ACCENT in shared.ts): every function/handler below is unchanged
// from the pre-redesign version. This pass touches JSX structure and
// Tailwind classes on ItemCard/Column/the board wrapper, plus adds a
// pipeline-overview strip up top.
//
// 2026-08 follow-up #2: the 4-column board was cramped inside WorkbenchShell's
// default max-w-4xl. Added an opt-in `wide` prop to WorkbenchShell itself
// (max-w-7xl) rather than forking the shell here — this page.tsx now passes
// `wide`, every other workbench is unaffected.
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

import { useEffect, useRef, useState } from 'react';
import { Badge, Button, Modal } from '@/components/ui';
import {
  STAGE_LABEL,
  STAGE_HINT,
  STAGE_ACCENT,
  PILLAR_LABEL,
  type Stage,
  type ContentItem,
} from './shared';
import {
  RankBadge,
  discard,
  sendBackToResearch,
  CaptureStageBody,
  ResearchStageBody,
  ContentPrepStageBody,
  ProofingStageBody,
} from './stageBodies';

const STAGES: Stage[] = ['capture', 'research', 'content_prep', 'proofing'];

// ── Card shell — collapsed preview + Modal detail view ───────────────────────

const DISCARD_GRACE_MS = 5000;

function ItemCard({ item, onChanged }: { item: ContentItem; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  // 2026-08-29 (design-audit): discard -> 'archived' is genuinely
  // reversible (comms_content stays, just off the active board — see
  // api/comms/[id]/advance TRANSITIONS comment), so a blocking confirm
  // dialog was the wrong pattern for it. No un-archive trigger exists on
  // that route yet, so real post-commit undo isn't available - this
  // instead delays the actual API call for a grace window and lets Undo
  // cancel it before it ever fires, which is the confirm-free pattern that
  // doesn't require a new backend capability.
  const [pendingDiscard, setPendingDiscard] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const discardTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [sendingBack, setSendingBack] = useState(false);
  const [sendBackMsg, setSendBackMsg] = useState('');
  const accent = STAGE_ACCENT[item.stage];

  // Unlike discard (archived, off the board — see the grace-window comment
  // above), sending back to Research is a normal forward-compatible workflow
  // move like officer_submitted/captain_approved elsewhere in this workbench,
  // so it fires directly with no undo window.
  async function handleSendBack() {
    setSendingBack(true);
    setSendBackMsg('');
    try {
      const res = await sendBackToResearch(item.id);
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.error);
      }
      setOpen(false);
      onChanged();
    } catch (e) {
      setSendBackMsg(e instanceof Error ? e.message : 'Error sending back to research');
    } finally {
      setSendingBack(false);
    }
  }

  useEffect(() => () => { if (discardTimer.current) clearTimeout(discardTimer.current); }, []);

  function startDiscard() {
    setPendingDiscard(true);
    discardTimer.current = setTimeout(async () => {
      setDiscarding(true);
      try {
        const res = await discard(item.id);
        if (res.ok) { setOpen(false); onChanged(); }
      } finally {
        setDiscarding(false);
        setPendingDiscard(false);
      }
    }, DISCARD_GRACE_MS);
  }

  function cancelDiscard() {
    if (discardTimer.current) clearTimeout(discardTimer.current);
    discardTimer.current = null;
    setPendingDiscard(false);
  }

  const chipRow = (
    <div className="flex flex-wrap items-center gap-1.5">
      <RankBadge score={item.rank_score} />
      {item.pillar && (
        <span className="rounded-full bg-wb-line px-2 py-0.5 text-[10.5px] font-medium text-wb-ink2">
          {PILLAR_LABEL[item.pillar] ?? item.pillar}
        </span>
      )}
      {item.captain_focus && <span className="rounded-full bg-wb-warn/15 px-2 py-0.5 text-[10.5px] font-semibold text-wb-warn-on">★ Priority</span>}
      {item.sensitive && <Badge status="error">! Sensitive</Badge>}
    </div>
  );

  return (
    <>
      <div className="overflow-hidden rounded-xl border border-wb-line bg-wb-surface shadow-sm transition-shadow hover:shadow-md">
        <div className="flex">
          <span className={`w-[3px] shrink-0 ${accent.bar}`} aria-hidden />
          <button type="button" onClick={() => setOpen(true)}
            className="w-full space-y-1.5 p-3 text-left transition-colors hover:bg-wb-line/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
            <div className="flex flex-wrap items-center gap-1.5">
              {chipRow}
              <span aria-hidden className="ml-auto text-[13px] text-wb-ink2">⤢</span>
            </div>
            <p className="break-words text-[13.5px] font-medium leading-snug text-wb-ink">{item.title}</p>
          </button>
        </div>
        <p className="border-t border-wb-line/70 px-3 py-1.5 text-[10px] text-wb-ink2">
          Created {item.created_at.slice(0, 10)}
          {item.source_kind && ` · ${item.source_kind.replace(/_/g, ' ')}`}
        </p>
      </div>

      <Modal open={open} onClose={() => { setOpen(false); cancelDiscard(); }} title={item.title} variant="preview">
        <div className="mb-4 space-y-2">
          {chipRow}
          <p className="text-[11px] uppercase tracking-wide text-wb-ink2">{STAGE_LABEL[item.stage]}</p>
        </div>

        {item.stage === 'capture' && <CaptureStageBody item={item} onChanged={onChanged} />}
        {item.stage === 'research' && <ResearchStageBody item={item} onChanged={onChanged} />}
        {item.stage === 'content_prep' && <ContentPrepStageBody item={item} onChanged={onChanged} />}
        {item.stage === 'proofing' && <ProofingStageBody item={item} onChanged={onChanged} />}

        <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-wb-line pt-3">
          {(item.stage === 'content_prep' || item.stage === 'proofing') && !pendingDiscard && (
            <button type="button" onClick={handleSendBack} disabled={sendingBack}
              className="text-[12px] text-wb-ink2 hover:underline disabled:opacity-60" aria-label={`Send "${item.title}" back to Research`}>
              {sendingBack ? 'Sending back…' : '← Send Back to Research'}
            </button>
          )}
          {!pendingDiscard ? (
            <button type="button" onClick={startDiscard}
              className="text-[12px] text-wb-crit-on hover:underline" aria-label={`Discard "${item.title}"`}>
              Discard this item
            </button>
          ) : (
            <div className="flex items-center gap-2 rounded-md border border-wb-crit/40 bg-wb-crit/5 p-2">
              <p className="flex-1 text-[12px] text-wb-crit-on">
                {discarding ? 'Discarding…' : 'Discarded — removed from the board, not deleted.'}
              </p>
              <Button size="sm" variant="secondary" onClick={cancelDiscard} disabled={discarding}>
                Undo
              </Button>
            </div>
          )}
        </div>
        {sendBackMsg && <p className="mt-1 text-[12px] text-wb-crit-on" role="status" aria-live="polite">{sendBackMsg}</p>}
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
      <div className={`h-1 rounded-full ${accent.bar}`} aria-hidden />
      <div className="flex items-center gap-1.5 px-1 py-1">
        <span aria-hidden className="text-[12px]">{accent.icon}</span>
        <p className="text-[11px] font-semibold uppercase tracking-wide text-wb-ink">{STAGE_LABEL[stage]}</p>
        <span className={`ml-auto rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${accent.chip}`}>{items.length}</span>
      </div>
      <p className="px-1 text-[9.5px] italic leading-tight text-wb-ink2">{STAGE_HINT[stage]}</p>
      <div className="flex flex-col gap-2" role="list" aria-label={`Items in ${STAGE_LABEL[stage]}`}>
        {items.map((item) => (<ItemCard key={item.id} item={item} onChanged={onChanged} />))}
        {items.length === 0 && <p className="py-4 text-center text-[10px] text-wb-ink2">Empty</p>}
      </div>
    </div>
  );
}

/** Compact funnel strip above the board — quick read of where volume sits.
 * 2026-08-09 mobile/iPad review (P1): below `sm` this doubles as the stage
 * picker for the single-column mobile board (see ContentBoard) — tapping
 * a stage here is how you switch which column you're looking at, instead
 * of horizontal-scrolling through all 4 at once. Above `sm` it's still
 * just a read-only overview, unchanged. */
function PipelineOverview({
  counts,
  activeStage,
  onSelectStage,
}: {
  counts: Record<Stage, number>;
  activeStage?: Stage;
  onSelectStage?: (stage: Stage) => void;
}) {
  return (
    <div className="mb-3 flex items-center gap-1.5 overflow-x-auto rounded-lg border border-wb-line bg-wb-surface px-2.5 py-2">
      {STAGES.map((stage, i) => {
        const accent = STAGE_ACCENT[stage];
        const isActive = onSelectStage && activeStage === stage;
        const chip = (
          <div className={`flex items-center gap-1.5 rounded-full py-1 pl-1 pr-2.5 ${isActive ? 'bg-wb-line' : ''}`}>
            <span className={`grid h-5 w-5 shrink-0 place-items-center rounded-full text-[10px] font-semibold text-white ${accent.bar}`} aria-hidden>
              {counts[stage]}
            </span>
            <span className="text-[11px] font-medium text-wb-ink2">{STAGE_LABEL[stage]}</span>
          </div>
        );
        return (
          <div key={stage} className="flex shrink-0 items-center gap-1.5">
            {onSelectStage ? (
              <button type="button" onClick={() => onSelectStage(stage)} aria-pressed={isActive}
                className="rounded-full transition active:scale-95 sm:pointer-events-none">
                {chip}
              </button>
            ) : chip}
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
  // 2026-08-09 mobile/iPad review (P1): the 4-column board's only mobile
  // fallback was horizontal-scroll through all 4 at min-w-[264px] each —
  // functional but a real working-memory cost on a phone (easy to lose
  // which column you scrolled to, no way to see "what's in each stage"
  // without scrolling through all of them). Below `sm`, render exactly
  // one stage at a time instead, switched via the PipelineOverview strip
  // acting as a stage picker.
  const [activeMobileStage, setActiveMobileStage] = useState<Stage>('capture');
  // 2026-08-09 fix: the mobile single-column board always opened on
  // 'capture' regardless of where the actual items were, so a Captain
  // opening the board on a phone with nothing to capture (the common
  // case — most work sits in later stages) landed on an empty column
  // and had to know to tap over. Auto-pick the first non-empty stage on
  // the initial load only; once the Captain has tapped a stage
  // themselves, respect that choice on subsequent refreshes instead of
  // yanking them back.
  const userPickedMobileStage = useRef(false);

  function selectMobileStage(stage: Stage) {
    userPickedMobileStage.current = true;
    setActiveMobileStage(stage);
  }

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
      if (!userPickedMobileStage.current && data.counts) {
        const firstNonEmpty = STAGES.find((s) => (data.counts[s] ?? 0) > 0);
        if (firstNonEmpty) setActiveMobileStage(firstNonEmpty);
      }
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
          {counts && (
            <PipelineOverview counts={counts} activeStage={activeMobileStage} onSelectStage={selectMobileStage} />
          )}
          {/* sm+: full multi-column board, unchanged. */}
          <div className="hidden gap-3 overflow-x-auto pb-2 sm:flex">
            {STAGES.map((stage) => (
              <Column key={stage} stage={stage} items={items.filter((i) => i.stage === stage)} onChanged={load} />
            ))}
          </div>
          {/* below sm: single active stage only, picked via the strip above. */}
          <div className="sm:hidden">
            <Column stage={activeMobileStage} items={items.filter((i) => i.stage === activeMobileStage)} onChanged={load} />
          </div>
        </>
      )}
    </div>
  );
}
