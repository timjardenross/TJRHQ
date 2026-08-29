'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { WorkbenchShell } from '@/components/ui';
import { TodaysBriefPanel } from '@/components/TodaysBriefPanel';
import { stateToneClasses } from '@/lib/departments';
import { useROSData } from '@/lib/useROSData';
import { useAlerts } from '@/lib/useAlerts';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { fetchCaptureAnalytics, fetchInboxCaptures } from '@/lib/capture';
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
// (decisions, human-systems, engineering-queue's mission_delivery view, the
// operating-model doctrine page) — nothing there was touched. This page is
// now: a situation strip (is today okay?), one unified "Needs Your
// Attention" queue pulling live counts from across the platform, and the
// two narrative cards worth keeping at exec altitude. Captain's Timeline,
// Since Last Session, Engineering Queue, the ROS Body Context/Recovery
// Guidance/"Sustainable Load" sub-panels (the latter two were confirmed
// mock/fake data), and the insight_outcomes-backed Captain Intelligence
// panel are all cut from this page — not deleted from the app, still
// reachable via their own workbenches.
//
// Mobile Operating Picture (the command-centre-backed Recommended
// Action/Ship Status/What Changed/Officer Activity panels) is the
// exception to that: it was cut here with no real alternate path back
// (docs/UI-Layer-Debt-Handoff-2026-08-29.md Finding 2) — this comment
// previously claimed it was "still reachable via Quick Links," which was
// never true in the actual code. Retired outright 2026-08-29 rather than
// leaving it half-wired: command-centre.ts, useCommandCentre.ts, and the
// MobileOperatingPicture/CommandStrip/ExecutiveSummary components are
// deleted. If this feature is wanted back, it needs re-wiring into a live
// page from scratch, not un-deleting orphaned code.

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

// Signal Snapshot's own small local maps (2026-08-22) — matching
// capacity_checkins.capacity_state's green/orange/red vocabulary and
// health_signals' severity vocabulary (see human-systems-workbench/
// _components/types.ts's CAPACITY_STATE_LABEL/capacityStateStatus and
// health-osint's threat-assessment/route.ts's SEVERITY_IMPACT for the
// canonical versions) — defined locally rather than imported, matching
// how this file already keeps its own POSTURE_STATE_TONE/RISK_STATE_TONE
// rather than reaching into another workbench's _components.
const CAPACITY_STATE_LABEL: Record<string, string> = {
  green: 'Sustainable',
  orange: 'Stretched',
  red: 'Depleted',
};

const CAPACITY_STATE_TONE: Record<string, StateTone> = {
  green: 'ok',
  orange: 'warn',
  red: 'crit',
};

const HEALTH_SEVERITY_TONE: Record<string, StateTone> = {
  critical: 'crit',
  severe: 'warn',
};

function SituationBadge({ label, value, tone, sublabel, href }: { label: string; value: string; tone: StateTone; sublabel?: string; href?: string }) {
  const c = stateToneClasses(tone);
  const content = (
    <>
      <p className="text-[10px] uppercase tracking-wider text-wb-ink2">{label}</p>
      <p className={`mt-0.5 text-lg font-bold ${c.text}`}>{value}</p>
      {sublabel && <p className="mt-0.5 text-xs text-wb-ink/80">{sublabel}</p>}
    </>
  );
  const className = `flex-1 rounded-lg border ${c.border} ${c.bg} px-4 py-3`;
  if (href) {
    return (
      <Link href={href} className={`${className} block transition-colors hover:border-wb-sage-deep/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep`}>
        {content}
      </Link>
    );
  }
  return <div className={className}>{content}</div>;
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

// 2026-08-29 council follow-up ("fresh look, further holes"): Emergency
// Alert Hub had zero presence on this page despite being Australia-wide
// bushfire/flood/storm data with its own hourly digest — every advisor
// independently flagged this as the single highest-value gap, since
// "nothing to show" and "you didn't check" look identical here and the
// cost of missing it is physical, unlike every other card on this page.
// Same curated worst-item pattern as Signal Snapshot: worst active alert
// tier + one headline, "Clear" otherwise.
interface EmergencyAlertsSummary {
  worstTier: 'emergency_warning' | 'watch_and_act' | null;
  count: number;
  worstHeadline: string | null;
}

function useEmergencyAlerts(): { data: EmergencyAlertsSummary | null; loading: boolean; error: string | null } {
  const [data, setData] = useState<EmergencyAlertsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch('/api/emergency-alerts?activeOnly=true');
        if (!res.ok) throw new Error(`Emergency alerts unavailable (${res.status})`);
        const body = await res.json();
        if (cancelled) return;
        const alerts: { severity: string; headline: string }[] = Array.isArray(body?.alerts) ? body.alerts : [];
        // Only the two genuinely urgent tiers count here (matches
        // intelligence/emergency_alert_summary.py's own urgent-tier
        // definition) — Advice/unclassified churn is deliberately not
        // surfaced on an exec-altitude page, same reasoning that page
        // already applies to its own hourly-digest suppression.
        const urgent = alerts.filter((a) => a.severity === 'emergency_warning' || a.severity === 'watch_and_act');
        const worst = urgent.find((a) => a.severity === 'emergency_warning') ?? urgent[0] ?? null;
        setData({
          worstTier: (worst?.severity as EmergencyAlertsSummary['worstTier']) ?? null,
          count: urgent.length,
          worstHeadline: worst?.headline ?? null,
        });
        setError(null);
      } catch (e) {
        console.error('[CaptainsChair] useEmergencyAlerts failed:', e);
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load emergency alerts');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  return { data, loading, error };
}

// Same council follow-up: Agent & Job Status deserves a slot on different
// grounds than a content signal — it's infrastructure trust, a
// meta-warning that answers "can I trust the rest of this page" before
// reading the rest of it. Directly ties to this platform's own history
// (draft_worker dead 10 days, XO Voice Debrief silently dead, both
// discovered only after the fact). Counts only 'failed' heartbeats as
// worth surfacing here — 'unknown'/'skipped' are routinely correct
// (see agent-status route's own cadence-label history: reading every
// stale job as "dead" was already a confirmed false-positive mistake
// once, don't repeat it on this page).
interface AgentHealthSummary {
  failedCount: number;
  worstLabel: string | null;
}

function useAgentHealth(): { data: AgentHealthSummary | null; loading: boolean; error: string | null } {
  const [data, setData] = useState<AgentHealthSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch('/api/agent-status');
        if (!res.ok) throw new Error(`Agent status unavailable (${res.status})`);
        const body = await res.json();
        if (cancelled) return;
        const jobs: { status: string; label: string }[] = Array.isArray(body?.jobs) ? body.jobs : [];
        const failed = jobs.filter((j) => j.status === 'failed');
        setData({ failedCount: failed.length, worstLabel: failed[0]?.label ?? null });
        setError(null);
      } catch (e) {
        console.error('[CaptainsChair] useAgentHealth failed:', e);
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load agent status');
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
  /** 2026-08-29: oldest item in each queue, not just its count — same
   * curated-not-raw philosophy already applied to Signal Snapshot,
   * finishing the demotion the council flagged as still leftover on these
   * two tiles. Oldest (longest-waiting), not highest-priority: this is a
   * "what's been sitting here the longest" signal, matching the Contrarian
   * council advisor's framing. */
  oldestContentAwaitingPublish: string | null;
  oldestCapturePending: string | null;
}

interface TopOsintSignal {
  title: string;
  risk_rating: string;
  canonical_url: string | null;
}

interface TopHealthSignal {
  title: string;
  severity: string;
}

interface SignalSnapshot {
  capacityState: string | null;
  postureMessage: string | null;
  topOsintSignal: TopOsintSignal | null;
  topHealthSignal: TopHealthSignal | null;
}

function useAttentionCounts(): { data: AttentionCounts; snapshot: SignalSnapshot; loading: boolean; errors: string[] } {
  const [data, setData] = useState<AttentionCounts>({
    contentAwaitingPublish: null,
    contentPriorityFlagged: null,
    capturePending: null,
    wellnessRiskFlags: null,
    oldestContentAwaitingPublish: null,
    oldestCapturePending: null,
  });
  const [snapshot, setSnapshot] = useState<SignalSnapshot>({
    capacityState: null,
    postureMessage: null,
    topOsintSignal: null,
    topHealthSignal: null,
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

      // Oldest pending capture, for the same curated-worst-item demotion
      // as content below. fetchInboxCaptures orders newest-first, so the
      // last element (not [0]) within the fetched page is the oldest —
      // exact within the first `limit` pending items, which is the same
      // "good enough, not exhaustive" tradeoff Signal Snapshot's other
      // curated cards already make.
      const oldestCapture = await fetchInboxCaptures({ statusFilter: 'pending', limit: 50 })
        .then((rows) => rows.length > 0 ? rows[rows.length - 1] : null)
        .catch((e) => { console.error('[CaptainsChair] oldest pending capture failed:', e); return null; });

      const wellness = await fetch('/api/human-systems?domain=recovery')
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
        .catch((e) => { console.error('[CaptainsChair] wellness risk flags failed:', e); errs.push('Wellness signals'); return null; });

      // Signal Snapshot (2026-08-22): curated top items, not raw counts —
      // a first pass surfaced raw counts (e.g. 1,851 degraded intelligence
      // sources) directly in "Needs Your Attention" and that read as
      // overwhelming noise, not a curated signal. These two feed the
      // separate Signal Snapshot card instead.
      const osintAttention = await fetch('/api/intelligence-workbench/attention-count')
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
        .catch((e) => { console.error('[CaptainsChair] top OSINT signal failed:', e); errs.push('OSINT signal'); return null; });

      const healthOsint = await fetch('/api/health-osint/attention-count')
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
        .catch((e) => { console.error('[CaptainsChair] top health OSINT signal failed:', e); errs.push('Health OSINT signal'); return null; });

      if (cancelled) return;

      const items: { status: string; captain_focus?: boolean; title?: string; created_at?: string }[] =
        Array.isArray(content?.items) ? content.items : [];
      const readyToPublish = items.filter((i) => i.status === 'ready_to_publish');
      // Oldest by created_at ascending — "what's been sitting here the
      // longest," same reasoning as the capture queue above.
      const oldestContentItem = readyToPublish.length > 0
        ? [...readyToPublish].sort((a, b) => (a.created_at ?? '').localeCompare(b.created_at ?? ''))[0]
        : null;

      setData({
        contentAwaitingPublish: content ? readyToPublish.length : null,
        contentPriorityFlagged: content ? items.filter((i) => i.captain_focus).length : null,
        capturePending: capture ? capture.pending : null,
        wellnessRiskFlags: wellness ? (wellness.wellness?.risk_flags?.length ?? 0) : null,
        oldestContentAwaitingPublish: oldestContentItem?.title ?? null,
        oldestCapturePending: oldestCapture ? (oldestCapture.title || oldestCapture.raw_text?.slice(0, 60) || null) : null,
      });
      setSnapshot({
        capacityState: wellness ? (wellness.latest_capacity_state ?? null) : null,
        postureMessage: wellness ? (wellness.system_posture_message ?? null) : null,
        topOsintSignal: osintAttention ? (osintAttention.top ?? null) : null,
        topHealthSignal: healthOsint ? (healthOsint.top ?? null) : null,
      });
      setErrors(errs);
      setLoading(false);
    }
    load();
    return () => { cancelled = true; };
  }, []);

  return { data, snapshot, loading, errors };
}

function CountTile({ label, value, href, loading, topItem }: { label: string; value: number | null; href: string; loading: boolean; topItem?: string | null }) {
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
      {/* 2026-08-29: oldest item, not just the count — same curated-not-
          raw demotion Signal Snapshot already applies. Only shown once
          loaded and there's an actual item, never a placeholder. */}
      {!loading && hasAction && topItem && (
        <p className="mt-1 truncate text-[11px] text-wb-ink/70">{topItem}</p>
      )}
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
  const { data: attention, snapshot, loading: attentionLoading, errors: attentionErrors } = useAttentionCounts();
  const { data: emergency, loading: emergencyLoading, error: emergencyError } = useEmergencyAlerts();
  const { data: agentHealth, loading: agentHealthLoading, error: agentHealthError } = useAgentHealth();

  const postureBand = currentPosture.posture;
  const postureTone = POSTURE_STATE_TONE[postureBand];
  const riskTone = opRisk?.overallRisk ? (RISK_STATE_TONE[opRisk.overallRisk] ?? 'unknown') : 'unknown';
  const interruptTone: StateTone = (briefingStats?.interruptNow ?? 0) > 0 ? 'crit' : 'ok';
  const emergencyTone: StateTone = emergency?.worstTier === 'emergency_warning' ? 'crit' : emergency?.worstTier === 'watch_and_act' ? 'warn' : 'ok';
  const agentHealthTone: StateTone = (agentHealth?.failedCount ?? 0) > 0 ? 'crit' : 'ok';

  return (
    <WorkbenchShell
      title="Captain's Chair"
      eyebrow="Executive Summary"
      tagline="USS TJR · Captain's Chair · Executive Summary"
      back={{ href: '/workbenches', label: 'Workbenches' }}
    >
      <div className="space-y-4">
        {/* ── Situation strip ── */}
        {/* 2026-08-29: flex-wrap added when this grew from 3 to 5 badges
            (Emergency Alerts, Background Systems) — sm:flex-row alone
            would cram 5 flex-1 items into one row on tablet widths. */}
        <div className="flex flex-col flex-wrap gap-3 sm:flex-row">
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
          <SituationBadge
            label="Emergency Alerts"
            value={emergencyLoading ? '…' : emergencyError ? 'Unknown' : emergency?.count ? `${emergency.count} Active` : 'Clear'}
            tone={emergencyError ? 'unknown' : emergencyTone}
            sublabel={emergency?.worstHeadline ?? undefined}
            href="/emergency-alert-hub-workbench"
          />
          <SituationBadge
            label="Background Systems"
            value={agentHealthLoading ? '…' : agentHealthError ? 'Unknown' : agentHealth?.failedCount ? `${agentHealth.failedCount} Failing` : 'Nominal'}
            tone={agentHealthError ? 'unknown' : agentHealthTone}
            sublabel={agentHealth?.worstLabel ?? undefined}
            href="/agent-status-workbench"
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
            <CountTile label="Content Awaiting Publish" value={attention.contentAwaitingPublish} href="/content-workbench" loading={attentionLoading} topItem={attention.oldestContentAwaitingPublish} />
            <CountTile label="Capture Pending Triage" value={attention.capturePending} href="/capture-workbench" loading={attentionLoading} topItem={attention.oldestCapturePending} />
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

        {/* ── Signal Snapshot (2026-08-22) — curated top items from Human
            Systems / Technical OSINT / Health OSINT, replacing a first pass
            that put raw counts (incl. 1,851 degraded intelligence sources)
            straight into "Needs Your Attention" and read as noise, not
            signal. One item per source, "all clear" when there's nothing
            worth surfacing — never a false zero. */}
        <div className="rounded-lg border border-wb-line bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold text-wb-ink">Signal Snapshot</h2>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className={`rounded-lg border ${stateToneClasses(CAPACITY_STATE_TONE[snapshot.capacityState ?? ''] ?? 'unknown').border} ${stateToneClasses(CAPACITY_STATE_TONE[snapshot.capacityState ?? ''] ?? 'unknown').bg} p-3`}>
              <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Capacity Today</p>
              <p className={`mt-0.5 text-lg font-bold ${stateToneClasses(CAPACITY_STATE_TONE[snapshot.capacityState ?? ''] ?? 'unknown').text}`}>
                {attentionLoading ? '…' : snapshot.capacityState ? CAPACITY_STATE_LABEL[snapshot.capacityState] ?? snapshot.capacityState : 'No data'}
              </p>
              {snapshot.postureMessage && (
                <p className="mt-1 text-xs text-wb-ink/80">{snapshot.postureMessage}</p>
              )}
              <Link href="/human-systems-workbench" className="mt-2 inline-block text-[11px] text-wb-sage-deep hover:underline">
                Human Systems →
              </Link>
            </div>

            <div className={`rounded-lg border ${stateToneClasses(snapshot.topOsintSignal ? RISK_STATE_TONE[snapshot.topOsintSignal.risk_rating] ?? 'unknown' : 'ok').border} ${stateToneClasses(snapshot.topOsintSignal ? RISK_STATE_TONE[snapshot.topOsintSignal.risk_rating] ?? 'unknown' : 'ok').bg} p-3`}>
              <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Top OSINT Signal</p>
              {attentionLoading ? (
                <p className="mt-0.5 text-sm text-wb-ink2">…</p>
              ) : snapshot.topOsintSignal ? (
                <>
                  <p className="mt-0.5 text-sm font-semibold text-wb-ink">{snapshot.topOsintSignal.risk_rating}</p>
                  <p className="mt-1 text-xs text-wb-ink/80">{snapshot.topOsintSignal.title}</p>
                </>
              ) : (
                <p className="mt-0.5 text-sm text-wb-ink2">All clear — nothing rated RED/AMBER this week.</p>
              )}
              <Link href="/intelligence-workbench" className="mt-2 inline-block text-[11px] text-wb-sage-deep hover:underline">
                OSINT Workbench →
              </Link>
            </div>

            <div className={`rounded-lg border ${stateToneClasses(snapshot.topHealthSignal ? HEALTH_SEVERITY_TONE[snapshot.topHealthSignal.severity] ?? 'unknown' : 'ok').border} ${stateToneClasses(snapshot.topHealthSignal ? HEALTH_SEVERITY_TONE[snapshot.topHealthSignal.severity] ?? 'unknown' : 'ok').bg} p-3`}>
              <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Top Health Signal</p>
              {attentionLoading ? (
                <p className="mt-0.5 text-sm text-wb-ink2">…</p>
              ) : snapshot.topHealthSignal ? (
                <>
                  <p className="mt-0.5 text-sm font-semibold text-wb-ink capitalize">{snapshot.topHealthSignal.severity}</p>
                  <p className="mt-1 text-xs text-wb-ink/80">{snapshot.topHealthSignal.title}</p>
                </>
              ) : (
                <p className="mt-0.5 text-sm text-wb-ink2">All clear — nothing escalating right now.</p>
              )}
              <Link href="/health-osint" className="mt-2 inline-block text-[11px] text-wb-sage-deep hover:underline">
                Health OSINT →
              </Link>
            </div>
          </div>
        </div>

        <TodaysBriefPanel />

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
