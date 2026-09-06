'use client';

import { useEffect, useState } from 'react';
import { WorkbenchShell } from '@/components/ui';
import { TodaysBriefPanel } from '@/components/TodaysBriefPanel';
import { useROSData } from '@/lib/useROSData';
import { useAlerts } from '@/lib/useAlerts';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { fetchCaptureAnalytics, fetchInboxCaptures } from '@/lib/capture';
import {
  RISK_STATE_TONE,
  useOperationalRisk,
  useEmergencyAlerts,
  useAgentHealth,
  useTodaysBriefing,
  useCalendarToday,
  useCalendarUpcoming,
  useReminders,
} from '@/lib/captainsChairData';
import { deriveCommandStatus, sortNeedsYou, type NeedsYouItem } from '@/lib/captainsChairSynthesis';
import { CommandStatus } from './_components/CommandStatus';
import { NeedsYou } from './_components/NeedsYou';
import { Situation } from './_components/Situation';
import { Ahead } from './_components/Ahead';
import { CaptainsLog } from './_components/CaptainsLog';

// MSN-0364 Captain's Chair redesign (2026-09-05): re-anchors this page
// around POSTURE -> ATTENTION -> SITUATION -> AHEAD -> BRIEF -> CAPTURE
// instead of a stack of dashboard widgets. See knowledge/missions/
// MSN-0364-captains-chair-redesign.md for the full scoping/audit that
// preceded this — key corrections there worth knowing before touching
// this file again:
//
// - Command Status's interpretation sentence is TEMPLATE-based
//   (captainsChairSynthesis.ts), not LLM-generated — must render
//   instantly, zero network dependency, unlike Captain's Brief below it.
// - useROSData().guidance (mockGuidance array) is still hardcoded mock —
//   never surface it as if real. posture.posture_message/mission_guidance
//   from the RPC ARE real; captainsChairSynthesis.ts only uses those.
// - /api/captain-brief (useTodaysBriefing) is a known-fragile source
//   (external context-service process, documented prior silent-breakage
//   on Vercel) — its confidence/priorities/warnings/recommendations
//   fields are intentionally NOT rendered anywhere on this page any more
//   (Captain-locked decision: removed, not demoted). Only interruptNow is
//   still read from it, since that's the one field with no other source —
//   treated as unknown (not zero) on fetch failure, same as before.
// - Captain's Notebook's full officer-review/routing workflow
//   (intelligence_notes) is untouched — Captain's Log here is a thin
//   capture box in front of it, not a replacement.
//
// Previous executive-summary redesign (2026-08-22) already cut Mission
// Overview/Board, Captain's Timeline, Since Last Session, Engineering
// Queue, and several mock ROS sub-panels from this page — see git history
// on this file for that context; none of it is being reconsidered here.

// ── Needs You + Situation: live counts from across the platform ────────────

interface AttentionCounts {
  contentAwaitingPublish: number | null;
  capturePending: number | null;
  wellnessRiskFlags: number | null;
  oldestContentAwaitingPublish: string | null;
  oldestCapturePending: string | null;
}

interface TopOsintSignal { title: string; risk_rating: string; canonical_url: string | null; }
interface TopHealthSignal { title: string; severity: string; }

interface SignalSnapshot {
  capacityState: string | null;
  postureMessage: string | null;
  topOsintSignal: TopOsintSignal | null;
  topHealthSignal: TopHealthSignal | null;
}

function useAttentionCounts(): { data: AttentionCounts; snapshot: SignalSnapshot; loading: boolean; errors: string[] } {
  const [data, setData] = useState<AttentionCounts>({
    contentAwaitingPublish: null,
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

      const oldestCapture = await fetchInboxCaptures({ statusFilter: 'pending', limit: 50 })
        .then((rows) => rows.length > 0 ? rows[rows.length - 1] : null)
        .catch((e) => { console.error('[CaptainsChair] oldest pending capture failed:', e); return null; });

      const wellness = await fetch('/api/human-systems?domain=recovery')
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
        .catch((e) => { console.error('[CaptainsChair] wellness risk flags failed:', e); errs.push('Wellness signals'); return null; });

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
      const oldestContentItem = readyToPublish.length > 0
        ? [...readyToPublish].sort((a, b) => (a.created_at ?? '').localeCompare(b.created_at ?? ''))[0]
        : null;

      setData({
        contentAwaitingPublish: content ? readyToPublish.length : null,
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

/** HQ Evolution's small morning signal (spec §37) — a count + the
 * highest-value opportunity, never the full Discover/Investigate/Improve/
 * Learned surface. Reuses the same summary endpoint the HQ Evolution page
 * itself uses for morning compression. */
function useEvolutionSignal(): { pendingCount: number | null; highestValueTitle: string | null; error: string | null } {
  const [pendingCount, setPendingCount] = useState<number | null>(null);
  const [highestValueTitle, setHighestValueTitle] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/self-improvement/evolution-summary')
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((body) => {
        if (cancelled) return;
        setPendingCount(body.pending_decisions_count ?? 0);
        setHighestValueTitle(body.highest_value_opportunity?.title ?? null);
      })
      .catch((e) => { if (!cancelled) { console.error('[CaptainsChair] HQ Evolution summary failed:', e); setError('HQ Evolution'); } });
    return () => { cancelled = true; };
  }, []);

  return { pendingCount, highestValueTitle, error };
}

/** Minimal slice of the old NotebookCard's fetch — just the ready-for-
 * routing count, since Captain's Log (compact capture box) replaces the
 * rest of that card's surface. Full detail is one click away. */
function useNotebookReadyCount(): { readyCount: number | null; error: string | null } {
  const [readyCount, setReadyCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const supabase = createSupabaseBrowserClient();
    supabase
      .from('intelligence_notes')
      .select('status')
      .eq('status', 'READY_FOR_ROUTING')
      .then(({ data, error: fetchError }) => {
        if (cancelled) return;
        if (fetchError) { setError(fetchError.message); return; }
        setReadyCount(data?.length ?? 0);
      });
    return () => { cancelled = true; };
  }, []);

  return { readyCount, error };
}

export default function CaptainsChairWorkbench() {
  const { posture: currentPosture, postureFetchFailed } = useROSData();
  const { alerts: liveAlerts } = useAlerts();
  const { data: opRisk, loading: opRiskLoading, error: opRiskError } = useOperationalRisk();
  const { stats: briefingStats, error: briefingError } = useTodaysBriefing();
  const { data: attention, snapshot, loading: attentionLoading, errors: attentionErrors } = useAttentionCounts();
  const { data: emergency, loading: emergencyLoading, error: emergencyError } = useEmergencyAlerts();
  const { data: agentHealth, loading: agentHealthLoading, error: agentHealthError } = useAgentHealth();
  const { events: calendarEvents, status: calendarStatus, loading: calendarLoading } = useCalendarToday();
  const { events: upcoming, status: upcomingStatus, loading: upcomingLoading } = useCalendarUpcoming(2);
  const { tasks: reminders, loading: remindersLoading } = useReminders();
  const { readyCount: notebookReadyCount } = useNotebookReadyCount();
  const { pendingCount: evolutionPendingCount, highestValueTitle: evolutionHighestValueTitle } = useEvolutionSignal();

  const commandStatusLoading = opRiskLoading || emergencyLoading || agentHealthLoading;
  const commandStatus = deriveCommandStatus({
    postureBand: currentPosture.posture,
    postureFetchFailed,
    capacityBand: currentPosture.capacity_band,
    operationalRisk: (opRisk?.overallRisk as 'GREEN' | 'AMBER' | 'RED' | null) ?? null,
    operationalRiskUnknown: opRiskError !== null,
    escalateCount: opRisk?.escalateCount ?? 0,
    interruptNow: briefingError ? null : (briefingStats?.interruptNow ?? 0),
    emergencyCount: emergency?.count ?? 0,
    emergencyWorstTier: emergency?.worstTier ?? null,
    systemsFailedCount: agentHealth?.failedCount ?? 0,
    systemsUnknown: agentHealthError !== null,
  });

  const capacityTone = postureFetchFailed
    ? ('unknown' as const)
    : currentPosture.capacity_band === 'REST' || currentPosture.capacity_band === 'LIMITED'
      ? ('crit' as const)
      : currentPosture.capacity_band === 'MODERATE'
        ? ('warn' as const)
        : currentPosture.capacity_band === 'GOOD'
          ? ('ok' as const)
          : ('unknown' as const);

  const signalChips = [
    { label: 'Capacity', value: postureFetchFailed ? 'Data error' : currentPosture.capacity_band, tone: capacityTone, href: '/human-systems-workbench' },
    { label: 'Interrupts', value: briefingError ? 'Unknown' : `${briefingStats?.interruptNow ?? 0}`, tone: briefingError ? 'unknown' as const : (briefingStats?.interruptNow ?? 0) > 0 ? 'crit' as const : 'ok' as const, href: '/captains-brief-workbench' },
    { label: 'Alerts', value: emergencyLoading ? '…' : emergencyError ? 'Unknown' : emergency?.count ? `${emergency.count} Active` : 'Clear', tone: emergencyError ? 'unknown' as const : emergency?.worstTier === 'emergency_warning' ? 'crit' as const : emergency?.worstTier === 'watch_and_act' ? 'warn' as const : 'ok' as const, href: '/emergency-alert-hub-workbench' },
    { label: 'Systems', value: agentHealthLoading ? '…' : agentHealthError ? 'Unknown' : agentHealth?.failedCount ? `${agentHealth.failedCount} Failing` : 'Nominal', tone: agentHealthError ? 'unknown' as const : (agentHealth?.failedCount ?? 0) > 0 ? 'crit' as const : 'ok' as const, href: '/agent-status-workbench' },
    { label: 'Risk', value: opRiskLoading ? '…' : opRiskError ? 'Unknown' : (opRisk?.overallRisk ?? 'No data'), tone: opRiskError ? ('unknown' as const) : opRisk?.overallRisk ? (RISK_STATE_TONE[opRisk.overallRisk] ?? 'unknown') : 'unknown', href: '/intelligence-workbench' },
  ];

  // ── Needs You: real human-gate items only, priority-sorted ──────────────
  const needsYouItems: NeedsYouItem[] = [];
  if (emergency?.worstTier === 'emergency_warning') {
    needsYouItems.push({
      id: 'emergency', kind: 'safety',
      title: emergency.worstHeadline ?? 'Active emergency warning',
      detail: `${emergency.count} active alert${emergency.count === 1 ? '' : 's'} at emergency tier.`,
      href: '/emergency-alert-hub-workbench', actionLabel: 'Review',
    });
  }
  if (!briefingError && (briefingStats?.interruptNow ?? 0) > 0) {
    needsYouItems.push({
      id: 'interrupt', kind: 'time_critical',
      title: `${briefingStats!.interruptNow} item${briefingStats!.interruptNow === 1 ? '' : 's'} flagged to interrupt now`,
      detail: 'The Attention Engine flagged this as needing you right now.',
      href: '/captains-brief-workbench', actionLabel: 'Review',
    });
  }
  if ((attention.contentAwaitingPublish ?? 0) > 0) {
    needsYouItems.push({
      id: 'content-publish', kind: 'approval',
      title: attention.oldestContentAwaitingPublish ?? 'Content ready to publish',
      detail: `${attention.contentAwaitingPublish} item${attention.contentAwaitingPublish === 1 ? '' : 's'} QA'd and ready for your publish decision.`,
      href: '/content-workbench', actionLabel: 'Publish / Schedule',
    });
  }
  if ((attention.wellnessRiskFlags ?? 0) > 0) {
    needsYouItems.push({
      id: 'wellness', kind: 'review',
      title: 'Nervous-system load remains elevated',
      detail: `${attention.wellnessRiskFlags} wellness risk flag${attention.wellnessRiskFlags === 1 ? '' : 's'} raised.`,
      href: '/human-systems-workbench', actionLabel: 'Review',
    });
  }
  if (notebookReadyCount !== null && notebookReadyCount > 0) {
    needsYouItems.push({
      id: 'notebook', kind: 'review',
      title: `${notebookReadyCount} note${notebookReadyCount === 1 ? '' : 's'} ready for routing`,
      detail: 'Captured in the Log, reviewed, waiting on your routing decision.',
      href: '/captains-chair-workbench/notebook', actionLabel: 'Review',
    });
  }
  if ((attention.capturePending ?? 0) > 0) {
    needsYouItems.push({
      id: 'capture-triage', kind: 'triage',
      title: attention.oldestCapturePending ?? 'Captures waiting on triage',
      detail: `${attention.capturePending} item${attention.capturePending === 1 ? '' : 's'} waiting.`,
      href: '/capture-workbench', actionLabel: 'Review',
    });
  }
  if ((evolutionPendingCount ?? 0) > 0) {
    needsYouItems.push({
      id: 'hq-evolution', kind: 'review',
      title: evolutionHighestValueTitle ?? 'HQ Evolution has opportunities worth considering',
      detail: `${evolutionPendingCount} opportunit${evolutionPendingCount === 1 ? 'y' : 'ies'} from overnight research ${evolutionPendingCount === 1 ? 'needs' : 'need'} your decision.`,
      href: '/self-improvement-findings', actionLabel: 'Review',
    });
  }
  for (const alert of liveAlerts.filter((a) => a.severity === 'critical').slice(0, 2)) {
    needsYouItems.push({
      id: `alert-${alert.id}`, kind: 'time_critical',
      title: alert.title, detail: alert.detail, href: alert.href, actionLabel: 'Review',
    });
  }
  const needsYouErrors = [...attentionErrors, ...(emergencyError ? ['Emergency alerts'] : []), ...(agentHealthError ? ['Systems'] : [])];

  return (
    <WorkbenchShell
      title="Captain's Chair"
      eyebrow="Executive command surface"
      tagline="USS TJR · Captain's Chair · Posture, attention, situation, ahead, synthesis, capture"
      back={{ href: '/workbenches', label: 'Workbenches' }}
      wide
    >
      <div className="space-y-4">
        <CommandStatus status={commandStatus} loading={commandStatusLoading} signals={signalChips} />

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <NeedsYou items={sortNeedsYou(needsYouItems)} loading={attentionLoading} errors={needsYouErrors} />
          <Situation
            loading={attentionLoading}
            data={{
              capacityState: snapshot.capacityState,
              postureMessage: snapshot.postureMessage,
              topHealthSignal: snapshot.topHealthSignal,
              emergencyCount: emergency?.count ?? 0,
              emergencyWorstHeadline: emergency?.worstHeadline ?? null,
              emergencyTone: emergency?.worstTier === 'emergency_warning' ? 'crit' : emergency?.worstTier === 'watch_and_act' ? 'warn' : 'ok',
              topOsintSignal: snapshot.topOsintSignal,
              agentFailedCount: agentHealth?.failedCount ?? 0,
              agentWorstLabel: agentHealth?.worstLabel ?? null,
            }}
          />
        </div>

        <Ahead
          calendarEvents={calendarEvents}
          calendarStatus={calendarStatus}
          calendarLoading={calendarLoading}
          upcoming={upcoming}
          upcomingStatus={upcomingStatus}
          upcomingLoading={upcomingLoading}
          reminders={reminders}
          remindersLoading={remindersLoading}
        />

        <TodaysBriefPanel />

        <CaptainsLog />
      </div>
    </WorkbenchShell>
  );
}
