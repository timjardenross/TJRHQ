'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Button, Input, Card } from '@/components/ui';
import type { ApprovalQueueItem, ApprovalQueueFlash } from '@/components/ApprovalQueue';

/**
 * Mission Workbench fork of components/ApprovalQueue.tsx — same prop
 * contract (imports its two exported types rather than redefining them, so
 * a drift in the shape is a compile error, not a silent mismatch), wb-*
 * look. Forked rather than restyled-in-place because the original is also
 * used by CaptainApprovalQueue.tsx on Captain's Chair, which stays on the
 * LCARS chrome and must not change.
 */
export interface ApprovalQueueProps {
  title?: string;
  items: ApprovalQueueItem[];
  loading?: boolean;
  emptyMessage?: string;
  onApprove: (id: string) => void | Promise<void>;
  onReject: (id: string, reason: string) => void | Promise<void>;
  onRefresh?: () => void;
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
      <Card title={title}>
        <p className="animate-pulse text-[12px] text-wb-ink2">Loading…</p>
      </Card>
    );
  }

  if (items.length === 0) {
    return (
      <Card title={title}>
        <p className="text-[12px] text-wb-ink2">{emptyMessage}</p>
      </Card>
    );
  }

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <p className="text-[11px] uppercase tracking-[0.2em] text-wb-sage-deep">
          {title} — {items.length} awaiting decision
        </p>
        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            className="text-[10px] uppercase tracking-[0.15em] text-wb-ink2 transition-colors hover:text-wb-sage-deep"
          >
            Refresh
          </button>
        )}
      </div>

      {flash && (
        <div className={`mb-3 rounded-md border px-3 py-2 text-[12px] ${
          flash.ok ? 'border-wb-ok/40 bg-wb-ok/10 text-wb-ok-on' : 'border-wb-crit/40 bg-wb-crit/10 text-wb-crit-on'
        }`}>
          {flash.message}
        </div>
      )}

      <ul className="flex flex-col gap-2">
        {items.map(item => (
          <li key={item.id} className="rounded-md border border-wb-line bg-wb-bg p-3">
            <div className="mb-2 flex items-start justify-between gap-2">
              <div>
                {item.code && <span className="font-mono text-[10px] text-wb-ink2">{item.code}</span>}
                {item.href ? (
                  <Link href={item.href} className="mt-0.5 block text-[12px] font-medium leading-snug text-wb-ink underline underline-offset-2 hover:text-wb-sage-deep">
                    {item.title}
                  </Link>
                ) : (
                  <p className="mt-0.5 text-[12px] font-medium leading-snug text-wb-ink">{item.title}</p>
                )}
                {item.detail && <p className="mt-0.5 text-[10px] text-wb-ink2">{item.detail}</p>}
              </div>
            </div>

            {rejectReasonFor === item.id ? (
              <div className="mt-2 flex flex-col gap-2">
                <Input
                  type="text"
                  placeholder="Rejection reason (required)"
                  value={rejectReason}
                  onChange={e => setRejectReason(e.target.value)}
                />
                <div className="flex gap-2">
                  <Button
                    variant="danger"
                    size="sm"
                    disabled={!rejectReason.trim() || actingId === item.id}
                    onClick={() => {
                      const reason = rejectReason.trim();
                      setRejectReasonFor(null);
                      setRejectReason('');
                      onReject(item.id, reason);
                    }}
                    className="flex-1"
                  >
                    {actingId === item.id ? 'Rejecting…' : 'Confirm Reject'}
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => { setRejectReasonFor(null); setRejectReason(''); }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <div className="mt-2 flex gap-2">
                {item.canApprove !== false && (
                  <Button size="sm" disabled={actingId === item.id} onClick={() => onApprove(item.id)} className="flex-1">
                    {actingId === item.id ? 'Working…' : 'Approve'}
                  </Button>
                )}
                {item.canReject !== false && (
                  <Button
                    variant="danger"
                    size="sm"
                    disabled={actingId === item.id}
                    onClick={() => setRejectReasonFor(item.id)}
                    className="flex-1"
                  >
                    Reject
                  </Button>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

export type { ApprovalQueueItem, ApprovalQueueFlash };
