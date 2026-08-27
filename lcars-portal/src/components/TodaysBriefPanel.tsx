'use client';

// Today's Brief — the executive-summary card the retired Pending
// Intelligence Briefs panel left a gap for (2026-08-22, Captain's direct
// request: "some form of executive view being brought from briefs into my
// captains chair").
//
// 2026-08-23: originally wired to /api/briefs (intelligence_briefs — the
// ORI cybersecurity/geopolitical resilience-brief archive, a separate
// feature). That pipeline runs fortnightly (intelligence/scheduler.py's
// or_intelligence_brief job) plus on-demand, not daily, so this card
// showed "no brief today" on almost every day regardless of whether the
// Captain's actual daily brief had generated — which it reliably does,
// every morning at 07:00 AEST via captains_brief.py, into
// captains_daily_briefs, a table nothing in the UI read. Repointed to
// /api/captains-daily-brief (that table) so this card shows what its own
// name says: today's real daily brief.
//
// captains_daily_briefs has no approval workflow — it's a plain,
// append-only log of every generated brief (migration 0033/0050) — so
// there's no publish-gate to check here, just "does today have a row."

import { useEffect, useState } from 'react';
import { WorkbenchPanel } from './WorkbenchPanel';

interface Brief {
  id: string;
  brief_type: 'morning' | 'midday' | 'eod' | 'weekly';
  brief_date: string;
  generated_at: string;
  brief_text: string;
  signals_count: number | null;
}

const BRIEF_TYPE_LABEL: Record<Brief['brief_type'], string> = {
  morning: 'Morning',
  midday: 'Midday',
  eod: 'End of Day',
  weekly: 'Weekly',
};

// brief_text is Telegram HTML (captains_brief.py builds it for direct
// bot delivery, e.g. "<b>☀️ MORNING BRIEF ...</b>") — stripped rather
// than rendered, so this card never dangerouslySetInnerHTML's bot-
// generated markup.
function stripHtml(text: string): string {
  return text.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
}

function isToday(dateStr: string): boolean {
  const d = new Date(dateStr);
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

export function TodaysBriefPanel() {
  const [brief, setBrief] = useState<Brief | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/captains-daily-brief')
      .then((r) => {
        if (!r.ok) throw new Error(`briefs unavailable (${r.status})`);
        return r.json();
      })
      .then((d) => {
        const briefs: Brief[] = d?.briefs ?? [];
        // Most-recent-first from the API; first one generated today is
        // the latest applicable brief (morning gets superseded by eod).
        const today = briefs.find((b) => isToday(b.generated_at));
        setBrief(today ?? null);
        setError(null);
      })
      .catch((e) => {
        console.error('[TodaysBriefPanel] load failed:', e);
        setError(e instanceof Error ? e.message : 'Failed to load');
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <WorkbenchPanel title="Executive Brief" eyebrow="Today's Captain's Brief">
      {loading ? (
        <p className="text-sm text-wb-ink2 animate-pulse">Loading…</p>
      ) : error ? (
        <p className="text-sm text-wb-crit-on">Failed to load today&apos;s brief: {error}</p>
      ) : !brief ? (
        <p className="text-sm text-wb-ink2">
          No brief generated yet today — the daily job runs at 07:00 AEST, or trigger one on
          demand via the XO bot&apos;s /brief command.
        </p>
      ) : (
        <div className="rounded-lg border border-wb-line/60 bg-wb-bg/60 p-3 text-sm">
          <div className="mb-1.5 flex items-center gap-2">
            <span className="rounded bg-wb-bg px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-wb-ink2">
              {BRIEF_TYPE_LABEL[brief.brief_type]}
            </span>
            <span className="text-[10px] uppercase tracking-wider text-wb-ink2">
              {new Date(brief.generated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>
          <p className="text-wb-ink whitespace-pre-wrap">{stripHtml(brief.brief_text)}</p>
        </div>
      )}
    </WorkbenchPanel>
  );
}
