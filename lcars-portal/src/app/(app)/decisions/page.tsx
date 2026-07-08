'use client';

// MSN-0345: Captain Decisions Inbox — one place for judgement, merging
// mission approvals, engineering approvals, and (once real) Operational
// Intelligence recommendations flagged requires_approval. Reuses each
// source's existing governed write path — see lib/decisions.ts's own header
// for exactly what is and isn't real here.

import { useCallback, useEffect, useState } from 'react';
import { LCARSPanel } from '@/components/LCARSPanel';
import { ApprovalQueue, type ApprovalQueueFlash } from '@/components/ApprovalQueue';
import { ConfidenceIndicator } from '@/components/ConfidenceIndicator';
import {
  fetchDecisionsInbox,
  decideItem,
  type DecisionItem,
  type DecisionsInboxData,
} from '@/lib/decisions';

const SOURCE_LABEL: Record<DecisionItem['source'], string> = {
  mission: 'Mission',
  engineering: 'Engineering',
  intelligence: 'Intelligence',
};

export default function DecisionsPage() {
  const [data, setData] = useState<DecisionsInboxData | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<string | null>(null);
  const [flash, setFlash] = useState<ApprovalQueueFlash | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const d = await fetchDecisionsInbox();
    setData(d);
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const decide = useCallback(
    async (item: DecisionItem, decision: 'approve' | 'reject', reason?: string) => {
      setActing(item.id);
      const res = await decideItem(item, decision, reason);
      setFlash({
        id: item.id,
        message: res.ok ? (decision === 'approve' ? 'Approved' : 'Rejected') : (res.error ?? 'Failed'),
        ok: res.ok,
      });
      setActing(null);
      if (res.ok) {
        setData((prev) =>
          prev ? { ...prev, actionable: prev.actionable.filter((i) => i.id !== item.id) } : prev,
        );
      }
      setTimeout(() => setFlash(null), 4000);
    },
    [],
  );

  const items = data?.actionable ?? [];

  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel
        title="Decisions"
        accent="command"
        eyebrow="Captain Decisions Inbox · MSN-0345"
      >
        <p className="text-sm text-lcars-text/80 leading-relaxed">
          One place for judgement — mission and engineering approvals merged into a single,
          priority-ordered list. Highest-priority item first, regardless of which system it came
          from.
        </p>
        {!loading && (
          <p className="mt-2 text-[11px] uppercase tracking-wide text-lcars-muted">
            {data?.counts.mission ?? 0} mission · {data?.counts.engineering ?? 0} engineering ·{' '}
            {data?.counts.intelligence ?? 0} intelligence awaiting decision
          </p>
        )}
      </LCARSPanel>

      <LCARSPanel title="Awaiting Your Decision" accent="command">
        <ApprovalQueue
          title="Decisions Inbox"
          items={items.map((i) => ({
            ...i,
            detail: `${SOURCE_LABEL[i.source]}${i.detail ? ` · ${i.detail}` : ''}`,
          }))}
          loading={loading}
          actingId={acting}
          flash={flash}
          onRefresh={load}
          emptyMessage="Nothing awaiting a decision — mission and engineering queues are both clear."
          onApprove={(id) => {
            const item = items.find((i) => i.id === id);
            if (item) decide(item, 'approve');
          }}
          onReject={(id, reason) => {
            const item = items.find((i) => i.id === id);
            if (item) decide(item, 'reject', reason);
          }}
        />
      </LCARSPanel>

      {/* Real, currently-expected-empty per lib/decisions.ts's own header — no
          domain sets requires_approval on an OI recommendation yet. Rendered
          honestly rather than hidden, so the section is visibly live and
          ready the moment that changes, not a silent gap. */}
      <LCARSPanel title="Intelligence Recommendations Needing Judgement" accent="science">
        {loading ? (
          <p className="text-xs text-lcars-muted animate-pulse">Loading…</p>
        ) : (data?.intelligence.length ?? 0) === 0 ? (
          <p className="text-xs text-lcars-muted">
            None right now. No Operational Intelligence domain currently flags a recommendation as
            requiring explicit Captain approval — this section activates automatically the moment
            one does.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {data!.intelligence.map((i) => (
              <li key={i.id} className="rounded border border-edge bg-panel-2/60 p-3">
                <p className="text-xs font-medium text-lcars-text leading-snug">{i.description}</p>
                <div className="mt-1.5 flex items-center justify-between gap-2">
                  <span className="text-[10px] uppercase tracking-wide text-lcars-muted">
                    {i.sourceDomain}
                  </span>
                  <ConfidenceIndicator score={i.confidence} compact />
                </div>
                <a
                  href={i.briefHref}
                  className="mt-1.5 inline-block text-[10px] uppercase tracking-wide text-command underline underline-offset-2 hover:text-status-on"
                >
                  View in Captain&apos;s Brief →
                </a>
              </li>
            ))}
          </ul>
        )}
      </LCARSPanel>
    </div>
  );
}
