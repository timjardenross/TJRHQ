'use client';

// Capture stage entry point — posts to /api/content-workbench/capture, which
// scores the text (pillar + rank_score) before insert. Deliberately a
// separate, simpler form than capture-workbench/_components/CaptureView.tsx —
// this one only ever creates comms_content opportunities, it doesn't offer
// the note/mission/health/idea/decision types (that's still the Capture
// Workbench's job; this workbench starts one step downstream of it).
//
// 2026-08 visual redesign: restyled as a "composer" (agency-tool convention —
// Buffer/Later put the same kind of prominent capture bar at the top of the
// queue). Same submit() logic and API contract, purely a JSX/styling pass.

import { useRef, useState } from 'react';
import { Button } from '@/components/ui';

export function CaptureBox({ onCaptured }: { onCaptured: () => void }) {
  const [text, setText] = useState('');
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<{ pillar_name: string; rank_score: number; captain_focus: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  async function submit() {
    const body = text.trim();
    if (!body || saving) return;
    setSaving(true);
    setError(null);
    try {
      const res = await fetch('/api/content-workbench/capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: body }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'Capture failed');
      setResult({ pillar_name: data.pillar_name, rank_score: data.rank_score, captain_focus: data.captain_focus });
      setText('');
      onCaptured();
      setTimeout(() => setResult(null), 4000);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Capture failed');
    } finally {
      setSaving(false);
      inputRef.current?.focus();
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      submit();
    }
  }

  return (
    <section
      className={`mb-5 overflow-hidden rounded-xl border bg-wb-surface shadow-sm transition-colors ${
        focused ? 'border-wb-sage-deep' : 'border-wb-line'
      }`}
    >
      <div className="h-1 bg-gradient-to-r from-wb-sage via-wb-warn to-wb-ok" aria-hidden />
      <div className="p-4">
        <div className="mb-2 flex items-center gap-2">
          <span className="grid h-6 w-6 place-items-center rounded-full bg-wb-sage-deep text-[12px] text-white" aria-hidden>+</span>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-wb-ink2">New content idea</p>
        </div>
        <textarea
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          rows={3}
          placeholder="Capture a content idea or topic — it's scored and pillar-classified automatically."
          aria-label="Capture content idea"
          className="w-full resize-none rounded-lg border border-wb-line bg-wb-bg px-3 py-3 text-[14px] leading-snug text-wb-ink placeholder:text-wb-ink2 focus:border-wb-sage-deep focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
        />
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button onClick={submit} disabled={saving || !text.trim()}>
            {saving ? 'Capturing…' : 'Capture & Score'}
          </Button>
          <span className="rounded border border-wb-line bg-wb-bg px-1.5 py-0.5 text-[10px] font-medium text-wb-ink2">
            ⌘/Ctrl + Enter
          </span>
        </div>

        <p className="mt-3 flex min-h-[1lh] flex-wrap items-center gap-1.5 text-[12px] text-wb-ok-on" role="status" aria-live="polite">
          {result && (
            <>
              <span className="rounded-full bg-wb-ok/15 px-2 py-0.5 font-semibold">✓ Captured</span>
              <span>{result.pillar_name} · rank {result.rank_score.toFixed(1)}</span>
              {result.captain_focus && <span className="rounded-full bg-wb-warn/15 px-2 py-0.5 font-semibold text-wb-warn-on">★ Captain Priority</span>}
              <span className="text-wb-ink2">— add a research brief below to move it forward.</span>
            </>
          )}
        </p>
        <p className="mt-3 min-h-[1lh] text-[12px] text-wb-crit-on">{error}</p>
      </div>
    </section>
  );
}
