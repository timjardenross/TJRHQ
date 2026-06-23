'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import {
  CAPTURE_TYPES,
  captureItem,
  captureTypeMeta,
  fetchRecentCaptures,
  type CaptureType,
  type RecentCapture,
} from '@/lib/capture';
import { DEPARTMENTS } from '@/lib/departments';

// ── Type chip ─────────────────────────────────────────────────────────────────

function TypeChips({
  selected,
  onChange,
}: {
  selected: CaptureType;
  onChange: (t: CaptureType) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {CAPTURE_TYPES.map((t) => {
        const active = t.key === selected;
        const dept = DEPARTMENTS[t.tone];
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            aria-pressed={active}
            className={[
              'flex items-center gap-2 rounded-lcars border px-4 py-2.5 text-sm font-semibold transition-colors',
              active
                ? `${dept.border} ${dept.bgSoft} ${dept.text}`
                : 'border-edge bg-space/40 text-lcars-muted hover:border-edge/80',
            ].join(' ')}
          >
            <span aria-hidden className="text-base leading-none">{t.glyph}</span>
            {t.label}
          </button>
        );
      })}
    </div>
  );
}

// ── Recent captures ─────────────────────────────────────────────────────────

function RecentList({ items }: { items: RecentCapture[] }) {
  if (!items.length) return null;
  const CLASS_LABEL: Record<string, string> = {
    reference: 'Note',
    research: 'Idea',
    mission: 'Mission',
    personal: 'Health',
  };
  return (
    <div className="rounded-lcars border border-edge bg-panel/40 p-4">
      <p className="mb-3 text-[10px] uppercase tracking-[0.25em] text-lcars-muted">Recently captured</p>
      <ul className="flex flex-col gap-2">
        {items.map((it) => (
          <li key={it.id} className="flex items-start gap-2 text-sm">
            <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-lcars-muted" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-lcars-text">{it.title}</p>
              <p className="text-[10px] uppercase tracking-wide text-lcars-muted">
                {CLASS_LABEL[it.classification ?? ''] ?? it.classification ?? 'capture'} ·{' '}
                {new Date(it.captured_at).toLocaleString('en-AU', {
                  day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false,
                })}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function QuickCapturePage() {
  const [text, setText] = useState('');
  const [type, setType] = useState<CaptureType>('note');
  const [showTypes, setShowTypes] = useState(false);
  const [saving, setSaving] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<RecentCapture[]>([]);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    fetchRecentCaptures().then(setRecent);
  }, []);

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
    setFlash(`${captureTypeMeta(type).label} captured`);
    setText('');
    setType('note');
    setShowTypes(false);
    fetchRecentCaptures().then(setRecent);
    inputRef.current?.focus();
    setTimeout(() => setFlash(null), 2200);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      submit();
    }
  }

  const meta = captureTypeMeta(type);

  return (
    <div className="mx-auto flex max-w-[640px] flex-col gap-4">
      <header>
        <p className="text-[10px] uppercase tracking-[0.3em] text-lcars-muted">Quick Capture</p>
        <h1 className="font-lcars text-2xl font-bold text-engineering">Capture it. Move on.</h1>
        <p className="mt-1 text-sm text-lcars-muted">
          One box. Type the thing — sort it later. Routes straight into the Captain&apos;s Inbox.
        </p>
      </header>

      {/* Single input box — the primary action */}
      <div className="rounded-lcars border border-edge bg-panel/60 p-3">
        <textarea
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          rows={4}
          placeholder="What do you want to capture?"
          className="w-full resize-none rounded-lcars border border-edge bg-space px-3 py-3 text-base text-lcars-text placeholder:text-lcars-muted focus:border-engineering focus:outline-none"
        />

        {/* Optional type selector — collapsed by default to keep it single-box-first */}
        <div className="mt-3 flex flex-col gap-3">
          {!showTypes ? (
            <button
              type="button"
              onClick={() => setShowTypes(true)}
              className="self-start text-xs uppercase tracking-[0.15em] text-lcars-muted hover:text-engineering"
            >
              Type: <span className="text-engineering">{meta.label}</span> · change ▾
            </button>
          ) : (
            <div className="flex flex-col gap-2">
              <TypeChips selected={type} onChange={setType} />
              <p className="text-[11px] italic text-lcars-muted/80">{meta.hint}</p>
            </div>
          )}

          <button
            type="button"
            onClick={submit}
            disabled={saving || !text.trim()}
            className="w-full rounded-lcars bg-engineering px-4 py-3 font-lcars text-base font-bold uppercase tracking-[0.2em] text-space transition-opacity hover:opacity-80 disabled:opacity-40"
          >
            {saving ? 'Capturing…' : `Capture ${meta.label}`}
          </button>
          <p className="text-center text-[10px] uppercase tracking-[0.15em] text-lcars-muted">
            ⌘/Ctrl + Enter to capture
          </p>
        </div>
      </div>

      {flash && (
        <div className="rounded-lcars border border-status/50 bg-status/10 px-4 py-3 text-sm font-semibold text-status">
          ✓ {flash} — added to the Captain&apos;s Inbox.
        </div>
      )}
      {error && (
        <div className="rounded-lcars border border-operations/50 bg-operations/10 px-4 py-3 text-sm text-operations">
          {error}
        </div>
      )}

      {/* Health shortcut — the structured pipeline lives in Medical Bay */}
      {type === 'health' && (
        <Link
          href="/medical/check-in"
          className="rounded-lcars border border-medical/40 bg-medical/5 px-4 py-3 text-center text-xs uppercase tracking-[0.15em] text-medical hover:border-medical/70"
        >
          Need a full check-in? Open Medical Bay →
        </Link>
      )}

      <RecentList items={recent} />
    </div>
  );
}
