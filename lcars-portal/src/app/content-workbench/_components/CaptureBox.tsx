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
import { discard } from './stageBodies';

interface CaptureResult {
  content_id: string;
  pillar_name: string;
  rank_score: number;
  captain_focus: boolean;
  suggested_angle: string;
  reasons: string[];
}

/** MSN-0363 §7: 0-100 rank_score presented as a plain-language tier, never
 * a bare unexplained number. */
function scoreTier(score: number): string {
  if (score >= 70) return 'HIGH POTENTIAL';
  if (score >= 45) return 'MODERATE';
  return 'LOW';
}

export function CaptureBox({ onCaptured, onDevelop }: { onCaptured: () => void; onDevelop?: (contentId: string) => void }) {
  const [text, setText] = useState('');
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<CaptureResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [focused, setFocused] = useState(false);
  const [archiving, setArchiving] = useState(false);
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
      setResult({
        content_id: data.content_id,
        pillar_name: data.pillar_name,
        rank_score: data.rank_score,
        captain_focus: data.captain_focus,
        suggested_angle: data.suggested_angle,
        reasons: data.reasons ?? [],
      });
      setText('');
      onCaptured();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Capture failed');
    } finally {
      setSaving(false);
      inputRef.current?.focus();
    }
  }

  async function archiveResult() {
    if (!result) return;
    setArchiving(true);
    try {
      await discard(result.content_id);
      onCaptured();
    } finally {
      setArchiving(false);
      setResult(null);
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

        {!result && <p className="mt-3 min-h-[1lh] text-[12px] text-wb-crit-on">{error}</p>}

        {result && (
          <div className="mt-3 space-y-2 rounded-lg border border-wb-ok/40 bg-wb-ok/5 p-3">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="rounded-full bg-wb-ok/15 px-2 py-0.5 text-[11px] font-semibold text-wb-ok-on">✓ Opportunity Created</span>
              <span className="text-[12px] font-semibold text-wb-ink">{result.rank_score.toFixed(0)} / 100 — {scoreTier(result.rank_score)}</span>
              {result.captain_focus && <span className="rounded-full bg-wb-warn/15 px-2 py-0.5 text-[10.5px] font-semibold text-wb-warn-on">★ Captain Focus</span>}
            </div>
            <p className="text-[12px] text-wb-ink2">Pillar: <span className="text-wb-ink">{result.pillar_name}</span></p>
            {result.reasons.length > 0 && (
              <ul className="list-inside list-disc text-[11.5px] leading-relaxed text-wb-ink2">
                {result.reasons.map((r, i) => (<li key={i}>{r}</li>))}
              </ul>
            )}
            {result.suggested_angle && (
              <p className="text-[12.5px] italic leading-relaxed text-wb-ink">&ldquo;{result.suggested_angle}&rdquo;</p>
            )}
            <div className="flex flex-wrap gap-2 pt-1">
              <Button size="sm" onClick={() => { onDevelop?.(result.content_id); setResult(null); }}>
                Develop this →
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setResult(null)}>
                Keep for later
              </Button>
              <Button size="sm" variant="secondary" onClick={archiveResult} disabled={archiving}>
                {archiving ? 'Archiving…' : 'Archive'}
              </Button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
