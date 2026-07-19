'use client';

// Phase B — Quick Capture form. Ported from the legacy Capture page.
// Reuses captureItem() / CAPTURE_TYPES / captureTypeMeta from lib/capture
// unchanged (comms -> /api/content/draft, all else -> captured_items insert).
// Classification/type chips are neutral + glyph per Captain decision 2026-07-12.

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Card } from '@/components/ui';
import {
  CAPTURE_TYPES,
  captureItem,
  captureTypeMeta,
  type CaptureType,
} from '@/lib/capture';

function TypeChips({ selected, onChange }: { selected: CaptureType; onChange: (t: CaptureType) => void }) {
  return (
    <div className="flex flex-wrap gap-2">
      {CAPTURE_TYPES.map((t) => {
        const active = t.key === selected;
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            aria-pressed={active}
            className={`flex items-center gap-2 rounded-md border px-4 py-2.5 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep ${
              active ? 'border-wb-sage-deep bg-wb-sage-deep/10 text-wb-sage-deep' : 'border-wb-line text-wb-ink2 hover:border-wb-sage-deep/40'
            }`}
          >
            <span aria-hidden className="text-base leading-none">{t.glyph}</span>
            {t.label}
          </button>
        );
      })}
    </div>
  );
}

export function CaptureView({ onCaptured }: { onCaptured: () => void }) {
  const [text, setText] = useState('');
  const [type, setType] = useState<CaptureType>('note');
  const [showTypes, setShowTypes] = useState(false);
  const [saving, setSaving] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [commsCapture, setCommsCapture] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  async function submit() {
    const body = text.trim();
    if (!body || saving) return;
    setSaving(true);
    setError(null);
    const res = await captureItem(body, type);
    setSaving(false);
    if (!res.ok) {
      setError(res.error ?? 'Capture failed.');
      return;
    }
    const meta = captureTypeMeta(type);
    const isComms = type === 'comms';
    setCommsCapture(isComms);
    setFlash(isComms ? 'Added to content pipeline' : `${meta.label} captured`);
    setText('');
    setType('note');
    setShowTypes(false);
    if (!isComms) onCaptured();
    inputRef.current?.focus();
    setTimeout(() => { setFlash(null); setCommsCapture(false); }, 2200);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      submit();
    }
  }

  const meta = captureTypeMeta(type);

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <textarea
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          rows={4}
          placeholder="What do you want to capture?"
          aria-label="Capture text"
          className="w-full resize-none rounded-md border border-wb-line bg-wb-bg px-3 py-3 text-base text-wb-ink placeholder:text-wb-ink2 focus:border-wb-sage-deep focus:outline-none"
        />

        <div className="mt-3 flex flex-col gap-3">
          {!showTypes ? (
            <button
              type="button"
              onClick={() => setShowTypes(true)}
              className="self-start text-xs uppercase tracking-[0.14em] text-wb-ink2 hover:text-wb-sage-deep"
            >
              Type: <span className="text-wb-sage-deep">{meta.label}</span> · change ▾
            </button>
          ) : (
            <div className="flex flex-col gap-2">
              <TypeChips selected={type} onChange={setType} />
              <p className="text-[11px] italic text-wb-ink2">{meta.hint}</p>
            </div>
          )}

          <button
            type="button"
            onClick={submit}
            disabled={saving || !text.trim()}
            className="w-full rounded-md bg-wb-sage-deep px-4 py-3 text-base font-semibold uppercase tracking-[0.14em] text-white transition-opacity hover:opacity-80 disabled:opacity-40"
          >
            {saving ? 'Capturing…' : `Capture ${meta.label}`}
          </button>
          <p className="text-center text-[10px] uppercase tracking-[0.14em] text-wb-ink2">⌘/Ctrl + Enter to capture</p>
        </div>
      </Card>

      {flash && (
        <div className="rounded-md border border-wb-ok/50 bg-wb-ok/10 px-4 py-3 text-sm font-semibold text-wb-ok-on">
          ✓ {flash}
          {commsCapture ? (
            <> — <Link href="/comms" className="text-wb-sage-deep underline">view in Content Pipeline →</Link></>
          ) : ' — added to the Capture Inbox.'}
        </div>
      )}
      {error && (
        <div className="rounded-md border border-wb-crit/50 bg-wb-crit/10 px-4 py-3 text-sm text-wb-crit-on">{error}</div>
      )}

      {type === 'health' && (
        <Link
          href="/medical/check-in"
          className="rounded-md border border-wb-line bg-wb-surface px-4 py-3 text-center text-xs uppercase tracking-[0.14em] text-wb-sage-deep hover:border-wb-sage-deep/50"
        >
          Need a full check-in? Open Medical Bay →
        </Link>
      )}
    </div>
  );
}
