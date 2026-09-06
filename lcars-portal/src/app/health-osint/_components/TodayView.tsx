'use client';

// Today — the default Health OSINT landing view (Phase 2 Three-Workbench
// Simplification mission). Answers "what's worth knowing", always shows a
// SAFETY read (clear or not), surfaces WATCH-equivalent items without a raw
// list, and folds the separate curation workbench in as a small
// high-value-only "Needs Your Review" card.

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Card, Badge } from '@/components/ui';
import { EVIDENCE_CONTRIBUTION_LABEL, IGNORE_REASONS, type EvidenceItem } from './shared';

interface NeedsReviewItem {
  signal_id: string;
  title: string;
  description: string | null;
  source_name: string | null;
  topic_label: string;
  collected_at: string;
  canonical_url: string | null;
  recommendation: 'UNCLEAR' | 'NEEDS_JUDGMENT';
  reason: string | null;
}

interface TodayPayload {
  worth_knowing: EvidenceItem[];
  worth_knowing_count: number;
  safety: { items: EvidenceItem[]; clear: boolean };
  emerging_count: number;
  needs_review: NeedsReviewItem[];
  needs_review_total_pending: number;
}

function ChangeCard({ item }: { item: EvidenceItem }) {
  const whatChanged = item.evidence_contribution
    ? EVIDENCE_CONTRIBUTION_LABEL[item.evidence_contribution] ?? item.evidence_contribution
    : 'New finding recorded';
  return (
    <div className="space-y-1.5 rounded-xl border border-wb-line bg-wb-surface p-3">
      <p className="text-[10.5px] font-semibold uppercase tracking-wide text-wb-ink2">{item.topic_label}</p>
      <p className="text-[13.5px] font-medium leading-snug text-wb-ink">{item.title}</p>
      <p className="text-[12px] text-wb-ink2">
        <span className="font-medium text-wb-sage-deep">{whatChanged}.</span>{' '}
        {item.summary || 'No summary available yet.'}
      </p>
      <p className="text-[11.5px] italic text-wb-ink2">
        You need to: {item.actionable_recommendation || 'Nothing — this is informational.'}
      </p>
      {item.source_url && (
        <a href={item.source_url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-wb-sage-deep underline decoration-dotted">
          {item.source_name}
        </a>
      )}
    </div>
  );
}

export function TodayView() {
  const [data, setData] = useState<TodayPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [reasonById, setReasonById] = useState<Record<string, string>>({});

  function load() {
    setLoading(true);
    fetch('/api/health-osint/today')
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw new Error(d?.error || 'Failed to load');
        setData(d);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  async function decide(signalId: string, action: 'publish' | 'reject') {
    setBusyId(signalId);
    try {
      const reason = action === 'reject' ? reasonById[signalId] : undefined;
      const res = await fetch(`/api/health-osint-curation/${signalId}/${action}`, {
        method: 'POST',
        ...(reason ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reason }) } : {}),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.error || `Failed to ${action}`);
      }
      setData((prev) => prev ? { ...prev, needs_review: prev.needs_review.filter((i) => i.signal_id !== signalId) } : prev);
    } catch (e) {
      setError(e instanceof Error ? e.message : `Failed to ${action}`);
    } finally {
      setBusyId(null);
    }
  }

  if (loading && !data) return <p className="text-sm text-wb-ink2">Loading…</p>;
  if (error && !data) return (
    <p className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">
      {error}. <Link href="/agent-status-workbench?tab=pipeline" className="underline">Check pipeline health →</Link>
    </p>
  );
  if (!data) return null;

  const worthCount = data.worth_knowing_count;

  return (
    <div className="space-y-6">
      {error && (
        <p className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">
          {error}. <Link href="/agent-status-workbench?tab=pipeline" className="underline">Check pipeline health →</Link>
        </p>
      )}

      <div>
        <p className="mb-2 text-[13px] font-semibold text-wb-ink">
          {worthCount === 0 ? 'Nothing new worth knowing right now.' : `${worthCount} thing${worthCount === 1 ? '' : 's'} worth knowing`}
        </p>
        {worthCount > 0 ? (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {data.worth_knowing.map((i) => (<ChangeCard key={i.signal_id} item={i} />))}
          </div>
        ) : (
          <p className="rounded-xl border border-wb-line bg-wb-surface p-4 text-[13px] text-wb-ink2">
            No high-value evidence changes in the last 14 days. Check My Evidence for the full current position on every topic.
          </p>
        )}
      </div>

      {/* SAFETY — always rendered, never conditionally omitted (mission
          spec: this must never regress into silence when there IS a
          safety-relevant item). */}
      <Card>
        <h2 className="mb-3 flex items-center gap-2 border-b border-wb-line pb-3 font-serif text-lg text-wb-ink">
          <span className={`inline-block h-2 w-2 rounded-full ${data.safety.clear ? 'bg-wb-ok' : 'bg-wb-crit'}`} aria-hidden />
          Safety
        </h2>
        {data.safety.clear ? (
          <p className="text-[13px] text-wb-ink2">✓ Nothing new requires attention.</p>
        ) : (
          <div className="space-y-2">
            {data.safety.items.map((s) => (
              <div key={s.signal_id} className="border-b border-wb-line pb-2 text-[12.5px] last:border-0">
                <div className="font-semibold text-wb-crit-on">{s.title}</div>
                <div className="text-wb-ink2">{s.summary}</div>
                {s.actionable_recommendation && <div className="italic text-wb-ink2">You need to: {s.actionable_recommendation}</div>}
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* EMERGING — count + link only, no raw list per spec. */}
      <div className="rounded-xl border border-wb-line bg-wb-surface p-3 text-[12.5px] text-wb-ink2">
        {data.emerging_count > 0 ? (
          <>
            {data.emerging_count} finding{data.emerging_count === 1 ? ' is' : 's are'} being watched. Evidence not yet strong enough to change what HQ thinks.{' '}
            <Link href="/health-osint?tab=my-evidence" className="text-wb-sage-deep hover:underline">View emerging →</Link>
          </>
        ) : (
          <>Nothing currently in the watch list.</>
        )}
      </div>

      {/* NEEDS YOUR REVIEW — curation folded in, ambiguous-only subset. */}
      {data.needs_review.length > 0 && (
        <Card title="Needs Your Review">
          <p className="mb-3 text-[11.5px] text-wb-ink2">
            The system is not confident these are relevant — everything else it already handled automatically.
          </p>
          <div className="space-y-3">
            {data.needs_review.map((item) => (
              <div key={item.signal_id} className="border-b border-wb-line pb-3 text-[12.5px] last:border-0">
                <div className="font-semibold text-wb-ink">
                  {item.canonical_url ? (
                    <a href={item.canonical_url} target="_blank" rel="noreferrer" className="hover:underline">{item.title}</a>
                  ) : item.title}
                </div>
                <div className="mt-0.5 text-wb-ink2">
                  {item.topic_label} · {item.source_name ?? 'Unknown source'}
                  {' · '}
                  <Badge status={item.recommendation === 'UNCLEAR' ? 'warning' : 'neutral'}>
                    Machine recommendation: {item.recommendation === 'UNCLEAR' ? 'Unclear' : 'Needs judgment'}
                  </Badge>
                </div>
                {item.reason && <p className="mt-1 italic text-wb-ink2">{item.reason}</p>}
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    disabled={busyId === item.signal_id}
                    onClick={() => decide(item.signal_id, 'publish')}
                    className="rounded bg-wb-sage-deep px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
                  >
                    Include
                  </button>
                  <button
                    type="button"
                    disabled={busyId === item.signal_id}
                    onClick={() => decide(item.signal_id, 'reject')}
                    className="rounded bg-wb-crit/10 px-3 py-1 text-xs font-medium text-wb-crit disabled:opacity-50"
                  >
                    Ignore
                  </button>
                  <select
                    value={reasonById[item.signal_id] ?? ''}
                    onChange={(e) => setReasonById((prev) => ({ ...prev, [item.signal_id]: e.target.value }))}
                    className="rounded border border-wb-line bg-transparent px-2 py-1 text-xs text-wb-ink2"
                    aria-label="Ignore reason (optional)"
                  >
                    <option value="">Ignore reason (optional)</option>
                    {IGNORE_REASONS.map((r) => (<option key={r.value} value={r.value}>{r.label}</option>))}
                  </select>
                </div>
              </div>
            ))}
          </div>
          {data.needs_review_total_pending > data.needs_review.length && (
            <p className="mt-3 text-[11px] text-wb-ink2">
              <Link href="/health-osint-curation" className="text-wb-sage-deep hover:underline">See the full queue →</Link>
            </p>
          )}
        </Card>
      )}
    </div>
  );
}
