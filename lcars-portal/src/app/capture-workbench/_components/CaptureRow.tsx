'use client';

// Phase C — capture inbox row with inline triage actions. Ported from the
// legacy Capture page CaptureRow. Reuses every lib/capture action and the
// /api/capture/[id] enrich proxy unchanged. Review-first governance preserved:
// promote-to-mission creates a candidate only. Route buttons are neutral per
// Captain decision 2026-07-12 (no department-hue rainbow).

import { useCallback, useState } from 'react';
import Link from 'next/link';
import {
  markCaptureReviewed,
  dismissCapture,
  archiveCapture,
  updateCaptureClassification,
  updateCaptureImportance,
  promoteCaptureToMission,
  routeCapture,
  type InboxCapture,
  type CaptureClassification,
  type CaptureImportance,
} from '@/lib/capture';
import { promoteCaptureToTask } from '@/lib/personalTasks';
import { SourceBadge, ClassBadge, AiBadge, VoiceMeta, AiSuggestion, parseSummary, fmtDate } from './badges';

const ROUTE_DEST: Record<string, { label: string; href: string }> = {
  personal:  { label: "Captain's Log", href: '/captains-log' },
  reference: { label: 'Knowledge Hub', href: '/knowledge-workbench?domain=memory' },
  decision:  { label: 'Decisions', href: '/knowledge-workbench?domain=memory&innerTab=decisions' },
  mission:   { label: 'Missions', href: '/missions' },
  research:  { label: 'Knowledge Hub', href: '/knowledge-workbench?domain=memory' },
};

type BtnTone = 'ok' | 'sage' | 'neutral';
const BTN_TONE: Record<BtnTone, string> = {
  ok:      'border-wb-ok/50 bg-wb-ok/10 text-wb-ok-on hover:bg-wb-ok/20',
  sage:    'border-wb-sage-deep/50 bg-wb-sage-deep/10 text-wb-sage-deep hover:bg-wb-sage-deep/20',
  neutral: 'border-wb-line text-wb-ink2 hover:border-wb-sage-deep/40 hover:text-wb-ink',
};

function ActionBtn({ label, onClick, disabled, tone }: { label: string; onClick: () => void; disabled: boolean; tone: BtnTone }) {
  return (
    <button type="button" disabled={disabled} onClick={onClick}
      className={`rounded-md border px-3 py-1 text-xs font-medium transition-colors disabled:opacity-40 ${BTN_TONE[tone]}`}>
      {label}
    </button>
  );
}

export function CaptureRow({ item, onRefresh }: { item: InboxCapture; onRefresh: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [showFullContent, setShowFullContent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [routedDest, setRoutedDest] = useState<{ label: string; href: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [newClass, setNewClass] = useState<CaptureClassification>(item.classification ?? 'unclassified');
  const [newImp, setNewImp] = useState<CaptureImportance>(item.importance ?? 'medium');
  const [suggestionDismissed, setSuggestionDismissed] = useState(false);

  const parsedSummary = parseSummary(item.summary as Record<string, unknown> | string | null);

  const act = useCallback(async (fn: () => Promise<{ ok: boolean; error?: string; mission_id?: string }>, label: string) => {
    setBusy(true);
    setErr(null);
    const res = await fn();
    setBusy(false);
    if (!res.ok) {
      setErr(res.error ?? 'Action failed.');
    } else {
      const msg = res.mission_id ? `${label} — Mission candidate: ${res.mission_id}` : label;
      setFlash(msg);
      setTimeout(() => { setFlash(null); onRefresh(); }, 1800);
    }
  }, [onRefresh]);

  const fullContent = item.raw_text ?? item.title ?? '';
  const preview = showFullContent ? fullContent : fullContent.slice(0, 300);
  const isVoice = item.source_channel_id === 'telegram-xo-voice-capture';

  return (
    <li className="flex flex-col rounded-md border border-wb-line bg-wb-surface transition-colors hover:border-wb-sage-deep/40">
      <button type="button" onClick={() => setExpanded((e) => !e)} className="flex w-full items-start gap-3 px-4 py-3 text-left">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-wb-ink">{item.title ?? '(untitled)'}</p>
          {isVoice && parsedSummary && <VoiceMeta summary={parsedSummary} />}
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <SourceBadge channelId={item.source_channel_id} />
            <ClassBadge classification={item.classification} />
            {item.importance && item.importance !== 'medium' && (
              <span className="text-[10px] uppercase tracking-wide text-wb-ink2">
                {item.importance === 'high' ? '▲ High' : '▼ Low'}
              </span>
            )}
            {item.requires_review && <span className="text-[10px] uppercase tracking-wide text-wb-warn-on">⚑ Review</span>}
            <AiBadge status={item.ai_enrichment_status} summary={parsedSummary} />
            <span className="ml-auto shrink-0 text-[10px] text-wb-ink2">{fmtDate(item.captured_at)}</span>
          </div>
        </div>
        <span className="shrink-0 text-xs text-wb-ink2">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="border-t border-wb-line px-4 pb-4 pt-3">
          {fullContent && (
            <div className="mb-3">
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-wb-ink2">{preview}</p>
              {fullContent.length > 300 && (
                <button type="button" onClick={() => setShowFullContent((v) => !v)}
                  className="mt-1 text-[10px] uppercase tracking-wider text-wb-sage-deep transition-colors hover:text-wb-sage-deep/70">
                  {showFullContent ? '▲ Show less' : `▼ Show full content (${fullContent.length} chars)`}
                </button>
              )}
            </div>
          )}

          {flash && (
            <div className="mb-2">
              <p className="text-xs text-wb-ok-on">✓ {flash}</p>
              {routedDest && (
                <Link href={routedDest.href} className="mt-1 inline-block text-[10px] uppercase tracking-wider text-wb-sage-deep hover:text-wb-sage-deep/70">
                  View in {routedDest.label} →
                </Link>
              )}
            </div>
          )}
          {err && <p className="mb-2 text-xs text-wb-crit-on">{err}</p>}

          {/* Classification + Importance pickers */}
          <div className="mb-3 flex flex-wrap gap-3">
            <label className="flex flex-col gap-1 text-[10px] uppercase tracking-wide text-wb-ink2">
              Classification
              <select value={newClass} disabled={busy} onChange={(e) => setNewClass(e.target.value as CaptureClassification)}
                className="rounded-md border border-wb-line bg-wb-bg px-2 py-1 text-xs normal-case tracking-normal text-wb-ink">
                <option value="reference">Note / Reference</option>
                <option value="mission">Mission</option>
                <option value="personal">Health / Personal</option>
                <option value="research">Idea / Research</option>
                <option value="decision">Decision</option>
                <option value="unclassified">Unclassified</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-[10px] uppercase tracking-wide text-wb-ink2">
              Importance
              <select value={newImp} disabled={busy} onChange={(e) => setNewImp(e.target.value as CaptureImportance)}
                className="rounded-md border border-wb-line bg-wb-bg px-2 py-1 text-xs normal-case tracking-normal text-wb-ink">
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </label>
            <div className="flex items-end">
              <button type="button" disabled={busy}
                onClick={() => act(async () => {
                  const r1 = await updateCaptureClassification(item.id, newClass);
                  if (!r1.ok) return r1;
                  return updateCaptureImportance(item.id, newImp);
                }, 'Classification updated')}
                className="rounded-md border border-wb-sage-deep/50 bg-wb-sage-deep/10 px-3 py-1 text-xs text-wb-sage-deep hover:bg-wb-sage-deep/20 disabled:opacity-40">
                Save changes
              </button>
            </div>
          </div>

          {/* AI enrichment — suggestion if pending, analysis summary if actioned */}
          {item.ai_enrichment_status === 'enriched' && !suggestionDismissed && (
            <AiSuggestion
              summary={parsedSummary}
              onAccept={(cls) => {
                setRoutedDest(ROUTE_DEST[cls] ?? null);
                act(async () => {
                  const r1 = await updateCaptureClassification(item.id, cls as CaptureClassification);
                  if (!r1.ok) return r1;
                  return markCaptureReviewed(item.id);
                }, `AI suggestion accepted — ${cls}`);
              }}
              onDismiss={() => setSuggestionDismissed(true)}
            />
          )}
          {item.ai_enrichment_status === 'enriched' && suggestionDismissed && parsedSummary?.ai_reasoning && (
            <div className="mb-3 rounded-md border border-wb-line bg-wb-bg px-3 py-2">
              <p className="mb-1 text-[10px] uppercase tracking-wide text-wb-ink2">✦ AI Analysis</p>
              <p className="text-[11px] italic text-wb-ink2">{parsedSummary.ai_reasoning}</p>
            </div>
          )}

          {/* Action buttons */}
          <div className="flex flex-wrap gap-2">
            <ActionBtn disabled={busy} tone="ok" label="Mark reviewed" onClick={() => act(() => markCaptureReviewed(item.id), 'Marked reviewed')} />
            <ActionBtn disabled={busy} tone="neutral" label="Route as Health log" onClick={() => { setRoutedDest(ROUTE_DEST.personal); act(() => routeCapture(item.id, 'personal'), "Routed → Captain's Log"); }} />
            <ActionBtn disabled={busy} tone="neutral" label="Route as Note" onClick={() => { setRoutedDest(ROUTE_DEST.reference); act(() => routeCapture(item.id, 'reference'), 'Routed → Note'); }} />
            <ActionBtn disabled={busy} tone="neutral" label="Route as Decision" onClick={() => { setRoutedDest(ROUTE_DEST.decision); act(() => routeCapture(item.id, 'decision'), 'Routed → Decision queue'); }} />
            <ActionBtn disabled={busy} tone="sage" label="→ Promote to Mission" onClick={() => act(() => promoteCaptureToMission(item.id), 'Mission candidate created')} />
            <ActionBtn disabled={busy} tone="sage" label="→ Send to Ready Room" onClick={() => act(() => promoteCaptureToTask(item.id, item.title ?? fullContent.slice(0, 120) ?? 'Untitled task'), 'Sent to Ready Room')} />
            <ActionBtn disabled={busy} tone="neutral" label="Archive" onClick={() => act(() => archiveCapture(item.id), 'Archived')} />
            <ActionBtn disabled={busy} tone="neutral" label="Dismiss" onClick={() => act(() => dismissCapture(item.id), 'Dismissed')} />
          </div>

          {/* AI enrichment trigger — only when not yet enriched */}
          {item.ai_enrichment_status !== 'enriched' && (
            <div className="mt-3 flex items-center gap-2 rounded-md border border-dashed border-wb-line px-3 py-2">
              <span className="text-[10px] uppercase tracking-wide text-wb-ink2">AI enrichment</span>
              <button type="button" disabled={busy || item.ai_enrichment_status === 'queued'}
                onClick={() => act(async () => {
                  // Server-side proxy now bounds this to 15s on its own
                  // (WORKBENCH-REVIEW.md Medium finding, 2026-07-18), but a
                  // client-side ceiling too means a Next.js-server-level
                  // hang (unrelated to Command Centre) can't hang this UI.
                  const resp = await fetch(`/api/capture/${item.id}?action=enrich`, {
                    method: 'POST',
                    signal: AbortSignal.timeout(20_000),
                  });
                  const json = await resp.json().catch(() => ({}));
                  if (!resp.ok) return { ok: false, error: json?.error ?? 'Command Centre unreachable' };
                  if (json?.data?.enriched === false) return { ok: false, error: json?.data?.error ?? 'Enrichment failed' };
                  return { ok: true };
                }, 'AI enrichment complete')}
                className="rounded-md border border-wb-sage-deep/40 bg-wb-sage-deep/10 px-2 py-0.5 text-[10px] text-wb-sage-deep hover:bg-wb-sage-deep/20 disabled:opacity-40">
                {item.ai_enrichment_status === 'queued' ? 'Queued…' : '✦ Enrich with AI'}
              </button>
              <span className="text-[10px] text-wb-ink2">Suggests classification + route</span>
            </div>
          )}
        </div>
      )}
    </li>
  );
}
