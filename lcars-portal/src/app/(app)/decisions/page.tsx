'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { WorkbenchShell } from '@/components/ui';
import { ApprovalQueue } from '@/components/ApprovalQueue';
import {
  fetchDecisionsInbox,
  decideItem,
  type DecisionItem,
  type IntelligenceDecisionItem,
} from '@/lib/decisions';

// Built 2026-09-26 (HQ Consolidation Audit follow-up). This page's real
// function — one merged queue for decisions genuinely awaiting the
// Captain — was planned as /decide (STARSHIP-REDESIGN.md §5), then this
// page itself sat as a redirect stub for over a month while the real data
// layer (lib/decisions.ts, MSN-0345) shipped and was wired into
// MobileAlertDrawer only. This is the first desktop consumer.
//
// Deliberately lean, not a dashboard: approve/reject actions were removed
// from Captain's Chair itself on 2026-08-22 ("too detailed for that page")
// — this page is where that action now lives, one click away via Needs
// You (commandState.ts's engineering-approvals item), not folded back
// into Captain's Chair.
export default function DecisionsPage() {
  const [actionable, setActionable] = useState<DecisionItem[]>([]);
  const [intelligence, setIntelligence] = useState<IntelligenceDecisionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [actingId, setActingId] = useState<string | null>(null);
  const [flash, setFlash] = useState<{ id: string; message: string; ok: boolean } | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    fetchDecisionsInbox()
      .then((data) => {
        setActionable(data.actionable);
        setIntelligence(data.intelligence);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleDecision = async (id: string, decision: 'approve' | 'reject', reason?: string) => {
    const item = actionable.find((i) => i.id === id);
    if (!item) return;
    setActingId(id);
    setFlash(null);
    const result = await decideItem(item, decision, reason);
    setActingId(null);
    setFlash({
      id,
      ok: result.ok,
      message: result.ok
        ? `${decision === 'approve' ? 'Approved' : 'Rejected'}: ${item.title}`
        : `Failed to ${decision}: ${result.error ?? 'unknown error'}`,
    });
    if (result.ok) load();
  };

  return (
    <WorkbenchShell
      title="Decisions Inbox"
      eyebrow="Executive command surface"
      tagline="USS TJR · Decisions Inbox · Engineering approvals + flagged intelligence recommendations, one queue"
      back={{ href: '/captains-chair-workbench', label: "Captain's Chair" }}
      mode="command"
    >
      <div className="space-y-4">
        <ApprovalQueue
          title="Awaiting Your Decision"
          items={actionable}
          loading={loading}
          emptyMessage="No engineering handoffs awaiting approval."
          onApprove={(id) => handleDecision(id, 'approve')}
          onReject={(id, reason) => handleDecision(id, 'reject', reason)}
          onRefresh={load}
          actingId={actingId}
          flash={flash}
        />

        {/* Operational Intelligence recommendations flagged requires_approval.
            Real fetch, real filter (lib/decisions.ts) — legitimately empty
            today since no domain sets that field true yet. Read-only: no
            governed approve/reject route exists for an OI recommendation,
            and inventing one here would be new governance this page does
            not authorise (see lib/decisions.ts's own header). */}
        <div className="rounded-xl border border-wb-line bg-wb-surface p-3">
          <p className="mb-3 text-[10px] uppercase tracking-[0.25em] text-wb-sand-deep">
            Flagged Intelligence Recommendations
            {intelligence.length > 0 && <span className="ml-1 text-wb-ink2">({intelligence.length})</span>}
          </p>
          {loading ? (
            <p className="text-xs animate-pulse text-wb-ink2">Loading…</p>
          ) : intelligence.length === 0 ? (
            <p className="text-xs text-wb-ink2">
              None currently flagged. No domain sets <code className="font-mono">requires_approval</code> yet —
              this section activates automatically the moment one does.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {intelligence.map((item) => (
                <li key={item.id} className="rounded border border-wb-line bg-wb-bg p-3">
                  <Link href={item.briefHref} className="block text-xs font-medium leading-snug text-wb-ink underline underline-offset-2 hover:text-wb-sand-deep">
                    {item.description}
                  </Link>
                  <p className="mt-0.5 text-[10px] text-wb-ink2">
                    {item.sourceDomain}
                    {item.confidence != null && ` · ${Math.round(item.confidence * 100)}% confidence`}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </WorkbenchShell>
  );
}
