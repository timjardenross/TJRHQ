'use client';

// Capture stage entry point — posts to /api/content-workbench/capture, which
// scores the text (pillar + rank_score) before insert. Deliberately a
// separate, simpler form than capture-workbench/_components/CaptureView.tsx —
// this one only ever creates comms_content opportunities, it doesn't offer
// the note/mission/health/idea/decision types (that's still the Capture
// Workbench's job; this workbench starts one step downstream of it).

import { useRef, useState } from 'react';
import { Card, Button } from '@/components/ui';

export function CaptureBox({ onCaptured }: { onCaptured: () => void }) {
  const [text, setText] = useState('');
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<{ pillar_name: string; rank_score: number; captain_focus: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
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
    <Card className="mb-4">
      <textarea
        ref={inputRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        rows={3}
        placeholder="Capture a content idea or topic — it's scored and pillar-classified automatically."
        aria-label="Capture content idea"
        className="w-full resize-none rounded-md border border-wb-line bg-wb-bg px-3 py-3 text-base text-wb-ink placeholder:text-wb-ink2 focus:border-wb-sage-deep focus:outline-none"
      />
      <div className="mt-3 flex items-center gap-3">
        <Button onClick={submit} disabled={saving || !text.trim()}>
          {saving ? 'Capturing…' : '✉ Capture & Score'}
        </Button>
        <p className="text-[10px] uppercase tracking-[0.14em] text-wb-ink2">⌘/Ctrl + Enter</p>
      </div>

      {result && (
        <p className="mt-2 text-[12px] text-wb-ok-on" role="status" aria-live="polite">
          ✓ Captured — {result.pillar_name}, rank {result.rank_score.toFixed(1)}
          {result.captain_focus ? ' · ⭐ Captain Priority' : ''}. Add a research brief below to move it forward.
        </p>
      )}
      {error && <p className="mt-2 text-[12px] text-wb-crit-on">{error}</p>}
    </Card>
  );
}
