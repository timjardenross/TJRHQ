'use client';

import { WorkbenchShell } from '@/components/ui';
import { TodaysBriefPanel } from '@/components/TodaysBriefPanel';
import { useAlerts } from '@/lib/useAlerts';
import {
  RISK_STATE_TONE,
  SYSTEM_POSTURE_STATE_TONE,
  useHumanSystemsContext,
  useHqStatusSummary,
  useOperationalRisk,
  useEmergencyAlerts,
  useTodaysBriefing,
  useCalendarToday,
  useCalendarUpcoming,
  useReminders,
  useAttentionCounts,
  useEvolutionSignal,
  useNotebookReadyCount,
} from '@/lib/captainsChairData';
import { deriveCommandStatus, sortNeedsYou } from '@/lib/captainsChairSynthesis';
import { deriveCommandPosture, buildNeedsYouItems, deriveIntelligenceHeadline } from '@/lib/commandState';
import { CommandStatus } from './_components/CommandStatus';
import { NeedsYou } from './_components/NeedsYou';
import { Intelligence } from './_components/Intelligence';
import { Capacity } from './_components/Capacity';
import { SystemStatus } from './_components/SystemStatus';
import { HqEvolution } from './_components/HqEvolution';
import { Ahead } from './_components/Ahead';
import { CaptainsLog } from './_components/CaptainsLog';

// Command-Experience vNext (Phase 2, 2026-09-06) — re-anchors this page
// around the mission's target information architecture: TODAY -> NEEDS YOU
// -> INTELLIGENCE -> AHEAD -> CAPACITY -> HQ EVOLUTION -> SYSTEM STATUS
// (docs/architecture/COMMAND-EXPERIENCE.md). Supersedes MSN-0364's POSTURE
// -> ATTENTION -> SITUATION -> AHEAD -> BRIEF -> CAPTURE anchor — Situation
// (the old Personal/Environment/Systems fold) is retired in favour of three
// dedicated sections (Intelligence, Capacity, System Status) that each
// consume exactly one canonical, already-interpreted contract instead of
// re-curating raw OSINT/health/job signals on this page. See
// docs/architecture/COMMAND-EXPERIENCE.md for the full domain-owner map.
//
// Notes worth knowing before touching this file again:
// - Today's headline is the command-level posture (commandState.ts's
//   deriveCommandPosture()), not Human Systems' own posture band — Human
//   Systems contributes to it, it does not become it (mission §6).
// - Needs You is built once by commandState.ts's buildNeedsYouItems() so
//   LifeOS can render the identical list — no second copy of this logic.
// - System Status reads the canonical HQ Status summary
//   (hqStatusInterpreter.ts's buildCaptainChairSummary(), via
//   useHqStatusSummary()) — never a raw failed-job count.
// - /api/captain-brief (useTodaysBriefing) is a known-fragile source
//   (external context-service process, documented prior silent-breakage on
//   Vercel) — its confidence/priorities/recommendations fields are still
//   not rendered on this page (Captain-locked decision, unchanged);
//   interruptNow and warnings feed the Intelligence headline and Needs You.
// - Captain's Notebook's full officer-review/routing workflow
//   (intelligence_notes) is untouched — Captain's Log here is a thin
//   capture box in front of it, not a replacement.

export default function CaptainsChairWorkbench() {
  const { context: humanSystems, loading: humanSystemsLoading, error: humanSystemsError } = useHumanSystemsContext();
  const { alerts: liveAlerts } = useAlerts();
  const { data: opRisk, loading: opRiskLoading, error: opRiskError } = useOperationalRisk();
  const { stats: briefingStats, loading: briefingLoading, error: briefingError } = useTodaysBriefing();
  const { data: attention, loading: attentionLoading, errors: attentionErrors } = useAttentionCounts();
  const { data: emergency, loading: emergencyLoading, error: emergencyError } = useEmergencyAlerts();
  const { data: hqStatus, loading: hqStatusLoading, error: hqStatusError } = useHqStatusSummary();
  const { events: calendarEvents, status: calendarStatus, loading: calendarLoading } = useCalendarToday();
  const { events: upcoming, status: upcomingStatus, loading: upcomingLoading } = useCalendarUpcoming(2);
  const { tasks: reminders, loading: remindersLoading } = useReminders();
  const { readyCount: notebookReadyCount } = useNotebookReadyCount();
  const { pendingCount: evolutionPendingCount, highestValueTitle: evolutionHighestValueTitle } = useEvolutionSignal();

  const commandStatusLoading = humanSystemsLoading || opRiskLoading || briefingLoading || emergencyLoading || hqStatusLoading;
  const hasCheckinToday = humanSystems?.has_checkin_today ?? false;
  const hqPostureLower = (hqStatus?.posture ?? 'UNKNOWN').toLowerCase() as 'normal' | 'degraded' | 'attention' | 'unknown';

  const commandStatus = deriveCommandStatus({
    posture: humanSystems?.posture ?? 'UNKNOWN',
    postureMessage: humanSystems?.posture_message ?? 'No capacity check-in recorded for today yet.',
    availableCapacity: humanSystems?.available_capacity ?? 'unknown',
    hasCheckinToday,
    humanSystemsUnavailable: humanSystemsError !== null,
    operationalRisk: (opRisk?.overallRisk as 'GREEN' | 'AMBER' | 'RED' | null) ?? null,
    operationalRiskUnknown: opRiskError !== null,
    escalateCount: opRisk?.escalateCount ?? 0,
    interruptNow: briefingError ? null : (briefingStats?.interruptNow ?? 0),
    emergencyCount: emergency?.count ?? 0,
    emergencyWorstTier: emergency?.worstTier ?? null,
    hqPosture: hqPostureLower,
    hqSummary: hqStatus?.summary ?? null,
    hqUnavailable: hqStatusError !== null,
  });

  // ── Needs You: one curated list, shared with LifeOS via commandState.ts ──
  const needsYouItems = buildNeedsYouItems({
    emergency,
    briefingError: briefingError !== null,
    interruptNow: briefingError ? null : (briefingStats?.interruptNow ?? 0),
    contentAwaitingPublish: attention.contentAwaitingPublish,
    oldestContentAwaitingPublish: attention.oldestContentAwaitingPublish,
    wellnessRiskFlags: attention.wellnessRiskFlags,
    notebookReadyCount,
    capturePending: attention.capturePending,
    oldestCapturePending: attention.oldestCapturePending,
    evolutionPendingCount,
    evolutionHighestValueTitle,
    hqPosture: hqStatus?.posture ?? null,
    hqAttentionItems: hqStatus?.attentionItems ?? [],
    criticalAlerts: liveAlerts.filter((a) => a.severity === 'critical').map((a) => ({ id: a.id, title: a.title, detail: a.detail, href: a.href })),
  });
  const sortedNeedsYou = sortNeedsYou(needsYouItems);
  const needsYouErrors = [...attentionErrors, ...(emergencyError ? ['Emergency alerts'] : []), ...(hqStatusError ? ['System status'] : [])];

  // ── Today: the command-level "what kind of day is this" posture ────────
  const commandPosture = deriveCommandPosture({
    hasEnvironmentConcern: commandStatus.hasEnvironmentConcern,
    needsYouCount: sortedNeedsYou.length,
    humanSystemsUnavailable: humanSystemsError !== null,
    hasCheckinToday,
    humanSystemsPosture: humanSystems?.posture ?? 'UNKNOWN',
    meaningfulCommitmentsToday: calendarStatus === 'ok' ? calendarEvents.length : 0,
  });

  // ── Intelligence: one canonical headline ────────────────────────────────
  const intelligenceHeadline = deriveIntelligenceHeadline({
    briefingError: briefingError !== null,
    briefingWarningsCount: briefingStats?.warnings ?? 0,
    operationalRisk: (opRisk?.overallRisk as 'GREEN' | 'AMBER' | 'RED' | null) ?? null,
    operationalRiskUnknown: opRiskError !== null,
    emergencyWorstTier: emergency?.worstTier ?? null,
    emergencyHeadline: emergency?.worstHeadline ?? null,
  });

  const capacityTone = humanSystemsLoading
    ? ('unknown' as const)
    : humanSystemsError
      ? ('unknown' as const)
      : SYSTEM_POSTURE_STATE_TONE[commandStatus.posture];

  const signalChips = [
    {
      label: 'Capacity',
      value: humanSystemsLoading ? '…' : humanSystemsError ? 'Data error' : !hasCheckinToday ? 'No check-in' : (humanSystems?.available_capacity ?? 'unknown'),
      tone: capacityTone,
      href: '/human-systems-workbench',
    },
    { label: 'Interrupts', value: briefingLoading ? '…' : briefingError ? 'Unknown' : `${briefingStats?.interruptNow ?? 0}`, tone: briefingError ? 'unknown' as const : (briefingStats?.interruptNow ?? 0) > 0 ? 'crit' as const : 'ok' as const, href: '/captains-brief-workbench' },
    { label: 'Alerts', value: emergencyLoading ? '…' : emergencyError ? 'Unknown' : emergency?.count ? `${emergency.count} Active` : 'Clear', tone: emergencyError ? 'unknown' as const : emergency?.worstTier === 'emergency_warning' ? 'crit' as const : emergency?.worstTier === 'watch_and_act' ? 'warn' as const : 'ok' as const, href: '/emergency-alert-hub-workbench' },
    { label: 'HQ', value: hqStatusLoading ? '…' : hqStatusError ? 'Unknown' : (hqStatus?.posture ?? 'Unknown'), tone: hqStatusError ? 'unknown' as const : hqStatus?.posture === 'ATTENTION' ? 'crit' as const : hqStatus?.posture === 'NORMAL' ? 'ok' as const : hqStatus?.posture === 'DEGRADED' ? 'warn' as const : 'unknown' as const, href: '/agent-status-workbench' },
    { label: 'Risk', value: opRiskLoading ? '…' : opRiskError ? 'Unknown' : (opRisk?.overallRisk ?? 'No data'), tone: opRiskError ? ('unknown' as const) : opRisk?.overallRisk ? (RISK_STATE_TONE[opRisk.overallRisk] ?? 'unknown') : 'unknown', href: '/intelligence-workbench' },
  ];

  return (
    <WorkbenchShell
      title="Captain's Chair"
      eyebrow="Executive command surface"
      tagline="USS TJR · Captain's Chair · Today, Needs You, intelligence, ahead, capacity, evolution, status"
      back={{ href: '/workbenches', label: 'Workbenches' }}
      wide
    >
      <div className="space-y-4">
        <CommandStatus posture={commandPosture} status={commandStatus} loading={commandStatusLoading} signals={signalChips} />

        <NeedsYou items={sortedNeedsYou} loading={attentionLoading} errors={needsYouErrors} />

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Intelligence headline={intelligenceHeadline} loading={opRiskLoading || briefingLoading || emergencyLoading} />
          <Capacity context={humanSystems} loading={humanSystemsLoading} unavailable={humanSystemsError !== null} />
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

        <HqEvolution pendingCount={evolutionPendingCount} highestValueTitle={evolutionHighestValueTitle} />

        <SystemStatus data={hqStatus} loading={hqStatusLoading} error={hqStatusError} />

        <TodaysBriefPanel />

        <CaptainsLog />
      </div>
    </WorkbenchShell>
  );
}
