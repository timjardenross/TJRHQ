'use client';

// STARSHIP-REDESIGN.md §5: Decide. One item at a time, full-width, plain
// question, plain reasoning, domain tag, evidence if available. No table,
// no ranked list, no Priority Engine claim, no fake recommendation.
// Reached only from Home's "Needs you" line - not part of the legacy
// sidebar nav (see src/lib/nav.ts's own note on why "Decisions" was never
// added there). One way back: Home.

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  fetchDecideQueue,
  approveDecideItem,
  holdDecideItem,
  undoDecideItem,
  fetchDecideHistory,
  updateDecideOutcome,
  DECIDE_EMPTY_TITLE,
  DECIDE_EMPTY_DETAIL,
  type DecideItem,
  type DecideHistoryEntry,
} from '@/lib/decide';

interface PostAction {
  item: DecideItem;
  kind: 'approve' | 'hold';
  ok: boolean;
  error?: string;
  undone?: boolean;
  /** EOS Phase 3 Priority 2: the decide_ledger row this action just wrote -
   * lets the Captain launch a Decision Brief with automatic context
   * (Communications Studio, lib/commsStudio.ts's assembleDecisionBrief())
   * instead of hunting down and pasting the id by hand. */
  ledgerId?: string | null;
}

export default function DecidePage() {
  const [items, setItems] = useState<DecideItem[] | null>(null);
  const [decidedIds, setDecidedIds] = useState<Set<string>>(new Set());
  const [heldIds, setHeldIds] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [post, setPost] = useState<PostAction | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState<DecideHistoryEntry[] | null>(null);

  const load = useCallback(async () => {
    const q = await fetchDecideQueue();
    setItems(q);
    setDecidedIds(new Set());
    setHeldIds(new Set());
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const current = useMemo(() => {
    if (!items) return null;
    return items.find((i) => !decidedIds.has(i.id) && !heldIds.has(i.id)) ?? null;
  }, [items, decidedIds, heldIds]);

  const remainingCount = useMemo(() => {
    if (!items) return 0;
    return items.filter((i) => !decidedIds.has(i.id) && !heldIds.has(i.id)).length;
  }, [items, decidedIds, heldIds]);

  const handleApprove = useCallback(async (item: DecideItem) => {
    setBusy(true);
    const res = await approveDecideItem(item);
    setDecidedIds((prev) => new Set(prev).add(item.id));
    setPost({ item, kind: 'approve', ok: res.ok, error: res.error, ledgerId: res.ledgerId });
    setBusy(false);
  }, []);

  const handleHold = useCallback(async (item: DecideItem) => {
    setBusy(true);
    const res = await holdDecideItem(item);
    setHeldIds((prev) => new Set(prev).add(item.id));
    setPost({ item, kind: 'hold', ok: true, ledgerId: res.ledgerId });
    setBusy(false);
  }, []);

  const toggleHistory = useCallback(async () => {
    const opening = !historyOpen;
    setHistoryOpen(opening);
    if (opening && history === null) {
      setHistory(await fetchDecideHistory());
    }
  }, [historyOpen, history]);

  const handleSaveOutcome = useCallback(async (entryId: string, outcome: string) => {
    const res = await updateDecideOutcome(entryId, outcome);
    if (res.ok) {
      setHistory((prev) => prev && prev.map((e) => (e.id === entryId ? { ...e, outcome } : e)));
    }
    return res;
  }, []);

  const handleUndo = useCallback(async (item: DecideItem) => {
    setBusy(true);
    const res = await undoDecideItem(item);
    if (res.ok) {
      setDecidedIds((prev) => {
        const next = new Set(prev);
        next.delete(item.id);
        return next;
      });
    }
    setPost((prev) => (prev && prev.item.id === item.id ? { ...prev, undone: res.ok } : prev));
    setBusy(false);
  }, []);

  return (
    <main className="min-h-screen flex justify-center bg-[#0B1017] text-[#E8EDF2]">
      <div className="w-full max-w-[620px] px-7 pt-10 pb-14 flex flex-col min-h-screen">
        <Link
          href="/home"
          className="text-sm text-[#5A6875] hover:text-[#93A1B0] mb-8 inline-flex items-center gap-1.5 w-fit"
        >
          ← Home
        </Link>

        {items === null ? (
          <p className="text-[#5A6875] text-[15.5px]">Checking for anything that needs you…</p>
        ) : current === null ? (
          <div>
            <h1
              className="text-[28px] mb-3"
              style={{
                // Same fix as HomeScreen.tsx: the app's globals.css forces
                // all h1/h2/h3 to uppercase sans-serif (@layer base) -
                // pinned inline rather than fought via the utility cascade.
                fontFamily: '"New York", "SF Pro Display", Georgia, serif',
                fontWeight: 500,
                textTransform: 'none',
              }}
            >
              {DECIDE_EMPTY_TITLE}
            </h1>
            <p className="text-[#93A1B0] text-[15.5px] leading-relaxed">
              {DECIDE_EMPTY_DETAIL}
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-6">
            {post && (
              <PostActionBanner post={post} onUndo={handleUndo} busy={busy} />
            )}

            <div>
              <span className="inline-block text-[11px] uppercase tracking-[0.14em] text-[#5A6875] border border-[rgba(147,161,176,0.25)] rounded-full px-2.5 py-1 mb-4">
                {current.domainTag}
              </span>
              <h1
                className="text-[26px] sm:text-[32px] leading-[1.25] mb-4"
                style={{
                // Same fix as HomeScreen.tsx: the app's globals.css forces
                // all h1/h2/h3 to uppercase sans-serif (@layer base) -
                // pinned inline rather than fought via the utility cascade.
                fontFamily: '"New York", "SF Pro Display", Georgia, serif',
                fontWeight: 500,
                textTransform: 'none',
              }}
              >
                {current.question}
              </h1>
              <p className="text-[16px] text-[#93A1B0] leading-relaxed mb-2">{current.reasoning}</p>
              {current.evidenceHref && (
                <a
                  href={current.evidenceHref}
                  target={current.evidenceHref.startsWith('http') ? '_blank' : undefined}
                  rel={current.evidenceHref.startsWith('http') ? 'noreferrer' : undefined}
                  className="text-[13px] text-[#6FB3C9] underline underline-offset-2 hover:text-[#93A1B0]"
                >
                  View evidence →
                </a>
              )}
            </div>

            <div className="flex flex-wrap gap-3 pt-2">
              <button
                disabled={busy}
                onClick={() => handleApprove(current)}
                className="px-6 py-3 rounded-md bg-[#58C0A8] text-[#0B1017] text-[15px] font-medium disabled:opacity-50"
              >
                Approve
              </button>
              <button
                disabled={busy}
                onClick={() => handleHold(current)}
                className="px-6 py-3 rounded-md border border-[rgba(147,161,176,0.3)] text-[#E8EDF2] text-[15px] font-medium disabled:opacity-50"
              >
                Hold
              </button>
            </div>

            <p className="text-[12.5px] text-[#5A6875] pt-2">
              {remainingCount} of {items.length} awaiting your judgement
            </p>
          </div>
        )}

        <div className="mt-10 pt-6 border-t border-[rgba(147,161,176,0.15)]">
          <button
            onClick={toggleHistory}
            className="text-[13px] text-[#5A6875] hover:text-[#93A1B0]"
          >
            {historyOpen ? '▾' : '▸'} Past decisions
          </button>
          {historyOpen && (
            <HistorySection history={history} onSaveOutcome={handleSaveOutcome} />
          )}
        </div>
      </div>
    </main>
  );
}

/** Retrospective outcome capture. Read-only list of past decide_ledger rows
 * with an inline field to record what actually happened - the only writer
 * for decide_ledger.outcome anywhere in the app (see lib/decide.ts). Judgment
 * about whether a decision was right is never inferred automatically; it's
 * always a Captain typing it in, same principle as tools/rate_decision.py's
 * manual retrospective rating of the older decisions table. */
function HistorySection({
  history,
  onSaveOutcome,
}: {
  history: DecideHistoryEntry[] | null;
  onSaveOutcome: (entryId: string, outcome: string) => Promise<{ ok: boolean; error?: string }>;
}) {
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [savingId, setSavingId] = useState<string | null>(null);
  const [errorId, setErrorId] = useState<string | null>(null);

  if (history === null) {
    return <p className="text-[13px] text-[#5A6875] mt-3">Loading…</p>;
  }
  if (history.length === 0) {
    return <p className="text-[13px] text-[#5A6875] mt-3">No past decisions yet.</p>;
  }

  const save = async (entryId: string) => {
    const draft = (drafts[entryId] ?? '').trim();
    if (!draft) return;
    setSavingId(entryId);
    setErrorId(null);
    const res = await onSaveOutcome(entryId, draft);
    setSavingId(null);
    if (!res.ok) setErrorId(entryId);
  };

  return (
    <ul className="mt-4 flex flex-col gap-4">
      {history.map((entry) => (
        <li key={entry.id} className="text-[13.5px] text-[#93A1B0]">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-[#E8EDF2]">{entry.question}</span>
            <span className="text-[11px] text-[#5A6875] whitespace-nowrap">
              {entry.action} · {new Date(entry.decided_at).toLocaleDateString()}
            </span>
          </div>
          {entry.outcome ? (
            <p className="mt-1 text-[13px] text-[#6FB3C9]">Outcome: {entry.outcome}</p>
          ) : (
            <div className="mt-1.5 flex gap-2 items-start">
              <input
                type="text"
                placeholder="What actually happened?"
                value={drafts[entry.id] ?? ''}
                onChange={(e) => setDrafts((prev) => ({ ...prev, [entry.id]: e.target.value }))}
                className="flex-1 bg-transparent border border-[rgba(147,161,176,0.25)] rounded px-2.5 py-1.5 text-[13px] text-[#E8EDF2] placeholder:text-[#5A6875] focus:outline-none focus:border-[#6FB3C9]/50"
              />
              <button
                disabled={savingId === entry.id || !(drafts[entry.id] ?? '').trim()}
                onClick={() => save(entry.id)}
                className="text-[12.5px] text-[#6FB3C9] disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Save
              </button>
            </div>
          )}
          {errorId === entry.id && (
            <p className="mt-1 text-[12px] text-[#D8A65A]">Couldn&rsquo;t save outcome — try again.</p>
          )}
        </li>
      ))}
    </ul>
  );
}

function PostActionBanner({
  post,
  onUndo,
  busy,
}: {
  post: PostAction;
  onUndo: (item: DecideItem) => void;
  busy: boolean;
}) {
  if (!post.ok) {
    return (
      <div className="rounded-md border border-[#D8A65A]/40 bg-[#D8A65A]/10 px-4 py-3 text-[14px] text-[#E8EDF2]">
        Couldn&rsquo;t {post.kind === 'approve' ? 'approve' : 'hold'} &ldquo;{post.item.question}&rdquo;
        {post.error ? ` — ${post.error}` : ''}.
      </div>
    );
  }

  if (post.kind === 'hold') {
    return (
      <div className="rounded-md border border-[rgba(147,161,176,0.2)] bg-[#101722] px-4 py-3 text-[14px] text-[#93A1B0] flex items-center justify-between gap-3 flex-wrap">
        <span>Held. &ldquo;{post.item.question}&rdquo; will come back later — nothing changed.</span>
        <DecisionBriefLink ledgerId={post.ledgerId} />
      </div>
    );
  }

  if (post.undone) {
    return (
      <div className="rounded-md border border-[rgba(147,161,176,0.2)] bg-[#101722] px-4 py-3 text-[14px] text-[#93A1B0]">
        Undone. &ldquo;{post.item.question}&rdquo; is back in the queue.
      </div>
    );
  }

  return (
    <div className="rounded-md border border-[#58C0A8]/30 bg-[#58C0A8]/10 px-4 py-3 flex items-center justify-between gap-3 flex-wrap">
      <span className="text-[14px] text-[#E8EDF2]">Approved &ldquo;{post.item.question}&rdquo;.</span>
      <div className="flex items-center gap-3">
        <DecisionBriefLink ledgerId={post.ledgerId} />
        {post.item.undoAvailable ? (
          <button
            disabled={busy}
            onClick={() => onUndo(post.item)}
            className="text-[13px] text-[#6FB3C9] underline underline-offset-2 hover:text-[#93A1B0] disabled:opacity-50"
          >
            Undo
          </button>
        ) : (
          <span className="text-[12.5px] text-[#5A6875]">This decision can&rsquo;t be undone.</span>
        )}
      </div>
    </div>
  );
}

/** EOS Phase 3 Priority 2: automatic context, no manual ID entry - the
 * decide_ledger row this action just wrote is the exact refId Communications
 * Studio's Decision Brief assembler (lib/commsStudio.ts) needs. Renders
 * nothing if the ledger write itself failed (writeLedger degrades to null
 * rather than throwing - see lib/decide.ts) so this never links to a
 * document that can't actually be assembled. */
function DecisionBriefLink({ ledgerId }: { ledgerId?: string | null }) {
  if (!ledgerId) return null;
  return (
    <Link
      href={`/comms-studio?type=decision_brief&refId=${encodeURIComponent(ledgerId)}`}
      className="text-[13px] text-[#6FB3C9] underline underline-offset-2 hover:text-[#93A1B0]"
    >
      Draft a Decision Brief →
    </Link>
  );
}
