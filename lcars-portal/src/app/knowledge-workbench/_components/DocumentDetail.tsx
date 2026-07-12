'use client';

import { Card } from '@/components/ui/Card';
import { StatusBadge } from '@/components/StatusBadge';
import { assignCategory } from '@/lib/categoryPropagation';
import { DECISION_LABELS, REVIEW_STATUS_LABELS, sensitivityTone } from './badges';
import type { ProcessingDocument, ProcessingChunk, ReviewDecision } from '@/lib/types';

interface DocumentDetailProps {
  selectedId: string | null;
  detail: ProcessingDocument | null;
  chunkPreview: ProcessingChunk[];
  detailLoading: boolean;
  detailError: string | null;
  reasonFor: ReviewDecision | null;
  reasonDraft: string;
  acting: string | null;
  flash?: { msg: string; ok: boolean } | null;
  onClose: () => void;
  onSetReasonFor: (decision: ReviewDecision | null) => void;
  onSetReasonDraft: (reason: string) => void;
  onDecide: (id: string, decision: ReviewDecision, reason?: string) => void;
}

export function DocumentDetail({
  selectedId,
  detail,
  chunkPreview,
  detailLoading,
  detailError,
  reasonFor,
  reasonDraft,
  acting,
  flash,
  onClose,
  onSetReasonFor,
  onSetReasonDraft,
  onDecide,
}: DocumentDetailProps) {
  if (!selectedId) return null;

  return (
    <Card className="lg:w-[420px] p-4">
      <div className="mb-3 flex items-start justify-between">
        <div>
          <h3 className="font-serif text-[14px] uppercase tracking-wide text-wb-ink">
            Document Detail
          </h3>
          <p className="mt-1 text-[10px] uppercase tracking-[0.2em] text-wb-ink2">
            j/k or ↓/↑ next-prev · a approve · m metadata-only
          </p>
        </div>
        <button
          onClick={onClose}
          className="text-[10px] uppercase tracking-[0.2em] text-wb-ink2 hover:text-wb-ink transition-colors"
        >
          Close
        </button>
      </div>
      {detailError ? (
        <div className="rounded border border-wb-crit/40 bg-operations/10 px-3 py-2 text-xs text-wb-crit-on">
          {detailError.includes('session has expired') ? (
            <>
              {detailError} <a href="/login" className="font-semibold underline">
                Sign in again
              </a>
              .
            </>
          ) : (
            <>Failed to load document: {detailError}</>
          )}
        </div>
      ) : detailLoading || !detail ? (
        <p className="text-xs text-wb-ink2 animate-pulse">Loading…</p>
      ) : (
        <div className="flex flex-col gap-3">
          <div>
            <p className="text-sm font-semibold text-wb-ink">{detail.filename}</p>
            <p className="mt-0.5 break-all text-[10px] text-wb-ink2">{detail.source_path}</p>
          </div>

          <div className="flex flex-wrap gap-1.5">
            <StatusBadge label={detail.status} status={detail.status} />
            <StatusBadge label={detail.sensitivity} tone={sensitivityTone(detail.sensitivity)} />
            {detail.category && <StatusBadge label={detail.category} tone="science" />}
            {detail.memory_document_id && (
              <StatusBadge label="Committed to Memory" tone="medical" />
            )}
            {detail.review_decision && !detail.memory_document_id && (
              <StatusBadge
                label={DECISION_LABELS[detail.review_decision]}
                tone={detail.review_decision === 'rejected' ? 'operations' : 'command'}
              />
            )}
          </div>

          {(detail.sensitivity === 'sensitive' || detail.sensitivity === 'restricted') && (
            <div className="rounded border border-wb-crit/40 bg-operations/10 px-3 py-2 text-[11px] text-wb-crit-on">
              Flagged {detail.sensitivity} — review carefully before approving into memory.
            </div>
          )}

          <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
            <dt className="text-wb-ink2">OCR status</dt>
            <dd className="text-wb-ink">
              {detail.ocr_used ? `OCR (${detail.ocr_engine ?? 'unknown engine'})` : detail.status === 'ocr_required' ? 'Required — pending' : 'Not required'}
            </dd>
            <dt className="text-wb-ink2">Tags</dt>
            <dd className="text-wb-ink">{detail.tags?.length ? detail.tags.join(', ') : '—'}</dd>
            <dt className="text-wb-ink2">Memory recommendation</dt>
            <dd className="text-wb-ink">{detail.memory_recommendation ?? '—'}</dd>
            <dt className="text-wb-ink2">Chunks</dt>
            <dd className="text-wb-ink">{detail.chunk_count}</dd>
            <dt className="text-wb-ink2">Memory category (if approved)</dt>
            <dd className="text-wb-ink">{assignCategory('Personal Archive', detail.category ?? null)}</dd>
            <dt className="text-wb-ink2">Document date</dt>
            <dd className="text-wb-ink">Not tracked by this pipeline</dd>
          </dl>

          {detail.summary && (
            <div>
              <p className="text-[10px] uppercase tracking-[0.2em] text-wb-ink2">Summary</p>
              <p className="mt-1 text-xs text-wb-ink">{detail.summary}</p>
            </div>
          )}

          {detail.failure_reason && (
            <div className="rounded border border-wb-crit/40 bg-operations/10 px-3 py-2 text-[11px] text-wb-crit-on">
              Failed: {detail.failure_reason}
            </div>
          )}

          {chunkPreview.length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer text-[10px] uppercase tracking-[0.2em] text-wb-ink2">
                Chunk preview ({chunkPreview.length} of {detail.chunk_count})
              </summary>
              <ul className="mt-2 flex flex-col gap-2">
                {chunkPreview.map((c) => (
                  <li key={c.id} className="rounded border border-wb-line bg-wb-surface-2/60 p-2 text-[11px] text-wb-ink2">
                    #{c.chunk_index}: {c.chunk_text.slice(0, 160)}
                    {c.chunk_text.length > 160 ? '…' : ''}
                  </li>
                ))}
              </ul>
            </details>
          )}

          {flash && (
            <div className={`rounded border px-3 py-2 text-xs ${flash.ok ? 'border-status/40 bg-status/10 text-status' : 'border-wb-crit/40 bg-operations/10 text-wb-crit-on'}`}>
              {flash.msg}
            </div>
          )}

          {detail.review_status === 'resolved' || detail.review_status === 'rejected' ? (
            <div className="rounded border border-wb-line bg-wb-surface-2/60 px-3 py-2 text-[11px] text-wb-ink2">
              {REVIEW_STATUS_LABELS[detail.review_status]}: {detail.review_decision ? DECISION_LABELS[detail.review_decision] : '—'}
              {detail.review_decided_by ? ` by ${detail.review_decided_by}` : ''}
              {detail.review_reason ? ` — "${detail.review_reason}"` : ''}
            </div>
          ) : detail.status !== 'awaiting_review' ? (
            <p className="text-[11px] text-wb-ink2">
              Not yet ready for review — still in the processing pipeline ({detail.status}).
            </p>
          ) : reasonFor ? (
            <div className="flex flex-col gap-2">
              <input
                type="text"
                placeholder={`Reason for ${DECISION_LABELS[reasonFor].toLowerCase()} (required)`}
                value={reasonDraft}
                onChange={(e) => onSetReasonDraft(e.target.value)}
                className="w-full rounded border border-wb-line bg-wb-surface px-2 py-1.5 text-xs text-wb-ink placeholder:text-wb-ink2 focus:border-wb-crit/60 focus:outline-none"
              />
              <div className="flex gap-2">
                <button
                  disabled={!reasonDraft.trim() || acting === detail.id}
                  onClick={() => onDecide(detail.id, reasonFor, reasonDraft.trim())}
                  className="flex-1 rounded border border-wb-crit/60 bg-operations/10 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-wb-crit-on hover:bg-operations/20 disabled:opacity-40 transition-colors"
                >
                  {acting === detail.id ? 'Working…' : `Confirm ${DECISION_LABELS[reasonFor]}`}
                </button>
                <button
                  onClick={() => {
                    onSetReasonFor(null);
                    onSetReasonDraft('');
                  }}
                  className="rounded border border-wb-line px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-wb-ink2 hover:text-wb-ink transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              {detail.review_status === 'awaiting_followup' && (
                <div className="rounded border border-command/40 bg-command/10 px-3 py-2 text-[11px] text-command">
                  Awaiting follow-up — previously marked &ldquo;Needs Review&rdquo;
                  {detail.review_reason ? `: "${detail.review_reason}"` : ''}. Choose a decision below to resolve it.
                </div>
              )}
              <p className="mb-1 text-[10px] text-wb-ink2">
                Approve writes {detail.summary ? 'the summary above' : `a metadata-only stub ("${detail.filename}")`} as
                the memory content, plus full chunk/embedding copy either way — same searchable content regardless of
                which Approve button, only the readable text differs. Approve — Metadata Only always uses the stub,
                even if a summary exists.
              </p>
              <button
                disabled={acting === detail.id}
                onClick={() => onDecide(detail.id, 'approved_chunks')}
                className="rounded border border-status/60 bg-status/10 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-status hover:bg-status/20 disabled:opacity-40 transition-colors"
              >
                Approve
              </button>
              <button
                disabled={acting === detail.id}
                onClick={() => onDecide(detail.id, 'approved_metadata')}
                className="rounded border border-status/60 bg-status/10 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-status hover:bg-status/20 disabled:opacity-40 transition-colors"
              >
                {DECISION_LABELS.approved_metadata}
              </button>
              <div className="mt-1 flex gap-1.5">
                <button
                  disabled={acting === detail.id}
                  onClick={() => onSetReasonFor('needs_review')}
                  className="flex-1 rounded border border-command/40 bg-command/5 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-command hover:bg-command/10 disabled:opacity-40 transition-colors"
                >
                  Needs Review
                </button>
                <button
                  disabled={acting === detail.id}
                  onClick={() => onSetReasonFor('rejected')}
                  className="flex-1 rounded border border-wb-crit/40 bg-operations/5 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-wb-crit-on hover:bg-operations/10 disabled:opacity-40 transition-colors"
                >
                  Reject
                </button>
              </div>
            </div>
          )}

          {detail.review_history && detail.review_history.length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer text-[10px] uppercase tracking-[0.2em] text-wb-ink2">
                Review history ({detail.review_history.length})
              </summary>
              <ul className="mt-2 flex flex-col gap-1.5">
                {detail.review_history.map((h, i) => (
                  <li key={i} className="rounded border border-wb-line bg-wb-surface-2/60 p-2 text-[11px] text-wb-ink2">
                    {DECISION_LABELS[h.decision]} by {h.decided_by} — {new Date(h.at).toLocaleString()}
                    {h.reason ? ` — "${h.reason}"` : ''}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </Card>
  );
}
