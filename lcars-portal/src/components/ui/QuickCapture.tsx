'use client';

// Global quick-capture (2026-08 UX review) — the one gap CaptureBox
// (content-workbench) and CaptureView (capture-workbench) both left open:
// each only exists on its own workbench, so recording a stray thought
// first required deciding which of six workbenches it belonged in and
// navigating there. This reuses captureItem()/CAPTURE_TYPES from
// lib/capture.ts unchanged (the same pipeline CaptureView already writes
// to - captured_items, review-first, no auto-mission-creation) tagged
// under the 'portal-floating-capture' channel that lib/capture.ts's own
// KNOWN_CHANNELS list already reserved for exactly this. Mounted once
// inside WorkbenchShell (every workbench) and once on the hub, so a
// capture is always at most one click away.
//
// Deliberately button-only, no global keyboard shortcut: a page-wide
// keydown listener risks firing while the user is typing in one of the
// many existing textareas (several of which already bind their own
// Cmd/Ctrl+Enter). A reliably-placed button beats an unreliable shortcut.

import { useRef, useState } from 'react';
import { Modal } from './Modal';
import { CAPTURE_TYPES, captureItem, captureTypeMeta, type CaptureType } from '@/lib/capture';

export function QuickCapture() {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [type, setType] = useState<CaptureType>('note');
  const [saving, setSaving] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  function reset() {
    setText('');
    setType('note');
    setError(null);
  }

  async function submit() {
    const body = text.trim();
    if (!body || saving) return;
    setSaving(true);
    setError(null);
    const res = await captureItem(body, type, undefined, 'portal-floating-capture');
    setSaving(false);
    if (!res.ok) {
      setError(res.error ?? 'Capture failed.');
      return;
    }
    setFlash(`✓ ${captureTypeMeta(type).label} captured`);
    reset();
    setTimeout(() => setOpen(false), 900);
    setTimeout(() => setFlash(null), 2000);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      submit();
    }
  }

  return (
    <>
      {/* 2026-08-09 mobile/iPad review (P2): bottom-5/right-5 alone can sit
          under iOS's home-indicator/dynamic bottom toolbar or an Android
          gesture-nav zone on some devices. max(1.25rem, safe-area-inset)
          keeps the existing 20px desktop offset but grows to clear the
          real device inset where one exists — a no-op on desktop/most
          Android, a real fix on notched/gesture-nav iOS. active: added
          alongside the existing hover:-only lift, which never fired on
          touch. */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Quick capture"
        title="Quick capture"
        className="fixed z-40 grid h-12 w-12 place-items-center rounded-full bg-wb-sage-deep text-[22px] font-semibold text-white shadow-lg transition hover:shadow-xl active:shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-ink"
        style={{
          bottom: 'max(1.25rem, env(safe-area-inset-bottom))',
          right: 'max(1.25rem, env(safe-area-inset-right))',
        }}
      >
        +
      </button>

      <Modal open={open} onClose={() => { setOpen(false); reset(); }} title="Quick Capture">
        <div className="space-y-3">
          <textarea
            ref={inputRef}
            autoFocus
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKeyDown}
            rows={4}
            placeholder="What do you want to capture?"
            aria-label="Capture text"
            className="w-full resize-none rounded-md border border-wb-line bg-wb-bg px-3 py-3 text-[14px] text-wb-ink placeholder:text-wb-ink2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
          />
          <div className="flex flex-wrap gap-1.5">
            {CAPTURE_TYPES.map((t) => (
              <button
                key={t.key}
                type="button"
                onClick={() => setType(t.key)}
                aria-pressed={type === t.key}
                className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[12px] font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep ${
                  type === t.key ? 'border-wb-sage-deep bg-wb-sage-deep/10 text-wb-sage-deep' : 'border-wb-line text-wb-ink2 hover:border-wb-sage-deep/40'
                }`}
              >
                <span aria-hidden>{t.glyph}</span>
                {t.label}
              </button>
            ))}
          </div>
          <p className="text-[11px] italic text-wb-ink2">{captureTypeMeta(type).hint}</p>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={submit}
              disabled={saving || !text.trim()}
              className="rounded-md bg-wb-sage-deep px-4 py-2 text-[13px] font-semibold text-white transition-opacity hover:opacity-80 disabled:opacity-40"
            >
              {saving ? 'Capturing…' : 'Capture'}
            </button>
            <span className="rounded border border-wb-line bg-wb-bg px-1.5 py-0.5 text-[10px] font-medium text-wb-ink2">⌘/Ctrl + Enter</span>
            {flash && <span className="text-[12px] text-wb-ok-on" role="status" aria-live="polite">{flash}</span>}
          </div>
          {error && <p className="text-[12px] text-wb-crit-on">{error}</p>}
        </div>
      </Modal>
    </>
  );
}
