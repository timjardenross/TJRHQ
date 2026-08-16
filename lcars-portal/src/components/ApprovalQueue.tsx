'use client';

import Link from 'next/link';
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
  /** MSN-0334: optional link to this item's own detail page. Previously
      approving/rejecting here left no path back to the record itself —
      the Captain had to manually navigate and re-find it. Undefined
      (no link) is a safe default for any consumer whose entity has no
      detail page. */
  href?: string;
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
  /** Chrome skin — 'legacy' (default) for (app)/* pages, 'wb' for *-workbench
   *  routes. This component's logic (approve/reject, reason capture, flash)
   *  is genuinely shared, not LCARS-specific — unlike LCARSPanel/StatusBadge
   *  it was never named after the legacy system, so a theme prop here isn't
   *  the coupling the WorkbenchPanel/WorkbenchBadge split was fixing. */
  theme?: 'legacy' | 'wb';
}

const CHROME = {
  legacy: {
    box: 'rounded-lcars border border-edge bg-panel/60 p-3',
    boxLabel: 'text-lcars-muted',
    boxBody: 'text-lcars-muted',
    container: 'rounded-lcars border border-command/40 bg-command/5 p-3',
    headerLabel: 'text-command',
    refresh: 'text-lcars-muted hover:text-command',
    item: 'rounded border border-edge bg-panel-2/60 p-3',
    itemMeta: 'text-lcars-muted',
    itemTitle: 'text-lcars-text',
    input: 'border-edge bg-panel text-lcars-text placeholder:text-lcars-muted',
    cancel: 'border-edge text-lcars-muted hover:text-lcars-text',
  },
  wb: {
    box: 'rounded-lg border border-wb-border bg-wb-bg/60 p-3',
    boxLabel: 'text-wb-ink2',
    boxBody: 'text-wb-ink2',
    container: 'rounded-lg border border-wb-sage-deep/40 bg-wb-sage-deep/5 p-3',
    headerLabel: 'text-wb-sage-deep',
    refresh: 'text-wb-ink2 hover:text-wb-sage-deep',
    item: 'rounded border border-wb-border bg-wb-bg/60 p-3',
    itemMeta: 'text-wb-ink2',
    itemTitle: 'text-wb-ink',
    input: 'border-wb-border bg-white text-wb-ink placeholder:text-wb-ink2',
    cancel: 'border-wb-border text-wb-ink2 hover:text-wb-ink',
  },
} as const;

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
  theme = 'legacy',
}: ApprovalQueueProps) {
  const [rejectReasonFor, setRejectReasonFor] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const t = CHROME[theme];

  if (loading) {
    return (
      <div className={t.box}>
        <p className={`text-[10px] uppercase tracking-[0.25em] mb-3 ${t.boxLabel}`}>{title}</p>
        <p className={`text-xs animate-pulse ${t.boxBody}`}>Loading…</p>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className={t.box}>
        <p className={`text-[10px] uppercase tracking-[0.25em] mb-3 ${t.boxLabel}`}>{title}</p>
        <p className={`text-xs ${t.boxBody}`}>{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className={t.container}>
      <div className="mb-3 flex items-center justify-between">
        <p className={`text-[10px] uppercase tracking-[0.25em] ${t.headerLabel}`}>
          {title} — {items.length} awaiting decision
        </p>
        {onRefresh && (
          <button
            onClick={onRefresh}
            className={`text-[10px] uppercase tracking-[0.2em] transition-colors ${t.refresh}`}
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
          <li key={item.id} className={t.item}>
            <div className="flex items-start justify-between gap-2 mb-2">
              <div>
                {item.code && <span className={`font-mono text-[10px] ${t.itemMeta}`}>{item.code}</span>}
                {item.href ? (
                  <Link href={item.href} className={`block text-xs font-medium leading-snug mt-0.5 underline underline-offset-2 hover:text-status-on ${t.itemTitle}`}>
                    {item.title}
                  </Link>
                ) : (
                  <p className={`text-xs font-medium leading-snug mt-0.5 ${t.itemTitle}`}>{item.title}</p>
                )}
                {item.detail && <p className={`text-[10px] mt-0.5 ${t.itemMeta}`}>{item.detail}</p>}
              </div>
            </div>

            {rejectReasonFor === item.id ? (
              <div className="mt-2 flex flex-col gap-2">
                <input
                  type="text"
                  placeholder="Rejection reason (required)"
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  className={`w-full min-h-[44px] rounded border px-2 py-1.5 text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-state-crit focus-visible:outline-offset-1 ${t.input}`}
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
                    className={`rounded border px-3 py-2.5 min-h-[44px] text-[10px] uppercase tracking-[0.15em] transition-colors ${t.cancel}`}
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
