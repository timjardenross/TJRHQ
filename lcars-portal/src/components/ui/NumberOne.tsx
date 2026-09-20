'use client';

// Ambient Number One (Mission 7 §9/§40) — the connective tissue the Captain
// reaches for from anywhere, not another workbench destination.
//
// The backend for this already existed and was fully idle: Mission 6B built
// a deterministic canonical-intent dispatcher (lib/number-one/intent-router.ts
// — remember / what matters / what am I forgetting / stuck / still can't
// start / too much / not now / where was I / done) with cross-turn
// continuity (number_one_context, lib/number-one/context-store.ts) wired
// into /api/ai/chat's role:'number_one' branch. Its only Captain-facing
// entry point was Advisory Workbench's full ConsultView — Workbenches ->
// Advisory -> Consult -> pick Number One from an advisor list built for
// long-form multi-turn sessions with 6+ other personas. That is exactly the
// "HQ tells me something -> I identify the right Workbench -> navigate
// there -> find the function -> act" pattern Mission 7 §5 calls out. This
// widget is the fix: the same dispatcher, reached in two taps from anywhere,
// no advisor menu, no chat history to scroll past.
//
// Mirrors QuickCapture.tsx's established pattern deliberately (fixed
// floating button + Modal, safe-area-aware) rather than inventing a new one
// — opposite corner (bottom-left) so the two never collide. Do not add a
// third floating entry point without first checking both fit together at
// 375px width.
//
// No new reasoning/intelligence lives here (Mission 7 §4/§9's constraint) —
// this only renders replies from the one canonical dispatcher and, when a
// message doesn't match a canonical intent, falls through to the existing
// number_one LLM persona exactly as ConsultView already does.

import { useEffect, useRef, useState } from 'react';
import { Sparkles } from 'lucide-react';
import { Modal } from './Modal';

interface Turn {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  error?: boolean;
}

// The 8 query/state intents classifyIntent() recognises verbatim (excludes
// "remember", which needs free text — that's the text input below instead
// of a chip). Order mirrors the mission's own §9 list.
const QUICK_INTENTS: { label: string; phrase: string }[] = [
  { label: 'What matters?', phrase: 'What matters?' },
  { label: "What am I forgetting?", phrase: 'What am I forgetting?' },
  { label: "I'm stuck", phrase: "I'm stuck" },
  { label: "Still can't start", phrase: "Still can't start" },
  { label: 'Too much', phrase: 'Too much' },
  { label: 'Not now', phrase: 'Not now' },
  { label: 'Where was I?', phrase: 'Where was I?' },
  { label: 'Done', phrase: "Done" },
];

export function NumberOne() {
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [disabled, setDisabled] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [turns, busy]);

  async function send(content: string) {
    const body = content.trim();
    if (!body || busy) return;
    const userTurn: Turn = { id: Date.now().toString(), role: 'user', content: body };
    const history = [...turns, userTurn];
    setTurns(history);
    setText('');
    setBusy(true);
    try {
      const res = await fetch('/api/ai/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: history.map((t) => ({ role: t.role, content: t.content, id: t.id })),
          role: 'number_one',
          stream: false,
        }),
      });
      if (res.status === 503) {
        setDisabled(true);
        setTurns((prev) => [...prev, {
          id: `${Date.now()}-a`, role: 'assistant',
          content: "Number One's conversational model isn't switched on in this environment yet — Remember, Ready Room and the rest of HQ still work as normal from their own workbenches.",
        }]);
        return;
      }
      if (!res.ok) {
        setTurns((prev) => [...prev, {
          id: `${Date.now()}-a`, role: 'assistant', error: true,
          content: "Couldn't reach Number One just now — nothing was lost, try again in a moment.",
        }]);
        return;
      }
      const data = await res.json();
      const reply = typeof data?.content === 'string' && data.content.trim()
        ? data.content.trim()
        : "Didn't catch a usable reply — try again in a moment.";
      setTurns((prev) => [...prev, { id: `${Date.now()}-a`, role: 'assistant', content: reply }]);
    } catch {
      setTurns((prev) => [...prev, {
        id: `${Date.now()}-a`, role: 'assistant', error: true,
        content: "Couldn't reach Number One just now — nothing was lost, try again in a moment.",
      }]);
    } finally {
      setBusy(false);
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && !busy) {
      e.preventDefault();
      send(text);
    }
  }

  return (
    <>
      {/* Opposite corner from QuickCapture (bottom-right) — see file header.
          Same safe-area-aware offset fix as QuickCapture: below xl the fixed
          MobileCommandBar occupies the bottom ~4.5rem of the viewport, so a
          plain bottom-5 would render partly hidden behind/under it. */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Number One"
        title="Number One"
        className="fixed z-40 grid h-12 w-12 place-items-center rounded-full bg-wb-ink text-white shadow-lg transition hover:shadow-xl active:shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep
          bottom-[max(5.25rem,calc(env(safe-area-inset-bottom)_+_4.75rem))] left-[max(1.25rem,env(safe-area-inset-left))]
          xl:bottom-[max(1.25rem,env(safe-area-inset-bottom))]"
      >
        <Sparkles className="h-5 w-5" aria-hidden />
      </button>

      <Modal open={open} onClose={() => setOpen(false)} title="Number One">
        <div className="flex h-[60vh] max-h-[520px] flex-col gap-3 sm:h-[420px]">
          <div
            ref={scrollRef}
            role="log"
            aria-live="polite"
            aria-label="Conversation with Number One"
            className="min-h-0 flex-1 space-y-2.5 overflow-y-auto pr-1"
          >
            {turns.length === 0 && (
              <p className="text-[13px] text-wb-ink2">
                Ask what matters, say what&rsquo;s stuck, or tell it what to remember — Number One routes to the
                right place in HQ so you don&rsquo;t have to.
              </p>
            )}
            {turns.map((t) => (
              <div
                key={t.id}
                className={`rounded-md px-3 py-2 text-[13px] leading-snug ${
                  t.role === 'user'
                    ? 'ml-6 bg-wb-sage-deep/10 text-wb-ink'
                    : t.error
                      ? 'mr-6 bg-wb-crit/10 text-wb-crit-on'
                      : 'mr-6 bg-wb-surface-raised text-wb-ink'
                }`}
              >
                {t.content}
              </div>
            ))}
            {busy && (
              <div className="mr-6 rounded-md bg-wb-surface-raised px-3 py-2 text-[13px] text-wb-ink2 animate-pulse">
                Thinking…
              </div>
            )}
          </div>

          {!disabled && (
            <div className="flex shrink-0 flex-wrap gap-1.5">
              {QUICK_INTENTS.map((q) => (
                <button
                  key={q.label}
                  type="button"
                  onClick={() => send(q.phrase)}
                  disabled={busy}
                  className="rounded-md border border-wb-line px-2.5 py-1.5 text-[12px] font-medium text-wb-ink2 transition-colors hover:border-wb-sage-deep/40 hover:text-wb-ink disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {q.label}
                </button>
              ))}
            </div>
          )}

          {!disabled && (
            <form
              className="flex shrink-0 items-center gap-2"
              onSubmit={(e) => { e.preventDefault(); send(text); }}
            >
              <input
                type="text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="Or type — e.g. &ldquo;Remember to send the referral Friday&rdquo;"
                aria-label="Message Number One"
                disabled={busy}
                className="w-full min-w-0 flex-1 rounded-md border border-wb-line bg-wb-bg px-3 py-2 text-[13px] text-wb-ink placeholder:text-wb-ink2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
              />
              <button
                type="submit"
                disabled={busy || !text.trim()}
                className="shrink-0 rounded-md bg-wb-sage-deep px-3 py-2 text-[13px] font-semibold text-white transition-opacity hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Send
              </button>
            </form>
          )}
        </div>
      </Modal>
    </>
  );
}
