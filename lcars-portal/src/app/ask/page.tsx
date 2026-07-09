'use client';

// STARSHIP-REDESIGN.md §6: Ask. One input box, one prose answer, a "based
// on" line. No persistent chat log, no card grid, no dashboard - a single
// question in, a single honest answer out. Reached only from Home's quiet
// link; one way back: Home. Placed outside the legacy (app) nav shell,
// matching Home and Decide.

import { useCallback, useState } from 'react';
import Link from 'next/link';
import { answerQuery, SUGGESTED_QUERIES, type AskAnswer } from '@/lib/ask';

function fmtLatest(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' });
}

export default function AskPage() {
  const [input, setInput] = useState('');
  const [asked, setAsked] = useState<string | null>(null);
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [loading, setLoading] = useState(false);

  const ask = useCallback(async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) return;
    setLoading(true);
    setAsked(trimmed);
    const res = await answerQuery(trimmed);
    setAnswer(res);
    setLoading(false);
  }, []);

  return (
    <main className="min-h-screen flex justify-center bg-[#0B1017] text-[#E8EDF2]">
      <div className="w-full max-w-[620px] px-7 pt-10 pb-14 flex flex-col min-h-screen">
        <Link
          href="/captains-chair"
          className="text-sm text-[#5A6875] hover:text-[#93A1B0] mb-8 inline-flex items-center gap-1.5 w-fit"
        >
          ← Home
        </Link>

        <h1
          className="text-[26px] mb-6"
          style={{
            fontFamily: '"New York", "SF Pro Display", Georgia, serif',
            fontWeight: 500,
            textTransform: 'none',
          }}
        >
          Ask
        </h1>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask(input);
          }}
          className="flex gap-2 mb-8"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="What missions are active?"
            className="flex-1 bg-[#101722] border border-[rgba(147,161,176,0.25)] rounded-md px-4 py-3 text-[15px] text-[#E8EDF2] placeholder:text-[#5A6875] focus:outline-none focus:border-[#6FB3C9]"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="px-5 py-3 rounded-md bg-[#58C0A8] text-[#0B1017] text-[15px] font-medium disabled:opacity-50"
          >
            Ask
          </button>
        </form>

        {!asked && (
          <div className="flex flex-col gap-2">
            <p className="text-[12.5px] uppercase tracking-[0.14em] text-[#5A6875] mb-1">Try asking</p>
            {SUGGESTED_QUERIES.map((q) => (
              <button
                key={q}
                onClick={() => {
                  setInput(q);
                  ask(q);
                }}
                className="text-left text-[14.5px] text-[#93A1B0] hover:text-[#E8EDF2] underline underline-offset-2 decoration-[rgba(147,161,176,0.3)] w-fit"
              >
                {q}
              </button>
            ))}
          </div>
        )}

        {loading && <p className="text-[#5A6875] text-[15px]">Checking…</p>}

        {!loading && answer && (
          <div className="flex flex-col gap-4">
            <p className="text-[12.5px] uppercase tracking-[0.14em] text-[#5A6875]">&ldquo;{asked}&rdquo;</p>
            <p className="text-[17px] text-[#E8EDF2] leading-relaxed">{answer.prose}</p>
            {answer.basedOn.length > 0 && (
              <div className="text-[12.5px] text-[#5A6875] leading-relaxed">
                Based on:{' '}
                {answer.basedOn.map((s, i) => (
                  <span key={s.label}>
                    {i > 0 && ' · '}
                    {s.label} ({s.count} record{s.count === 1 ? '' : 's'}
                    {fmtLatest(s.latest) ? `, latest ${fmtLatest(s.latest)}` : ''})
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
