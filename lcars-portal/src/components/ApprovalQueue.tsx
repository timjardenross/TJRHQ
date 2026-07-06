'use client';

import { useState } from 'react';
import { stateToneClasses } from '@/lib/departments';

/**
 * Canonical Approval Queue contract (MSN-0315 Phase 1B). Presentational and
 * entity-agnostic — CaptainApprovalQueue.tsx is its only consumer today
 * (mission approvals over Supabase); a second consumer (e.g. build-request
 * or handoff approvals) can adopt this directly by mapping its own rows onto
 * `ApprovalQueueItem` and supplying `onApprove`/`onReject`, instead of
 * copy-pasting this file. No data-fetching or entity-specific logic lives
 * here — that stays owned by each consumer.
 */
export interface ApprovalQueueItem {
  id: string;
  /** Short monospace identifier shown above the title, e.g. a mission number. */
  code?: string;
  title: string;
  /** Secondary line, e.g. "status · priority · owner". */
  detail?: string;
  /** Defaults to true. Set false when this item's current state isn't eligible for approval (a second consumer's governed route would 409). */
  canApprove?: boolean;
  /** Defaults to true. Set false when this item's current state isn't eligible for rejection. */
  canReject?: boolean;
}

export interface ApprovalQueueFlash {
  id: string;
  message: string;
  ok: boolean;
}

export interface ApprovalQueueProps {
  title?: string;
  items: ApprovalQueueItem[];
  loading?: boolean;
  emptyMessage?: string;
  onApprove: (id: string) => void | Promise<void>;
  onReject: (id: string, reason: string) => void | Promise<void>;
  onRefresh?: () => void;
  /** Item id currently mid-decision — disables its buttons and shows a working label. */
  actingId?: string | null;
  flash?: ApprovalQueueFlash | null;
}

export function ApprovalQueue({
  title = "Captain's Queue",
  items,
  loading = false,
  emptyMessage = 'No missions awaiting approval.',
  onApprove,
  onReject,
  onRefresh,
  actingId = null,
  flash = null,
}: ApprovalQueueProps) {
  const [rejectReasonFor, setRejectReasonFor] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState('');

  if (loading) {
    return (
      <div className="rounded-lcars border border-edge bg-panel/60 p-3">
        <p className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted mb-3">{title}</p>
        <p className="text-xs text-lcars-muted animate-pulse">Loading…</p>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="rounded-lcars border border-edge bg-panel/60 p-3">
        <p className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted mb-3">{title}</p>
        <p className="text-xs text-lcars-muted">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className="rounded-lcars border border-command/40 bg-command/5 p-3">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-[10px] uppercase tracking-[0.25em] text-command">
          {title} — {items.length} awaiting decision
        </p>
        {onRefresh && (
          <button
            onClick={onRefresh}
            className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted hover:text-command transition-colors"
          >
            Refresh
          </button>
        )}
      </div>

      {flash && (
        <div
          className={`mb-3 rounded border px-3 py-2 text-xs ${flash.ok ? `${stateToneClasses('ok').border} ${stateToneClasses('ok').bg} ${stateToneClasses('ok').text}` : `${stateToneClasses('crit').border} ${stateToneClasses('crit').bg} ${stateToneClasses('crit').text}`}`}
        >
          {flash.message}
        </div>
      )}

      <ul className="flex flex-col gap-2">
        {items.map((item) => (
          <li key={item.id} className="rounded border border-edge bg-panel-2/60 p-3">
            <div className="flex items-start justify-between gap-2 mb-2">
              <div>
                {item.code && <span className="font-mono text-[10px] text-lcars-muted">{item.code}</span>}
                <p className="text-xs font-medium text-lcars-text leading-snug mt-0.5">{item.title}</p>
                {item.detail && <p className="text-[10px] text-lcars-muted mt-0.5">{item.detail}</p>}
              </div>
            </div>

            {rejectReasonFor === item.id ? (
              <div className="mt-2 flex flex-col gap-2">
                <input
                  type="text"
                  placeholder="Rejection reason (required)"
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  className="w-full rounded border border-edge bg-panel px-2 py-1.5 text-xs text-lcars-text placeholder:text-lcars-muted focus:border-state-crit/60 focus:outline-none"
                />
                <div className="flex gap-2">
                  <button
                    disabled={!rejectReason.trim() || actingId === item.id}
                    onClick={() => {
                      const reason = rejectReason.trim();
                      setRejectReasonFor(null);
                      setRejectReason('');
                      onReject(item.id, reason);
                    }}
                    className={`flex-1 rounded border ${stateToneClasses('crit').border} ${stateToneClasses('crit').bg} px-3 py-2.5 min-h-[44px] text-[10px] uppercase tracking-[0.15em] ${stateToneClasses('crit').text} hover:bg-state-crit/20 disabled:opacity-40 transition-colors`}
                  >
                    {actingId === item.id ? 'Rejecting…' : 'Confirm Reject'}
                  </button>
                  <button
                    onClick={() => {
                      setRejectReasonFor(null);
                      setRejectReason('');
                    }}
                    className="rounded border border-edge px-3 py-2.5 min-h-[44px] text-[10px] uppercase tracking-[0.15em] text-lcars-muted hover:text-lcars-text transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex gap-2 mt-2">
                {item.canApprove !== false && (
                  <button
                    disabled={actingId === item.id}
                    onClick={() => onApprove(item.id)}
                    className={`flex-1 rounded border ${stateToneClasses('ok').border} ${stateToneClasses('ok').bg} px-3 py-2.5 min-h-[44px] text-[10px] uppercase tracking-[0.15em] ${stateToneClasses('ok').text} hover:bg-state-ok/20 disabled:opacity-40 transition-colors`}
                  >
                    {actingId === item.id ? 'Working…' : 'Approve'}
                  </button>
                )}
                {item.canReject !== false && (
                  <button
                    disabled={actingId === item.id}
                    onClick={() => setRejectReasonFor(item.id)}
                    className={`flex-1 rounded border ${stateToneClasses('crit').border} ${stateToneClasses('crit').bg} px-3 py-2.5 min-h-[44px] text-[10px] uppercase tracking-[0.15em] ${stateToneClasses('crit').text} hover:bg-state-crit/10 disabled:opacity-40 transition-colors`}
                  >
                    Reject
                  </button>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
