'use client';

// Captain's Log (MSN-0364) — a one-line capture box pinned on the Chair
// page itself, not a link out to the Notebook sub-page. Friction is the
// enemy of capturing a fleeting thought (mission doc §10, locked
// decision). Same insert shape as notebook/page.tsx's handleCapture() —
// plain capture into the existing intelligence_notes triage workflow,
// unchanged. Route-suggestion/classification (brief §12) deferred to a
// fast-follow per Captain's instruction; this ships plain capture only.

import Link from 'next/link';
import { useRef, useState } from 'react';
import { WorkbenchPanel } from '@/components/WorkbenchPanel';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

export function CaptainsLog() {
  const [text, setText] = useState('');
  const [saving, setSaving] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function submit() {
    const body = text.trim();
    if (!body || saving) return;
    setSaving(true);
    setError(null);
    try {
      const supabase = createSupabaseBrowserClient();
      const { error: insertError } = await supabase.from('intelligence_notes').insert({
        title: null,
        raw_content: body,
        tags: [],
        source: 'manual',
        status: 'CAPTURED',
      });
      if (insertError) throw insertError;
      setFlash('✓ Captured');
      setText('');
      setTimeout(() => setFlash(null), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Capture failed');
    } finally {
      setSaving(false);
      inputRef.current?.focus();
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') { e.preventDefault(); submit(); }
  }

  return (
    <WorkbenchPanel
      title="Captain's Log"
      actions={<Link href="/captains-chair-workbench/notebook" className="text-[10px] uppercase tracking-[0.15em] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">Open Log →</Link>}
    >
      <div className="flex items-center gap-2">
        <input
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Capture a thought, decision or instruction…"
          aria-label="Capture a thought, decision or instruction"
          className="w-full rounded-md border border-wb-line bg-wb-bg px-3 py-2 text-[13.5px] text-wb-ink placeholder:text-wb-ink2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
        />
        <button
          type="button"
          onClick={submit}
          disabled={saving || !text.trim()}
          aria-label="Capture"
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-wb-sage-deep text-[16px] font-semibold text-white transition hover:opacity-90 disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-ink"
        >
          +
        </button>
      </div>
      <p className="mt-2 min-h-[1lh] text-[11px]" role="status" aria-live="polite">
        {flash && <span className="text-wb-ok-on">{flash}</span>}
        {error && <span className="text-wb-crit-on">{error}</span>}
      </p>
    </WorkbenchPanel>
  );
}
