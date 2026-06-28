'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import {
  CAPTURE_TYPES,
  KNOWN_CHANNELS,
  SOURCE_BADGE,
  captureItem,
  captureTypeMeta,
  fetchInboxCaptures,
  fetchRecentCaptures,
  markCaptureReviewed,
  dismissCapture,
  archiveCapture,
  updateCaptureClassification,
  updateCaptureImportance,
  promoteCaptureToMission,
  routeCapture,
  type CaptureType,
  type InboxCapture,
  type CaptureClassification,
  type CaptureImportance,
} from '@/lib/capture';
import { DEPARTMENTS } from '@/lib/departments';

// ── Small utilities ───────────────────────────────────────────────────────────

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString('en-AU', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false,
  });
}

// ── Source badge chip ─────────────────────────────────────────────────────────

const TONE_TEXT: Record<string, string> = {
  engineering: 'text-engineering border-engineering/50 bg-engineering/10',
  science:     'text-science border-science/50 bg-science/10',
  command:     'text-command border-command/50 bg-command/10',
  operations:  'text-operations border-operations/50 bg-operations/10',
  medical:     'text-medical border-medical/50 bg-medical/10',
};

function SourceBadge({ channelId }: { channelId: string | null | undefined }) {
  const { label, tone } = channelId && SOURCE_BADGE[channelId]
    ? SOURCE_BADGE[channelId]
    : { label: 'Unknown', tone: 'command' };
  const isVoice = channelId === 'telegram-xo-voice-capture';
  return (
    <span className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${TONE_TEXT[tone] ?? TONE_TEXT.command}`}>
      {isVoice && <span aria-hidden>🎙</span>}
      {label}
    </span>
  );
}

function ClassBadge({ classification }: { classification: string | null | undefined }) {
  if (!classification) return null;
  const map: Record<string, string> = {
    mission:       'text-engineering border-engineering/40 bg-engineering/10',
    personal:      'text-medical border-medical/40 bg-medical/10',
    research:      'text-science border-science/40 bg-science/10',
    decision:      'text-operations border-operations/40 bg-operations/10',
    reference:     'text-command border-command/40 bg-command/10',
    unclassified:  'text-lcars-muted border-edge bg-edge/20',
  };
  const label: Record<string, string> = {
    mission: 'Mission', personal: 'Health', research: 'Idea/Research',
    decision: 'Decision', reference: 'Note', unclassified: 'Unclassified',
  };
  return (
    <span className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${map[classification] ?? map.unclassified}`}>
      {label[classification] ?? classification}
    </span>
  );
}

function AiBadge({ status }: { status: string | null | undefined }) {
  const s = status ?? 'not_enriched';
  const map: Record<string, { label: string; cls: string }> = {
    not_enriched: { label: 'Not enriched',       cls: 'text-lcars-muted border-edge bg-transparent' },
    queued:       { label: 'Enrichment queued',  cls: 'text-command border-command/40 bg-command/10' },
    enriched:     { label: 'Enriched',           cls: 'text-status border-status/40 bg-status/10' },
    failed:       { label: 'Enrichment failed',  cls: 'text-operations border-operations/40 bg-operations/10' },
  };
  const { label, cls } = map[s] ?? map.not_enriched;
  return (
    <span className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${cls}`}>
      ✦ {label}
    </span>
  );
}

// ── Voice metadata from summary ───────────────────────────────────────────────

function VoiceMeta({ summary }: { summary: Record<string, unknown> | null }) {
  if (!summary) return null;
  const origin = summary.capture_origin;
  if (origin !== 'telegram_voice') return null;
  const dur = summary.duration_s as number | undefined;
  const model = summary.transcription_model as string | undefined;
  const conf = summary.confidence as number | undefined;
  return (
    <div className="mt-1 flex flex-wrap gap-2 text-[10px] text-lcars-muted">
      {dur !== undefined && <span>⏱ {dur.toFixed(1)}s</span>}
      {model && <span>Model: {model}</span>}
      {conf !== undefined && <span>Conf: {(conf * 100).toFixed(0)}%</span>}
    </div>
  );
}

// ── Type chips (capture form) ─────────────────────────────────────────────────

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
        const dept   = DEPARTMENTS[t.tone as keyof typeof DEPARTMENTS];
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

// ── Inbox filter tabs ─────────────────────────────────────────────────────────

type InboxFilter =
  | 'all'
  | 'portal'
  | 'telegram-voice'
  | 'mission'
  | 'health'
  | 'research'
  | 'decision'
  | 'unclassified';

const INBOX_FILTERS: { key: InboxFilter; label: string }[] = [
  { key: 'all',           label: 'All' },
  { key: 'portal',        label: 'Portal' },
  { key: 'telegram-voice', label: 'Telegram Voice' },
  { key: 'mission',       label: 'Mission' },
  { key: 'health',        label: 'Health' },
  { key: 'research',      label: 'Idea/Research' },
  { key: 'decision',      label: 'Decision' },
  { key: 'unclassified',  label: 'Unclassified' },
];

function filterToQuery(f: InboxFilter): {
  source?: string;
  classification?: CaptureClassification;
} {
  if (f === 'portal')         return { source: 'lcars-mobile-quick-capture' };
  if (f === 'telegram-voice') return { source: 'telegram-xo-voice-capture' };
  if (f === 'mission')        return { classification: 'mission' };
  if (f === 'health')         return { classification: 'personal' };
  if (f === 'research')       return { classification: 'research' };
  if (f === 'decision')       return { classification: 'decision' };
  if (f === 'unclassified')   return { classification: 'unclassified' };
  return {};
}

// ── Capture item row with inline actions ──────────────────────────────────────

function CaptureRow({
  item,
  onRefresh,
}: {
  item: InboxCapture;
  onRefresh: () => void;
}) {
  const [expanded,  setExpanded]  = useState(false);
  const [busy,      setBusy]      = useState(false);
  const [flash,     setFlash]     = useState<string | null>(null);
  const [err,       setErr]       = useState<string | null>(null);
  const [newClass,  setNewClass]  = useState<CaptureClassification>(item.classification ?? 'unclassified');
  const [newImp,    setNewImp]    = useState<CaptureImportance>(item.importance ?? 'medium');

  const act = useCallback(async (fn: () => Promise<{ ok: boolean; error?: string; mission_id?: string }>, label: string) => {
    setBusy(true);
    setErr(null);
    const res = await fn();
    setBusy(false);
    if (!res.ok) {
      setErr(res.error ?? 'Action failed.');
    } else {
      const msg = res.mission_id ? `${label} — Mission candidate: ${res.mission_id}` : label;
      setFlash(msg);
      setTimeout(() => { setFlash(null); onRefresh(); }, 1800);
    }
  }, [onRefresh]);

  const preview = (item.raw_text ?? item.title ?? '').slice(0, 160);
  const isVoice = item.source_channel_id === 'telegram-xo-voice-capture';

  return (
    <li className="flex flex-col rounded-lcars border border-edge bg-panel/40 transition-colors hover:border-edge/80">
      {/* ── Header row ── */}
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="flex w-full items-start gap-3 px-4 py-3 text-left"
      >
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-lcars-text">
            {item.title ?? '(untitled)'}
          </p>
          {isVoice && item.summary && (
            <VoiceMeta summary={item.summary} />
          )}
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <SourceBadge channelId={item.source_channel_id} />
            <ClassBadge classification={item.classification} />
            {item.importance && item.importance !== 'medium' && (
              <span className="text-[10px] uppercase tracking-wide text-lcars-muted">
                {item.importance === 'high' ? '▲ High' : '▼ Low'}
              </span>
            )}
            {item.requires_review && (
              <span className="text-[10px] uppercase tracking-wide text-command">⚑ Review</span>
            )}
            <AiBadge status={item.ai_enrichment_status} />
            <span className="ml-auto shrink-0 text-[10px] text-lcars-muted">{fmtDate(item.captured_at)}</span>
          </div>
        </div>
        <span className="shrink-0 text-xs text-lcars-muted">{expanded ? '▲' : '▼'}</span>
      </button>

      {/* ── Expanded detail + actions ── */}
      {expanded && (
        <div className="border-t border-edge px-4 pb-4 pt-3">
          {preview && (
            <p className="mb-3 whitespace-pre-wrap text-sm text-lcars-muted">{preview}</p>
          )}

          {flash && (
            <p className="mb-2 text-xs text-status">✓ {flash}</p>
          )}
          {err && (
            <p className="mb-2 text-xs text-operations">{err}</p>
          )}

          {/* Classification + Importance pickers */}
          <div className="mb-3 flex flex-wrap gap-3">
            <label className="flex flex-col gap-1 text-[10px] uppercase tracking-wide text-lcars-muted">
              Classification
              <select
                value={newClass}
                disabled={busy}
                onChange={(e) => setNewClass(e.target.value as CaptureClassification)}
                className="rounded border border-edge bg-space px-2 py-1 text-xs text-lcars-text"
              >
                <option value="reference">Note / Reference</option>
                <option value="mission">Mission</option>
                <option value="personal">Health / Personal</option>
                <option value="research">Idea / Research</option>
                <option value="decision">Decision</option>
                <option value="unclassified">Unclassified</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-[10px] uppercase tracking-wide text-lcars-muted">
              Importance
              <select
                value={newImp}
                disabled={busy}
                onChange={(e) => setNewImp(e.target.value as CaptureImportance)}
                className="rounded border border-edge bg-space px-2 py-1 text-xs text-lcars-text"
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </label>
            <div className="flex items-end">
              <button
                type="button"
                disabled={busy}
                onClick={() => act(async () => {
                  const r1 = await updateCaptureClassification(item.id, newClass);
                  if (!r1.ok) return r1;
                  return updateCaptureImportance(item.id, newImp);
                }, 'Classification updated')}
                className="rounded border border-command/50 bg-command/10 px-3 py-1 text-xs text-command hover:bg-command/20 disabled:opacity-40"
              >
                Save changes
              </button>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex flex-wrap gap-2">
            <ActionBtn
              disabled={busy}
              onClick={() => act(() => markCaptureReviewed(item.id), 'Marked reviewed')}
              tone="status"
              label="Mark reviewed"
            />
            <ActionBtn
              disabled={busy}
              onClick={() => act(() => routeCapture(item.id, 'personal'), 'Routed → Captain\'s Log')}
              tone="medical"
              label="Route as Health log"
            />
            <ActionBtn
              disabled={busy}
              onClick={() => act(() => routeCapture(item.id, 'reference'), 'Routed → Note')}
              tone="command"
              label="Route as Note"
            />
            <ActionBtn
              disabled={busy}
              onClick={() => act(() => routeCapture(item.id, 'decision'), 'Routed → Decision queue')}
              tone="operations"
              label="Route as Decision"
            />
            <ActionBtn
              disabled={busy}
              onClick={() => act(() => promoteCaptureToMission(item.id), 'Mission candidate created')}
              tone="engineering"
              label="→ Promote to Mission"
            />
            <ActionBtn
              disabled={busy}
              onClick={() => act(() => archiveCapture(item.id), 'Archived')}
              tone="muted"
              label="Archive"
            />
            <ActionBtn
              disabled={busy}
              onClick={() => act(() => dismissCapture(item.id), 'Dismissed')}
              tone="muted"
              label="Dismiss"
            />
          </div>

          {/* AI enrichment placeholder */}
          <div className="mt-3 flex items-center gap-2 rounded border border-dashed border-edge px-3 py-2">
            <span className="text-[10px] uppercase tracking-wide text-lcars-muted">AI enrichment</span>
            <span className="text-[10px] text-lcars-muted/60">— coming soon. Manual actions only for now.</span>
          </div>
        </div>
      )}
    </li>
  );
}

type BtnTone = 'status' | 'medical' | 'command' | 'operations' | 'engineering' | 'muted';
const BTN_TONE: Record<BtnTone, string> = {
  status:      'border-status/50 bg-status/10 text-status hover:bg-status/20',
  medical:     'border-medical/50 bg-medical/10 text-medical hover:bg-medical/20',
  command:     'border-command/50 bg-command/10 text-command hover:bg-command/20',
  operations:  'border-operations/50 bg-operations/10 text-operations hover:bg-operations/20',
  engineering: 'border-engineering/60 bg-engineering/15 text-engineering hover:bg-engineering/25',
  muted:       'border-edge bg-edge/20 text-lcars-muted hover:bg-edge/40',
};

function ActionBtn({
  label, onClick, disabled, tone,
}: {
  label: string;
  onClick: () => void;
  disabled: boolean;
  tone: BtnTone;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`rounded border px-3 py-1 text-xs font-medium transition-colors disabled:opacity-40 ${BTN_TONE[tone]}`}
    >
      {label}
    </button>
  );
}

// ── Inbox section ─────────────────────────────────────────────────────────────

function CaptureInbox() {
  const [activeFilter, setActiveFilter] = useState<InboxFilter>('all');
  const [items,  setItems]  = useState<InboxCapture[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,  setError]  = useState<string | null>(null);

  const load = useCallback(async (filter: InboxFilter) => {
    setLoading(true);
    setError(null);
    try {
      const opts = filterToQuery(filter);
      const rows = await fetchInboxCaptures({ ...opts, limit: 50 });
      setItems(rows);
    } catch (e) {
      setError('Could not load inbox.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(activeFilter); }, [activeFilter, load]);

  const handleRefresh = useCallback(() => load(activeFilter), [activeFilter, load]);

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted">Capture Inbox</p>
        {!loading && (
          <span className="text-[10px] text-lcars-muted">{items.length} item{items.length !== 1 ? 's' : ''}</span>
        )}
      </div>

      {/* Filter tabs */}
      <div className="flex flex-wrap gap-1.5">
        {INBOX_FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            onClick={() => setActiveFilter(f.key)}
            className={[
              'rounded border px-3 py-1 text-xs font-medium transition-colors',
              activeFilter === f.key
                ? 'border-engineering bg-engineering/15 text-engineering'
                : 'border-edge bg-space/40 text-lcars-muted hover:border-edge/80',
            ].join(' ')}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* States */}
      {loading && (
        <p className="py-4 text-center text-xs uppercase tracking-[0.2em] text-lcars-muted">Loading…</p>
      )}
      {error && !loading && (
        <p className="rounded border border-operations/40 bg-operations/10 px-4 py-3 text-sm text-operations">{error}</p>
      )}
      {!loading && !error && items.length === 0 && (
        <div className="rounded-lcars border border-edge bg-panel/30 px-4 py-8 text-center">
          <p className="text-sm text-lcars-muted">No pending captures</p>
          <p className="mt-1 text-[11px] text-lcars-muted/60">
            {activeFilter === 'all'
              ? 'All clear. Use the form above or Telegram to add a capture.'
              : `No ${activeFilter} captures pending.`}
          </p>
        </div>
      )}
      {!loading && !error && items.length > 0 && (
        <ul className="flex flex-col gap-2">
          {items.map((item) => (
            <CaptureRow key={item.id} item={item} onRefresh={handleRefresh} />
          ))}
        </ul>
      )}
    </section>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function QuickCapturePage() {
  const [text,      setText]      = useState('');
  const [type,      setType]      = useState<CaptureType>('note');
  const [showTypes, setShowTypes] = useState(false);
  const [saving,    setSaving]    = useState(false);
  const [flash,     setFlash]     = useState<string | null>(null);
  const [error,     setError]     = useState<string | null>(null);
  const [inboxKey,  setInboxKey]  = useState(0);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
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
    const meta = captureTypeMeta(type);
    setFlash(`${meta.label} captured`);
    setText('');
    setType('note');
    setShowTypes(false);
    setInboxKey((k) => k + 1);
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
    <div className="mx-auto flex max-w-[680px] flex-col gap-6">
      {/* ── Header ── */}
      <header>
        <p className="text-[10px] uppercase tracking-[0.3em] text-lcars-muted">Quick Capture</p>
        <h1 className="font-lcars text-2xl font-bold text-engineering">Capture it. Move on.</h1>
        <p className="mt-1 text-sm text-lcars-muted">
          One box. Text, voice, or Telegram — everything lands here for review.
        </p>
      </header>

      {/* ── Capture form ── */}
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
          ✓ {flash} — added to the Capture Inbox.
        </div>
      )}
      {error && (
        <div className="rounded-lcars border border-operations/50 bg-operations/10 px-4 py-3 text-sm text-operations">
          {error}
        </div>
      )}

      {type === 'health' && (
        <Link
          href="/medical/check-in"
          className="rounded-lcars border border-medical/40 bg-medical/5 px-4 py-3 text-center text-xs uppercase tracking-[0.15em] text-medical hover:border-medical/70"
        >
          Need a full check-in? Open Medical Bay →
        </Link>
      )}

      {/* ── Source legend ── */}
      <div className="flex flex-wrap gap-2">
        <p className="w-full text-[10px] uppercase tracking-[0.2em] text-lcars-muted">Sources shown in inbox</p>
        {Object.entries(SOURCE_BADGE).map(([ch, { label, tone }]) => (
          <span key={ch} className={`inline-flex rounded border px-2 py-0.5 text-[10px] uppercase tracking-wide ${TONE_TEXT[tone] ?? TONE_TEXT.command}`}>
            {label}
          </span>
        ))}
      </div>

      {/* ── Capture Inbox ── */}
      <div key={inboxKey}>
        <CaptureInbox />
      </div>
    </div>
  );
}

