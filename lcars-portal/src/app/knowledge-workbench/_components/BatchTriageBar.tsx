'use client';

import { Card } from '@/components/ui/Card';
import { DECISION_LABELS, REVIEW_STATUS_LABELS } from './badges';
import type { ReviewDecision } from '@/lib/types';

interface BatchTriageBarProps {
  checkedIds: Set<string>;
  batchActing: boolean;
  batchReasonFor: ReviewDecision | null;
  batchReasonDraft: string;
  setBatchReasonFor: (decision: ReviewDecision | null) => void;
  setBatchReasonDraft: (reason: string) => void;
  batchDecide: (decision: ReviewDecision, reason?: string) => void;
  setCheckedIds: (ids: Set<string>) => void;
  flash?: { msg: string; ok: boolean } | null;
}

export function BatchTriageBar({
  checkedIds,
  batchActing,
  batchReasonFor,
  batchReasonDraft,
  setBatchReasonFor,
  setBatchReasonDraft,
  batchDecide,
  setCheckedIds,
  flash,
}: BatchTriageBarProps) {
  if (checkedIds.size === 0) return null;

  return (
    <Card className="lg:w-[340px] p-4">
      <h3 className="mb-3 font-serif text-[14px] uppercase tracking-wide text-wb-ink">
        Batch Decide ({checkedIds.size} selected)
      </h3>
      {flash && (
        <div className={`mb-2 rounded border px-3 py-2 text-xs ${flash.ok ? 'border-wb-ok/40 bg-wb-ok/10 text-wb-ok-on' : 'border-wb-crit/40 bg-wb-crit/10 text-wb-crit-on'}`}>
          {flash.msg}
        </div>
      )}
      {batchReasonFor ? (
        <div className="flex flex-col gap-2">
          <input
            type="text"
            placeholder={`Reason for ${DECISION_LABELS[batchReasonFor].toLowerCase()} (required)`}
            value={batchReasonDraft}
            onChange={(e) => setBatchReasonDraft(e.target.value)}
            className="w-full rounded border border-wb-line bg-wb-surface px-2 py-1.5 text-xs text-wb-ink placeholder:text-wb-ink2 focus:border-wb-crit/60 focus:outline-none"
          />
          <div className="flex gap-2">
            <button
              disabled={!batchReasonDraft.trim() || batchActing}
              onClick={() => batchDecide(batchReasonFor, batchReasonDraft.trim())}
              className="flex-1 rounded border border-wb-crit/60 bg-wb-crit/10 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-wb-crit-on hover:bg-wb-crit/20 disabled:opacity-40 transition-colors"
            >
              {batchActing ? 'Working…' : `Confirm ${DECISION_LABELS[batchReasonFor]}`}
            </button>
            <button
              onClick={() => {
                setBatchReasonFor(null);
                setBatchReasonDraft('');
              }}
              className="rounded border border-wb-line px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-wb-ink2 hover:text-wb-ink transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-1.5">
          <p className="mb-1 text-[11px] text-wb-ink2">
            Applies one decision to all {checkedIds.size} selected documents. Each is still checked individually server-side (idempotent, terminal-status guarded) — only genuinely eligible ones are decided.
          </p>
          <button
            disabled={batchActing}
            onClick={() => batchDecide('approved_chunks')}
            className="rounded border border-wb-ok/60 bg-wb-ok/10 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-wb-ok-on hover:bg-wb-ok/20 disabled:opacity-40 transition-colors"
          >
            {batchActing ? 'Working…' : 'Approve'}
          </button>
          <button
            disabled={batchActing}
            onClick={() => batchDecide('approved_metadata')}
            className="rounded border border-wb-ok/60 bg-wb-ok/10 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-wb-ok-on hover:bg-wb-ok/20 disabled:opacity-40 transition-colors"
          >
            {DECISION_LABELS.approved_metadata}
          </button>
          <div className="mt-1 flex gap-1.5">
            <button
              disabled={batchActing}
              onClick={() => setBatchReasonFor('needs_review')}
              className="flex-1 rounded border border-wb-warn/40 bg-wb-warn/5 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-wb-warn-on hover:bg-wb-warn/10 disabled:opacity-40 transition-colors"
            >
              Needs Review
            </button>
            <button
              disabled={batchActing}
              onClick={() => setBatchReasonFor('rejected')}
              className="flex-1 rounded border border-wb-crit/40 bg-wb-crit/5 px-3 py-1.5 text-[10px] uppercase tracking-[0.15em] text-wb-crit-on hover:bg-wb-crit/10 disabled:opacity-40 transition-colors"
            >
              Reject
            </button>
          </div>
          <button
            onClick={() => setCheckedIds(new Set())}
            className="mt-2 text-[10px] uppercase tracking-[0.2em] text-wb-ink2 hover:text-wb-ink transition-colors"
          >
            Clear selection
          </button>
        </div>
      )}
    </Card>
  );
}
