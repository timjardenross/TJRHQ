'use client';

// Phase C — capture badges. Ported from the legacy Capture page. Per Captain
// decision 2026-07-12, classification is shown by glyph + text on neutral
// wb-ink2 chips (no six-way colour scale); AI/status use the wb- status hues.

import { SOURCE_BADGE } from '@/lib/capture';

export interface ParsedSummary {
  suggested_classification?: string;
  ai_confidence?: number;
  ai_reasoning?: string;
  ai_enrichment_status?: string;
  enriched_at?: string;
  capture_origin?: string;
  duration_s?: number;
  transcription_model?: string;
  confidence?: number;
  [key: string]: unknown;
}

export function parseSummary(raw: Record<string, unknown> | string | null | undefined): ParsedSummary | null {
  if (!raw) return null;
  if (typeof raw === 'string') {
    try { return JSON.parse(raw) as ParsedSummary; } catch { return null; }
  }
  return raw as ParsedSummary;
}

export function fmtDate(iso: string) {
  return new Date(iso).toLocaleString('en-AU', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false,
  });
}

const CHIP = 'inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] uppercase tracking-wide';

export function SourceBadge({ channelId }: { channelId: string | null | undefined }) {
  const label = channelId && SOURCE_BADGE[channelId] ? SOURCE_BADGE[channelId].label : 'Unknown';
  const isVoice = channelId === 'telegram-xo-voice-capture';
  return (
    <span className={`${CHIP} border-wb-line font-semibold text-wb-ink2`}>
      {isVoice && <span aria-hidden>🎙</span>}
      {label}
    </span>
  );
}

const CLASS_GLYPH: Record<string, string> = {
  mission: '★', personal: '✚', research: '✦', decision: '⚖', reference: '✎', unclassified: '○',
};
const CLASS_LABEL: Record<string, string> = {
  mission: 'Mission', personal: 'Health', research: 'Idea/Research',
  decision: 'Decision', reference: 'Note', unclassified: 'Unclassified',
};

export function ClassBadge({ classification }: { classification: string | null | undefined }) {
  if (!classification) return null;
  return (
    <span className={`${CHIP} border-wb-line font-semibold text-wb-ink2`}>
      <span aria-hidden>{CLASS_GLYPH[classification] ?? '○'}</span>
      {CLASS_LABEL[classification] ?? classification}
    </span>
  );
}

export function AiBadge({ status, summary }: { status: string | null | undefined; summary?: ParsedSummary | null }) {
  const s = status ?? 'not_enriched';
  const map: Record<string, { label: string; cls: string }> = {
    not_enriched: { label: 'Not enriched', cls: 'border-wb-line text-wb-ink2' },
    queued:       { label: 'Enrichment queued', cls: 'border-wb-sage-deep/40 bg-wb-sage-deep/10 text-wb-sage-deep' },
    enriched:     { label: 'Enriched', cls: 'border-wb-ok/40 bg-wb-ok/10 text-wb-ok-on' },
    failed:       { label: 'Enrichment failed', cls: 'border-wb-crit/40 bg-wb-crit/10 text-wb-crit-on' },
  };
  const { label, cls } = map[s] ?? map.not_enriched;
  const confPct = s === 'enriched' && summary?.ai_confidence != null
    ? ` ${Math.round(Number(summary.ai_confidence) * 100)}%`
    : '';
  return (
    <span className={`${CHIP} ${cls}`}>
      ✦ {s === 'enriched' ? `AI ✓${confPct}` : label}
    </span>
  );
}

export function VoiceMeta({ summary }: { summary: Record<string, unknown> | null }) {
  if (!summary) return null;
  if (summary.capture_origin !== 'telegram_voice') return null;
  const dur = summary.duration_s as number | undefined;
  const model = summary.transcription_model as string | undefined;
  const conf = summary.confidence as number | undefined;
  return (
    <div className="mt-1 flex flex-wrap gap-2 text-[10px] text-wb-ink2">
      {dur !== undefined && <span>⏱ {dur.toFixed(1)}s</span>}
      {model && <span>Model: {model}</span>}
      {conf !== undefined && <span>Conf: {(conf * 100).toFixed(0)}%</span>}
    </div>
  );
}

export function AiSuggestion({
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
  const barColour = conf == null ? 'bg-wb-line' : conf >= 0.85 ? 'bg-wb-ok' : conf >= 0.6 ? 'bg-wb-warn' : 'bg-wb-line';

  return (
    <div className="mb-3 rounded-md border border-wb-sage-deep/40 bg-wb-sage-deep/5 px-3 py-3">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-wb-sage-deep">✦ AI Suggestion</span>
        {confPct != null && <span className="text-[10px] text-wb-ink2">{confPct}% confidence</span>}
      </div>
      {conf != null && (
        <div className="mb-2 h-1 w-full overflow-hidden rounded bg-wb-line">
          <div className={`h-full rounded transition-all ${barColour}`} style={{ width: `${Math.round(conf * 100)}%` }} />
        </div>
      )}
      <div className="mb-1 flex items-center gap-2">
        <span className="text-[10px] text-wb-ink2">Classification:</span>
        <ClassBadge classification={cls} />
      </div>
      {summary.ai_reasoning && <p className="mb-3 text-[11px] italic text-wb-ink2">{summary.ai_reasoning}</p>}
      <div className="flex items-center gap-3">
        <button type="button" onClick={() => onAccept(cls)}
          className="rounded-md bg-wb-sage-deep px-3 py-1 text-xs font-semibold text-white hover:opacity-80">
          Accept suggestion
        </button>
        <button type="button" onClick={onDismiss} className="text-xs text-wb-ink2 hover:text-wb-ink">Dismiss</button>
      </div>
    </div>
  );
}
