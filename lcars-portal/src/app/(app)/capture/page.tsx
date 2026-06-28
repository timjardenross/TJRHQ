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
  fetchCaptureAnalytics,
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
  type CaptureAnalytics,
} from '@/lib/capture';
import { DEPARTMENTS } from '@/lib/departments';

// ── Types ─────────────────────────────────────────────────────────────────────

interface ParsedSummary {
  suggested_classification?: string;
  ai_confidence?: number;
  ai_reasoning?: string;
  ai_enrichment_status?: string;
  enriched_at?: string;
  // voice metadata fields (also present in summary)
  capture_origin?: string;
  duration_s?: number;
  transcription_model?: string;
  confidence?: number;
  [key: string]: unknown;
}

function parseSummary(raw: Record<string, unknown> | string | null | undefined): ParsedSummary | null {
  if (!raw) return null;
  if (typeof raw === 'string') {
    try { return JSON.parse(raw) as ParsedSummary; } catch { return null; }
  }
  return raw as ParsedSummary;
}

// ── Small utilities ───────────────────────────────────────────────────────────

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString('en-AU', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false,
  });
}

// ── Source badge chip ─────────────────────────────────────────────────────────

const TONE_TEXT: Record<string, string> = {
  engineering: 'text-engineering-on border-engineering/50 bg-engineering/10',
  science:     'text-science-on border-science/50 bg-science/10',
  command:     'text-command-on border-command/50 bg-command/10',
  operations:  'text-operations-on border-operations/50 bg-operations/10',
  medical:     'text-medical-on border-medical/50 bg-medical/10',
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
    mission:       'text-engineering-on border-engineering/40 bg-engineering/10',
    personal:      'text-medical-on border-medical/40 bg-medical/10',
    research:      'text-science-on border-science/40 bg-science/10',
    decision:      'text-operations-on border-operations/40 bg-operations/10',
    reference:     'text-command-on border-command/40 bg-command/10',
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

function AiBadge({ status, summary }: { status: string | null | undefined; summary?: ParsedSummary | null }) {
  const s = status ?? 'not_enriched';
  const map: Record<string, { label: string; cls: string }> = {
    not_enriched: { label: 'Not enriched',       cls: 'text-lcars-muted border-edge bg-transparent' },
    queued:       { label: 'Enrichment queued',  cls: 'text-command-on border-command/40 bg-command/10' },
    enriched:     { label: 'Enriched',           cls: 'text-status-on border-status/40 bg-status/10' },
    failed:       { label: 'Enrichment failed',  cls: 'text-operations-on border-operations/40 bg-operations/10' },
  };
  const { label, cls } = map[s] ?? map.not_enriched;
  const confPct = s === 'enriched' && summary?.ai_confidence != null
    ? ` ${Math.round(Number(summary.ai_confidence) * 100)}%`
    : '';
  return (
    <span className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${cls}`}>
      ✦ {s === 'enriched' ? `AI ✓${confPct}` : label}
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

// ── AI suggestion panel ───────────────────────────────────────────────────────

function AiSuggestion({
  summary,
  onAccept,
  onDismiss,
}: {
  summary: ParsedSummary | null;
  onAccept: (cls: string) => void;
  onDismiss: () => void;
}) {
  if (!summary?.suggested_classification) return null;
  if (summary.ai_enrichment_status !== 'enriched') return null;

  const cls = summary.suggested_classification;
  const conf = summary.ai_confidence != null ? Number(summary.ai_confidence) : null;
  const confPct = conf != null ? Math.round(conf * 100) : null;
  const barColour =
    conf == null ? 'bg-edge'
    : conf >= 0.85 ? 'bg-science'
    : conf >= 0.6  ? 'bg-operations'
    : 'bg-edge';

  return (
    <div className="mb-3 rounded-lcars border border-science/40 bg-science/5 px-3 py-3">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-science-on">✦ AI Suggestion</span>
        {confPct != null && (
          <span className="text-[10px] text-lcars-muted">{confPct}% confidence</span>
        )}
      </div>

      {/* Confidence bar */}
      {conf != null && (
        <div className="mb-2 h-1 w-full overflow-hidden rounded bg-edge/40">
          <div
            className={`h-full rounded transition-all ${barColour}`}
            style={{ width: `${Math.round(conf * 100)}%` }}
          />
        </div>
      )}

      <div className="mb-1 flex items-center gap-2">
        <span className="text-[10px] text-lcars-muted">Classification:</span>
        <ClassBadge classification={cls} />
      </div>

      {summary.ai_reasoning && (
        <p className="mb-3 text-[11px] italic text-lcars-muted/80">{summary.ai_reasoning}</p>
      )}

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => onAccept(cls)}
          className="rounded-lcars bg-science px-3 py-1 text-xs font-semibold text-white hover:opacity-80"
        >
          Accept suggestion
        </button>
        <button
          type="button"
          onClick={onDismiss}
          className="text-xs text-lcars-muted hover:text-lcars-text"
        >
          Dismiss
        </button>
      </div>
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
  | 'routed'
  | 'portal'
  | 'telegram-voice'
  | 'mission'
  | 'health'
  | 'research'
  | 'decision'
  | 'unclassified';

const INBOX_FILTERS: { key: InboxFilter; label: string }[] = [
  { key: 'all',            label: 'Pending' },
  { key: 'routed',         label: 'Routed / Done' },
  { key: 'telegram-voice', label: 'Voice' },
  { key: 'mission',        label: 'Mission' },
  { key: 'health',         label: 'Health' },
  { key: 'research',       label: 'Idea/Research' },
  { key: 'decision',       label: 'Decision' },
  { key: 'unclassified',   label: 'Unclassified' },
];

const ROUTE_DEST: Record<string, { label: string; href: string }> = {
  personal:  { label: 'Captain\'s Log', href: '/captains-log' },
  reference: { label: 'Knowledge Hub',  href: '/knowledge' },
  decision:  { label: 'Decisions',      href: '/knowledge?tab=decisions' },
  mission:   { label: 'Missions',       href: '/missions' },
  research:  { label: 'Knowledge Hub',  href: '/knowledge' },
};

function filterToQuery(f: InboxFilter): {
  source?: string;
  classification?: CaptureClassification;
  statusFilter?: 'pending' | 'routed';
} {
  if (f === 'routed')         return { statusFilter: 'routed' };
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
  const [expanded,            setExpanded]            = useState(false);
  const [showFullContent,     setShowFullContent]     = useState(false);
  const [busy,                setBusy]                = useState(false);
  const [flash,               setFlash]               = useState<string | null>(null);
  const [routedDest,          setRoutedDest]          = useState<{ label: string; href: string } | null>(null);
  const [err,                 setErr]                 = useState<string | null>(null);
  const [newClass,            setNewClass]            = useState<CaptureClassification>(item.classification ?? 'unclassified');
  const [newImp,              setNewImp]              = useState<CaptureImportance>(item.importance ?? 'medium');
  const [suggestionDismissed, setSuggestionDismissed] = useState(false);

  const parsedSummary = parseSummary(item.summary as Record<string, unknown> | string | null);

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

  const fullContent = item.raw_text ?? item.title ?? '';
  const preview = showFullContent ? fullContent : fullContent.slice(0, 300);
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
          {isVoice && parsedSummary && (
            <VoiceMeta summary={parsedSummary} />
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
              <span className="text-[10px] uppercase tracking-wide text-command-on">⚑ Review</span>
            )}
            <AiBadge status={item.ai_enrichment_status} summary={parsedSummary} />
            <span className="ml-auto shrink-0 text-[10px] text-lcars-muted">{fmtDate(item.captured_at)}</span>
          </div>
        </div>
        <span className="shrink-0 text-xs text-lcars-muted">{expanded ? '▲' : '▼'}</span>
      </button>

      {/* ── Expanded detail + actions ── */}
      {expanded && (
        <div className="border-t border-edge px-4 pb-4 pt-3">
          {fullContent && (
            <div className="mb-3">
              <p className="whitespace-pre-wrap text-sm text-lcars-muted leading-relaxed">{preview}</p>
              {fullContent.length > 300 && (
                <button type="button" onClick={() => setShowFullContent((v) => !v)}
                  className="mt-1 text-[10px] uppercase tracking-wider text-science-on hover:text-science-on/70 transition-colors">
                  {showFullContent ? '▲ Show less' : `▼ Show full content (${fullContent.length} chars)`}
                </button>
              )}
            </div>
          )}

          {flash && (
            <div className="mb-2">
              <p className="text-xs text-status-on">✓ {flash}</p>
              {routedDest && (
                <Link href={routedDest.href}
                  className="mt-1 inline-block text-[10px] uppercase tracking-wider text-science-on hover:text-science-on/70 transition-colors">
                  View in {routedDest.label} →
                </Link>
              )}
            </div>
          )}
          {err && (
            <p className="mb-2 text-xs text-operations-on">{err}</p>
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
                className="rounded border border-command/50 bg-command/10 px-3 py-1 text-xs text-command-on hover:bg-command/20 disabled:opacity-40"
              >
                Save changes
              </button>
            </div>
          </div>

          {/* AI enrichment — suggestion if pending, analysis summary if already actioned */}
          {expanded && item.ai_enrichment_status === 'enriched' && !suggestionDismissed && (
            <AiSuggestion
              summary={parsedSummary}
              onAccept={(cls) => {
                setRoutedDest(ROUTE_DEST[cls] ?? null);
                act(async () => {
                  const r1 = await updateCaptureClassification(item.id, cls as CaptureClassification);
                  if (!r1.ok) return r1;
                  return markCaptureReviewed(item.id);
                }, `AI suggestion accepted — ${cls}`);
              }}
              onDismiss={() => setSuggestionDismissed(true)}
            />
          )}
          {expanded && item.ai_enrichment_status === 'enriched' && suggestionDismissed && parsedSummary?.ai_reasoning && (
            <div className="mb-3 rounded border border-edge/50 bg-panel/30 px-3 py-2">
              <p className="mb-1 text-[10px] uppercase tracking-wide text-lcars-muted">✦ AI Analysis</p>
              <p className="text-[11px] text-lcars-muted/80 italic">{parsedSummary.ai_reasoning}</p>
            </div>
          )}

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
              onClick={() => { setRoutedDest(ROUTE_DEST.personal); act(() => routeCapture(item.id, 'personal'), 'Routed → Captain\'s Log'); }}
              tone="medical"
              label="Route as Health log"
            />
            <ActionBtn
              disabled={busy}
              onClick={() => { setRoutedDest(ROUTE_DEST.reference); act(() => routeCapture(item.id, 'reference'), 'Routed → Note'); }}
              tone="command"
              label="Route as Note"
            />
            <ActionBtn
              disabled={busy}
              onClick={() => { setRoutedDest(ROUTE_DEST.decision); act(() => routeCapture(item.id, 'decision'), 'Routed → Decision queue'); }}
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

          {/* AI enrichment trigger — only shown when not yet enriched */}
          {item.ai_enrichment_status !== 'enriched' && (
            <div className="mt-3 flex items-center gap-2 rounded border border-dashed border-edge px-3 py-2">
              <span className="text-[10px] uppercase tracking-wide text-lcars-muted">AI enrichment</span>
              <button
                type="button"
                disabled={busy || item.ai_enrichment_status === 'queued'}
                onClick={() => act(async () => {
                  const resp = await fetch(`/api/capture/${item.id}/route?action=enrich`, { method: 'POST' });
                  const json = await resp.json();
                  return resp.ok ? { ok: true } : { ok: false, error: json?.error };
                }, 'Enrichment queued')}
                className="rounded border border-science/40 bg-science/10 px-2 py-0.5 text-[10px] text-science-on hover:bg-science/20 disabled:opacity-40"
              >
                {item.ai_enrichment_status === 'queued' ? 'Queued…' : '✦ Enrich with AI'}
              </button>
              <span className="text-[10px] text-lcars-muted/50">Suggests classification + route</span>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

type BtnTone = 'status' | 'medical' | 'command' | 'operations' | 'engineering' | 'muted';
const BTN_TONE: Record<BtnTone, string> = {
  status:      'border-status/50 bg-status/10 text-status-on hover:bg-status/20',
  medical:     'border-medical/50 bg-medical/10 text-medical-on hover:bg-medical/20',
  command:     'border-command/50 bg-command/10 text-command-on hover:bg-command/20',
  operations:  'border-operations/50 bg-operations/10 text-operations-on hover:bg-operations/20',
  engineering: 'border-engineering/60 bg-engineering/15 text-engineering-on hover:bg-engineering/25',
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

// ── Analytics panel ───────────────────────────────────────────────────────────

const CLASS_LABELS: Record<string, string> = {
  mission: 'Mission', personal: 'Health', research: 'Idea', decision: 'Decision',
  reference: 'Note', unclassified: 'Unclassified',
};

// Maps source channel key → InboxFilter key
const SOURCE_TO_FILTER: Record<string, InboxFilter> = {
  'lcars-mobile-quick-capture': 'portal',
  'telegram-xo-voice-capture':  'telegram-voice',
};

// Maps classification key → InboxFilter key
const CLASS_TO_FILTER: Record<string, InboxFilter> = {
  mission:       'mission',
  personal:      'health',
  research:      'research',
  decision:      'decision',
  unclassified:  'unclassified',
};

function CaptureAnalyticsPanel({ onFilter }: { onFilter: (f: InboxFilter) => void }) {
  const [stats, setStats] = useState<CaptureAnalytics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchCaptureAnalytics().then(s => { setStats(s); setLoading(false); });
  }, []);

  if (loading) return (
    <div className="rounded-lcars border border-edge bg-panel/30 px-4 py-3">
      <p className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">Capture Analytics</p>
      <p className="mt-2 text-xs text-lcars-muted/60">Loading…</p>
    </div>
  );

  if (!stats) return null;

  const topSources = Object.entries(stats.by_source)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);
  const topClasses = Object.entries(stats.by_classification)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6);

  return (
    <div className="rounded-lcars border border-edge bg-panel/30 px-4 py-3">
      <p className="mb-3 text-[10px] uppercase tracking-[0.2em] text-lcars-muted">Capture Analytics — 7 days</p>
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Today"     value={stats.today}    tone="engineering" />
        <Stat label="This week" value={stats.this_week} tone="command" />
        <Stat
          label="Pending"
          value={stats.pending}
          tone={stats.pending > 0 ? 'operations' : 'status'}
          onClick={() => onFilter('all')}
        />
      </div>
      {topSources.length > 0 && (
        <div className="mt-3">
          <p className="mb-1.5 text-[9px] uppercase tracking-[0.2em] text-lcars-muted/70">By source</p>
          <div className="flex flex-wrap gap-2">
            {topSources.map(([ch, n]) => {
              const filter = SOURCE_TO_FILTER[ch];
              return (
                <button
                  key={ch}
                  type="button"
                  onClick={() => filter && onFilter(filter)}
                  className={[
                    'flex items-center gap-1 text-[10px] transition-opacity',
                    filter ? 'cursor-pointer text-lcars-muted hover:text-lcars-text hover:opacity-80' : 'cursor-default text-lcars-muted',
                  ].join(' ')}
                >
                  <span className="font-semibold text-lcars-text">{n}</span>
                  {SOURCE_BADGE[ch]?.label ?? ch}
                </button>
              );
            })}
          </div>
        </div>
      )}
      {topClasses.length > 0 && (
        <div className="mt-2">
          <p className="mb-1.5 text-[9px] uppercase tracking-[0.2em] text-lcars-muted/70">By classification</p>
          <div className="flex flex-wrap gap-2">
            {topClasses.map(([cl, n]) => {
              const filter = CLASS_TO_FILTER[cl];
              return (
                <button
                  key={cl}
                  type="button"
                  onClick={() => filter && onFilter(filter)}
                  className={[
                    'flex items-center gap-1 text-[10px] transition-opacity',
                    filter ? 'cursor-pointer text-lcars-muted hover:text-lcars-text hover:opacity-80' : 'cursor-default text-lcars-muted',
                  ].join(' ')}
                >
                  <span className="font-semibold text-lcars-text">{n}</span>
                  {CLASS_LABELS[cl] ?? cl}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, tone, onClick }: { label: string; value: number; tone: string; onClick?: () => void }) {
  const textMap: Record<string, string> = {
    engineering: 'text-engineering-on', command: 'text-command-on',
    operations: 'text-operations-on', status: 'text-status-on',
  };
  return (
    <div
      className={`flex flex-col ${onClick ? 'cursor-pointer hover:opacity-75 transition-opacity' : ''}`}
      onClick={onClick}
    >
      <span className={`text-xl font-bold ${textMap[tone] ?? 'text-lcars-text'}`}>{value}</span>
      <span className="text-[10px] uppercase tracking-wide text-lcars-muted">{label}{onClick ? ' ↓' : ''}</span>
    </div>
  );
}

// ── Inbox section ─────────────────────────────────────────────────────────────

function CaptureInbox({
  activeFilter,
  onFilterChange,
}: {
  activeFilter: InboxFilter;
  onFilterChange: (f: InboxFilter) => void;
}) {
  const [items,  setItems]  = useState<InboxCapture[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,  setError]  = useState<string | null>(null);

  const load = useCallback(async (filter: InboxFilter) => {
    setLoading(true);
    setError(null);
    try {
      const opts = filterToQuery(filter);
      const rows = await fetchInboxCaptures({ ...opts, limit: 100 });
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
            onClick={() => onFilterChange(f.key)}
            className={[
              'rounded border px-3 py-1 text-xs font-medium transition-colors',
              activeFilter === f.key
                ? 'border-engineering bg-engineering/15 text-engineering-on'
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
        <p className="rounded border border-operations/40 bg-operations/10 px-4 py-3 text-sm text-operations-on">{error}</p>
      )}
      {!loading && !error && items.length === 0 && (
        <div className="rounded-lcars border border-edge bg-panel/30 px-4 py-8 text-center">
          <p className="text-sm text-lcars-muted">{activeFilter === 'routed' ? 'No routed captures' : 'No pending captures'}</p>
          <p className="mt-1 text-[11px] text-lcars-muted/60">
            {activeFilter === 'all'
              ? 'All clear. Use the form above or Telegram to add a capture.'
              : activeFilter === 'routed'
              ? 'Items appear here after you route or review them.'
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
  const [text,         setText]        = useState('');
  const [type,         setType]        = useState<CaptureType>('note');
  const [showTypes,    setShowTypes]   = useState(false);
  const [saving,       setSaving]      = useState(false);
  const [flash,        setFlash]       = useState<string | null>(null);
  const [error,        setError]       = useState<string | null>(null);
  const [inboxKey,     setInboxKey]    = useState(0);
  const [inboxFilter,  setInboxFilter] = useState<InboxFilter>('all');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const inboxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  function applyFilter(f: InboxFilter) {
    setInboxFilter(f);
    setTimeout(() => inboxRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
  }

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
        <h1 className="font-lcars text-2xl font-bold text-engineering-on">Capture it. Move on.</h1>
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
              className="self-start text-xs uppercase tracking-[0.15em] text-lcars-muted hover:text-engineering-on"
            >
              Type: <span className="text-engineering-on">{meta.label}</span> · change ▾
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
            className="w-full rounded-lcars bg-engineering px-4 py-3 font-lcars text-base font-bold uppercase tracking-[0.2em] text-white transition-opacity hover:opacity-80 disabled:opacity-40"
          >
            {saving ? 'Capturing…' : `Capture ${meta.label}`}
          </button>
          <p className="text-center text-[10px] uppercase tracking-[0.15em] text-lcars-muted">
            ⌘/Ctrl + Enter to capture
          </p>
        </div>
      </div>

      {flash && (
        <div className="rounded-lcars border border-status/50 bg-status/10 px-4 py-3 text-sm font-semibold text-status-on">
          ✓ {flash} — added to the Capture Inbox.
        </div>
      )}
      {error && (
        <div className="rounded-lcars border border-operations/50 bg-operations/10 px-4 py-3 text-sm text-operations-on">
          {error}
        </div>
      )}

      {type === 'health' && (
        <Link
          href="/medical/check-in"
          className="rounded-lcars border border-medical/40 bg-medical/5 px-4 py-3 text-center text-xs uppercase tracking-[0.15em] text-medical-on hover:border-medical/70"
        >
          Need a full check-in? Open Medical Bay →
        </Link>
      )}

      {/* ── Analytics ── */}
      <CaptureAnalyticsPanel onFilter={applyFilter} />

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
      <div key={inboxKey} ref={inboxRef}>
        <CaptureInbox activeFilter={inboxFilter} onFilterChange={setInboxFilter} />
      </div>
    </div>
  );
}

