'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { WorkbenchShell } from '@/components/ui';
import { PendingBriefsPanel } from '@/components/PendingBriefsPanel';
import { stateToneClasses } from '@/lib/departments';
import { useROSData } from '@/lib/useROSData';
import { useAlerts } from '@/lib/useAlerts';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { fetchCaptureAnalytics } from '@/lib/capture';
import type { AlertSeverity } from '@/lib/alerts';
import type { RecoveryPostureBand, StateTone } from '@/lib/types';

const ALERT_SEVERITY_BORDER: Record<AlertSeverity, string> = {
  critical: 'border-state-crit',
  high: 'border-state-crit',
  warning: 'border-state-warn',
};

// Executive-summary redesign (2026-08-22): Captain's Chair no longer runs a
// Mission Overview/Board — the Captain doesn't operate on missions as the
// unit of work day-to-day any more. That removal is UI-only on THIS page;
// the `missions` table itself is still live and read by ~20 other files
// (command-centre, decisions, human-systems, engineering-queue's
// mission_delivery view, the operating-model doctrine page) — nothing there
// was touched. This page is now: a situation strip (is today okay?), one
// unified "Needs Your Attention" queue pulling live counts from across the
// platform, and the two narrative cards worth keeping at exec altitude.
// Captain's Timeline, Since Last Session, Engineering Queue, Mobile
// Operating Picture, the ROS Body Context/Recovery Guidance/"Sustainable
// Load" sub-panels (the latter two were confirmed mock/fake data), and the
// insight_outcomes-backed Captain Intelligence panel are all cut from this
// page — not deleted from the app, still reachable via Quick Links or their
// own workbenches.

// ── Situation strip ──────────────────────────────────────────────────────────

const POSTURE_STATE_TONE: Record<RecoveryPostureBand, StateTone> = {
  STRONG: 'ok',
  STABLE: 'ok',
  FRAGILE: 'warn',
  REST: 'crit',
  UNKNOWN: 'unknown',
};

const RISK_STATE_TONE: Record<string, StateTone> = {
  GREEN: 'ok',
  AMBER: 'warn',
  RED: 'crit',
};

function SituationBadge({ label, value, tone, sublabel }: { label: string; value: string; tone: StateTone; sublabel?: string }) {
  const c = stateToneClasses(tone);
  return (
    <div className={`flex-1 rounded-lg border ${c.border} ${c.bg} px-4 py-3`}>
      <p className="text-[10px] uppercase tracking-wider text-wb-ink2">{label}</p>
      <p className={`mt-0.5 text-lg font-bold ${c.text}`}>{value}</p>
      {sublabel && <p className="mt-0.5 text-xs text-wb-ink/80">{sublabel}</p>}
    </div>
  );
}

interface OperationalRiskData {
  overallRisk: string | null;
  escalateCount: number;
}

function useOperationalRisk(): { data: OperationalRiskData | null; loading: boolean; error: string | null } {
  const [data, setData] = useState<OperationalRiskData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [credRes, threatRes] = await Promise.all([
          fetch('/api/intelligence-workbench/credibility'),
          fetch('/api/intelligence-workbench/threat-assessment'),
        ]);
        if (!credRes.ok) throw new Error(`Operational risk unavailable (${credRes.status})`);
        if (!threatRes.ok) throw new Error(`Threat assessment unavailable (${threatRes.status})`);
        const cred = await credRes.json();
        const threat = await threatRes.json();
        if (cancelled) return;
        const threats: { escalation?: string }[] = Array.isArray(threat.threats) ? threat.threats : [];
        setData({
          overallRisk: cred.brief?.overall_risk ?? null,
          escalateCount: threats.filter((t) => t.escalation === 'escalate').length,
        });
        setError(null);
      } catch (e) {
        console.error('[CaptainsChair] useOperationalRisk failed:', e);
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load operational risk');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  return { data, loading, error };
}

interface TodaysBriefingStats {
  confidence: number | null;
  priorities: number;
  warnings: number;
  recommendations: number;
  nextActions: number;
  interruptNow: number;
}

function useTodaysBriefing(): {
  stats: TodaysBriefingStats | null;
  loading: boolean;
  error: string | null;
} {
  const [stats, setStats] = useState<TodaysBriefingStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/captain-brief')
      .then((r) => {
        if (!r.ok) throw new Error(`Captain's brief unavailable (${r.status})`);
        return r.json();
      })
      .then((doc) => {
        if (cancelled || !doc) return;
        setStats({
          confidence: doc.confidence ?? null,
          priorities: doc.priorities?.length ?? 0,
          warnings: doc.warnings?.length ?? 0,
          recommendations: doc.recommendations?.length ?? 0,
          nextActions: doc.next_actions?.length ?? 0,
          // MSN-0339 Attention Engine "act now" bucket — fetched here since
          // MSN-0345, but never rendered anywhere on Chair until now.
          interruptNow: doc.interrupt_now?.length ?? 0,
        });
        setError(null);
      })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load briefing'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return { stats, loading, error };
}

// ── Needs Your Attention: live counts from across the platform ──────────────

interface AttentionCounts {
  contentAwaitingPublish: number | null;
  contentPriorityFlagged: number | null;
  capturePending: number | null;
  wellnessRiskFlags: number | null;
}

function useAttentionCounts(): { data: AttentionCounts; loading: boolean; errors: string[] } {
  const [data, setData] = useState<AttentionCounts>({
    contentAwaitingPublish: null,
    contentPriorityFlagged: null,
    capturePending: null,
    wellnessRiskFlags: null,
  });
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const errs: string[] = [];

      const content = await fetch('/api/content-workbench')
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
        .catch((e) => { console.error('[CaptainsChair] content pipeline count failed:', e); errs.push('Content pipeline'); return null; });

      const capture = await fetchCaptureAnalytics();
      if (capture === null) { console.error('[CaptainsChair] capture pending count failed'); errs.push('Capture pending'); }

      const wellness = await fetch('/api/human-systems?domain=recovery')
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
        .catch((e) => { console.error('[CaptainsChair] wellness risk flags failed:', e); errs.push('Wellness signals'); return null; });

      if (cancelled) return;

      const items: { status: string; captain_focus?: boolean }[] = Array.isArray(content?.items) ? content.items : [];

      setData({
        contentAwaitingPublish: content ? items.filter((i) => i.status === 'ready_to_publish').length : null,
        contentPriorityFlagged: content ? items.filter((i) => i.captain_focus).length : null,
        capturePending: capture ? capture.pending : null,
        wellnessRiskFlags: wellness ? (wellness.wellness?.risk_flags?.length ?? 0) : null,
      });
      setErrors(errs);
      setLoading(false);
    }
    load();
    return () => { cancelled = true; };
  }, []);

  return { data, loading, errors };
}

function CountTile({ label, value, href, loading }: { label: string; value: number | null; href: string; loading: boolean }) {
  const hasAction = (value ?? 0) > 0;
  return (
    <Link
      href={href}
      className={`block rounded-lg border p-3 transition-colors hover:border-wb-sage-deep/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep ${hasAction ? 'border-wb-sage-deep/40 bg-wb-sage-deep/5' : 'border-wb-line bg-white'}`}
    >
      <p className="text-[10px] uppercase tracking-wider text-wb-ink2">{label}</p>
      <p className={`mt-1 text-xl font-bold ${hasAction ? 'text-wb-sage-deep' : 'text-wb-ink'}`}>
        {loading ? '…' : value === null ? '—' : value}
      </p>
    </Link>
  );
}

// ── Captain's Notebook — quick-capture widget ────────────────────────────────

interface NbNote {
  id: string;
  title: string | null;
  raw_content: string;
  status: string;
  created_at: string;
  recommended_route: string | null;
  strategic_alignment_score: number | null;
  routed_entity_type: string | null;
  routed_to_id: string | null;
}

function NotebookCard() {
  const [readyCount, setReadyCount] = useState<number | null>(null);
  const [capturedCount, setCapturedCount] = useState<number | null>(null);
  const [topOpportunity, setTopOpportunity] = useState<NbNote | null>(null);
  const [recentRouted, setRecentRouted] = useState<NbNote[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const supabase = createSupabaseBrowserClient();
    supabase
      .from('intelligence_notes')
      .select('id, title, raw_content, status, created_at, recommended_route, strategic_alignment_score, routed_entity_type, routed_to_id')
      .in('status', ['CAPTURED', 'OFFICER_REVIEW', 'NUMBER_ONE_REVIEW', 'READY_FOR_ROUTING', 'ROUTED'])
      .order('created_at', { ascending: false })
      .limit(100)
      .then(({ data, error: fetchError }) => {
        if (cancelled) return;
        // Previously the `error` field was never checked, so a failed query
        // just fell into `if (!data) return` — readyCount/capturedCount
        // stayed null forever and the card was stuck on "Loading…"
        // indefinitely rather than showing a real error.
        if (fetchError) {
          console.error('[NotebookCard] load failed:', fetchError);
          setError(fetchError.message);
          return;
        }
        if (!data) return;
        const ready = data.filter((n) => n.status === 'READY_FOR_ROUTING');
        const captured = data.filter((n) => n.status === 'CAPTURED');
        const routed = data.filter((n) => n.status === 'ROUTED' && n.routed_to_id);

        setReadyCount(ready.length);
        setCapturedCount(captured.length);

        const top = ready.sort((a, b) =>
          (b.strategic_alignment_score ?? 0) - (a.strategic_alignment_score ?? 0)
        )[0] ?? null;
        setTopOpportunity(top as NbNote | null);
        setRecentRouted(routed.slice(0, 3) as NbNote[]);
      });
    return () => { cancelled = true; };
  }, []);

  const hasAction = (readyCount ?? 0) > 0;

  function noteTitle(n: NbNote) {
    return n.title || n.raw_content.slice(0, 48) + (n.raw_content.length > 48 ? '…' : '');
  }

  return (
    <div className={`rounded-lg border bg-white p-4 ${hasAction ? 'border-wb-sage-deep/40' : 'border-wb-line'}`}>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-wb-ink">Captain&apos;s Notebook</h3>
        <Link href="/captains-chair-workbench/notebook" className="text-[10px] uppercase tracking-[0.15em] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
          Open →
        </Link>
      </div>
      {error ? (
        <p className="text-xs text-wb-crit-on">Failed to load: {error}</p>
      ) : readyCount === null ? (
        <p className="text-xs text-wb-ink2 animate-pulse">Loading…</p>
      ) : (
        <div className="space-y-2 text-xs">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className={`h-2 w-2 shrink-0 rounded-full ${hasAction ? 'bg-wb-sage-deep animate-pulse' : 'bg-wb-border'}`} />
              <span className="text-wb-ink2">Ready for routing</span>
            </div>
            <span className={`font-mono font-semibold ${hasAction ? 'text-wb-sage-deep' : 'text-wb-ink2'}`}>{readyCount}</span>
          </div>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 shrink-0 rounded-full bg-wb-border" />
              <span className="text-wb-ink2">Pending triage</span>
            </div>
            <span className="font-mono font-semibold text-wb-ink2">{capturedCount}</span>
          </div>

          {topOpportunity && (
            <div className="mt-1 rounded border border-wb-sage-deep/20 bg-wb-sage-deep/5 px-2 py-1.5">
              <p className="mb-0.5 text-[9px] uppercase tracking-[0.2em] text-wb-sage-deep">Top opportunity</p>
              <p className="truncate text-wb-ink">{noteTitle(topOpportunity)}</p>
              {topOpportunity.recommended_route && (
                <p className="text-[10px] text-wb-ink2">→ {topOpportunity.recommended_route}</p>
              )}
            </div>
          )}

          {recentRouted.length > 0 && (
            <div className="mt-1">
              <p className="mb-1 text-[9px] uppercase tracking-[0.2em] text-wb-ink2">Recent conversions</p>
              {recentRouted.map((n) => (
                <p key={n.id} className="truncate text-[10px] text-wb-ink2/80">
                  ✓ {noteTitle(n)}{n.routed_entity_type ? ` → ${n.routed_entity_type.replace(/_/g, ' ')}` : ''}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Workbench Shell Layout ──────────────────────────────────────────────────

export default function CaptainsChairWorkbench() {
  const { posture: currentPosture, postureFetchFailed } = useROSData();
  const { alerts: liveAlerts, isLoading: alertsLoading, failedSources: alertsFailedSources, totalSources: alertsTotalSources } = useAlerts();
  const { data: opRisk, loading: opRiskLoading, error: opRiskError } = useOperationalRisk();
  const { stats: briefingStats, loading: briefingLoading, error: briefingError } = useTodaysBriefing();
  const { data: attention, loading: attentionLoading, errors: attentionErrors } = useAttentionCounts();

  const postureBand = currentPosture.posture;
  const postureTone = POSTURE_STATE_TONE[postureBand];
  const riskTone = opRisk?.overallRisk ? (RISK_STATE_TONE[opRisk.overallRisk] ?? 'unknown') : 'unknown';
  const interruptTone: StateTone = (briefingStats?.interruptNow ?? 0) > 0 ? 'crit' : 'ok';

  return (
    <WorkbenchShell
      title="Captain's Chair"
      eyebrow="Executive Summary"
      tagline="USS TJR · Captain's Chair · Executive Summary"
      back={{ href: '/workbenches', label: 'Workbenches' }}
    >
      <div className="space-y-4">
        {/* ── Situation strip ── */}
        <div className="flex flex-col gap-3 sm:flex-row">
          <SituationBadge
            label="Recovery Posture"
            value={postureFetchFailed ? 'Data error' : postureBand}
            tone={postureFetchFailed ? 'unknown' : postureTone}
            sublabel={postureFetchFailed ? 'Check connection — see console' : currentPosture.capacity_band}
          />
          <SituationBadge
            label="Operational Risk"
            value={opRiskLoading ? '…' : opRiskError ? 'Unknown' : (opRisk?.overallRisk ?? 'No data')}
            tone={opRiskError ? 'unknown' : riskTone}
            sublabel={opRisk && opRisk.escalateCount > 0 ? `${opRisk.escalateCount} threat${opRisk.escalateCount === 1 ? '' : 's'} at escalate` : undefined}
          />
          <SituationBadge
            label="Interrupt Now"
            value={briefingLoading ? '…' : briefingError ? 'Unknown' : `${briefingStats?.interruptNow ?? 0}`}
            tone={briefingError ? 'unknown' : interruptTone}
            sublabel={(briefingStats?.interruptNow ?? 0) > 0 ? 'Needs you right now' : undefined}
          />
        </div>

        {(postureBand === 'FRAGILE' || postureBand === 'REST') && !postureFetchFailed && (
          <div className={postureBand === 'REST' ? 'rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3' : 'rounded-lg border border-wb-warn/40 bg-wb-warn/10 p-3'}>
            <p className={postureBand === 'REST' ? 'text-sm text-wb-crit-on' : 'text-sm text-wb-warn-on'}>
              Recovery posture is {postureBand} — consider deferring anything below that isn&apos;t genuinely urgent.
            </p>
          </div>
        )}

        {/* ── Needs Your Attention ── */}
        <div className="rounded-lg border border-wb-line bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold text-wb-ink">Needs Your Attention</h2>

          <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <CountTile label="Content Awaiting Publish" value={attention.contentAwaitingPublish} href="/content-workbench" loading={attentionLoading} />
            <CountTile label="Capture Pending Triage" value={attention.capturePending} href="/capture-workbench" loading={attentionLoading} />
            <CountTile label="Wellness Risk Flags" value={attention.wellnessRiskFlags} href="/human-systems-workbench" loading={attentionLoading} />
          </div>
          {attentionErrors.length > 0 && (
            <p className="mb-4 text-[10px] text-wb-ink2">
              Unavailable right now: {attentionErrors.join(', ')} — see console for detail.
            </p>
          )}

          <div>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-wb-ink2">Live Alerts</h3>
              {alertsFailedSources > 0 && (
                <span className="text-[10px] text-wb-ink2">{alertsFailedSources} of {alertsTotalSources} sources unavailable</span>
              )}
            </div>
            {alertsLoading ? (
              <p className="text-xs text-wb-ink2 animate-pulse">Loading…</p>
            ) : liveAlerts.length === 0 ? (
              <p className="text-xs text-wb-ink2">No alerts.</p>
            ) : (
              <ul className="space-y-2">
                {liveAlerts.slice(0, 5).map((alert) => (
                  <li key={alert.id} className={`border-l-2 ${ALERT_SEVERITY_BORDER[alert.severity]} pl-2 text-xs`}>
                    <p className="font-semibold text-wb-ink">{alert.title}</p>
                    <p className="text-wb-ink2">{alert.detail}</p>
                  </li>
                ))}
                {liveAlerts.length > 5 && (
                  <p className="text-xs text-wb-ink2">+{liveAlerts.length - 5} more</p>
                )}
              </ul>
            )}
          </div>
        </div>
        {/* Approvals Pending (CaptainApprovalQueue) removed 2026-08-22, Captain
            directive — the manual mission-approval gate (Awaiting Captain/XO
            Approval statuses) sits permanently empty; real delivery is
            direct-to-main commits (see delivery_reconciler), not this queue.
            Component kept at components/CaptainApprovalQueue.tsx in case the
            gate is revived. */}

        {/* Pending Intelligence Briefs — renders nothing when the queue is
            genuinely empty; shows its own error state on failure. */}
        <PendingBriefsPanel />

        {/* ── Narrative cards ── */}
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border border-wb-line bg-white p-4">
            <h3 className="mb-3 text-sm font-semibold text-wb-ink">Today&apos;s Briefing</h3>
            {briefingLoading ? (
              <p className="text-xs text-wb-ink2 animate-pulse">Loading…</p>
            ) : briefingError ? (
              <p className="text-xs text-wb-crit-on">Failed to load: {briefingError}</p>
            ) : (
              <div className="space-y-2 text-xs">
                <div className="flex justify-between">
                  <span className="text-wb-ink2">Confidence</span>
                  <span className="font-semibold text-wb-ink">{briefingStats?.confidence != null ? `${briefingStats.confidence}%` : '—'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-wb-ink2">Priorities</span>
                  <span className="font-semibold text-wb-ink">{briefingStats?.priorities ?? 0}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-wb-ink2">Warnings</span>
                  <span className="font-semibold text-wb-ink">{briefingStats?.warnings ?? 0}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-wb-ink2">Recommendations</span>
                  <span className="font-semibold text-wb-ink">{briefingStats?.recommendations ?? 0}</span>
                </div>
                <Link href="/captains-brief-workbench" className="mt-1 inline-block text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
                  Full Brief →
                </Link>
              </div>
            )}
          </div>

          <NotebookCard />
        </div>
      </div>
    </WorkbenchShell>
  );
}
