'use client';

// LifeOS Hub — Command-Experience vNext (Phase 2, 2026-09-06).
//
// Target role (docs/architecture/COMMAND-EXPERIENCE.md, mission §8): the
// ambient operating picture, understandable in ~3–10 seconds. Answers five
// questions — what kind of day is this, what's next, does anything need
// me, has anything material changed, is HQ okay — and nothing else. It is
// not a mini Captain's Chair, a dashboard, or a workbench browser.
//
// Supersedes the 2026-09-05 MSN-0364-era version, which rendered a
// permanent 5-badge situation strip (Recovery Posture/Operational
// Risk/Interrupt Now/Emergency Alerts/Background Systems) plus a raw Live
// Alerts list — exactly the "dashboard, not command system" pattern the
// vNext mission calls out. This version consumes the same shared command
// synthesis Captain's Chair does (captainsChairSynthesis.ts's
// deriveCommandStatus(), commandState.ts's deriveCommandPosture()/
// buildNeedsYouItems()/deriveIntelligenceHeadline()) so the two surfaces
// cannot disagree on Human Systems state, genuine Needs You, Emergency
// materiality, HQ health, or command posture (mission §17).
//
// Sanctuary / low-stimulation behaviour (mission §8): when capacity is
// constrained (PROTECT/RECOVER) and nothing needs you, the page quiets
// itself — Next Commitments and Intelligence collapse to their headline
// only, no expanded detail.
//
// Architecture: /hub is the start_url (manifest.webmanifest) — the front
// door. The WorkbenchShell logo click goes to /workbenches (the full
// directory) — Captain's Chair is one of those workbenches, reachable the
// same as any other, not the same page as this one.

import { useState } from 'react';
import { WorkbenchShell } from '@/components/ui';
import {
  useHumanSystemsContext,
  useHqStatusSummary,
  useOperationalRisk,
  useEmergencyAlerts,
  useTodaysBriefing,
  useCalendarToday,
  useAttentionCounts,
  useEvolutionSignal,
  useNotebookReadyCount,
} from '@/lib/captainsChairData';
import { useAlerts } from '@/lib/useAlerts';
import { deriveCommandStatus } from '@/lib/captainsChairSynthesis';
import { deriveCommandPosture, buildNeedsYouItems, deriveIntelligenceHeadline } from '@/lib/commandState';
import { playTts, type TtsPlaybackState } from '@/lib/ttsPlayer';
import { useWakeLock } from '@/lib/useWakeLock';

const POSTURE_TONE_CLASS: Record<string, string> = {
  RESPOND: 'text-state-crit',
  RECOVER: 'text-state-crit',
  PROTECT: 'text-state-warn',
  FOCUS: 'text-state-ok',
  STEADY: 'text-state-ok',
  UNKNOWN: 'text-state-unknown',
};

export default function LifeOSHub() {
  // Always-on wall-tablet use (this page's whole purpose) — keeps the
  // screen awake while it's open. Deliberately only on this page.
  useWakeLock();

  const { context: humanSystems, loading: humanSystemsLoading, error: humanSystemsError } = useHumanSystemsContext();
  const { data: opRisk, loading: opRiskLoading, error: opRiskError } = useOperationalRisk();
  const { stats: briefingStats, loading: briefingLoading, error: briefingError } = useTodaysBriefing();
  const { data: emergency, loading: emergencyLoading, error: emergencyError } = useEmergencyAlerts();
  const { data: hqStatus, loading: hqStatusLoading, error: hqStatusError } = useHqStatusSummary();
  const { events: calendarEvents, status: calendarStatus, loading: calendarLoading } = useCalendarToday();
  const { data: attention, loading: attentionLoading } = useAttentionCounts();
  const { readyCount: notebookReadyCount } = useNotebookReadyCount();
  const { pendingCount: evolutionPendingCount, highestValueTitle: evolutionHighestValueTitle } = useEvolutionSignal();
  const { alerts: liveAlerts } = useAlerts();

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

  // The exact same builder Captain's Chair uses — same inputs, same
  // output, so the two surfaces cannot disagree on "what needs you."
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

  const commandPosture = deriveCommandPosture({
    hasEnvironmentConcern: commandStatus.hasEnvironmentConcern,
    needsYouCount: needsYouItems.length,
    humanSystemsUnavailable: humanSystemsError !== null,
    hasCheckinToday,
    humanSystemsPosture: humanSystems?.posture ?? 'UNKNOWN',
    meaningfulCommitmentsToday: calendarStatus === 'ok' ? calendarEvents.length : 0,
  });

  const intelligenceHeadline = deriveIntelligenceHeadline({
    briefingError: briefingError !== null,
    briefingWarningsCount: briefingStats?.warnings ?? 0,
    operationalRisk: (opRisk?.overallRisk as 'GREEN' | 'AMBER' | 'RED' | null) ?? null,
    operationalRiskUnknown: opRiskError !== null,
    emergencyWorstTier: emergency?.worstTier ?? null,
    emergencyHeadline: emergency?.worstHeadline ?? null,
  });

  const stillLoading = humanSystemsLoading || opRiskLoading || briefingLoading || emergencyLoading || hqStatusLoading || attentionLoading;

  // Sanctuary / low-stimulation behaviour (mission §8): quiet the page when
  // capacity is constrained and nothing genuinely needs attention. Never
  // hides genuine risk — RESPOND always takes priority over quieting, since
  // deriveCommandPosture() only returns PROTECT/RECOVER when
  // hasEnvironmentConcern is false and needsYouCount is 0.
  const sanctuary = !stillLoading
    && (commandPosture.posture === 'PROTECT' || commandPosture.posture === 'RECOVER')
    && needsYouItems.length === 0;

  // Acceptance-audit repair: `sanctuary` alone is not enough to hide the
  // World/Intelligence section. hasEnvironmentConcern only reacts to
  // emergency_warning/RED — a `watch_and_act` tier or a genuinely
  // unavailable Brief/Operational-Risk read (intelligenceHeadline.unknown)
  // can coexist with PROTECT/RECOVER + zero Needs You, and quiet mode must
  // never suppress that (mission §8: "changes presentation, not truth").
  // World only disappears when intelligence itself is confirmed quiet.
  const hideWorldSection = sanctuary && !intelligenceHeadline.unknown && intelligenceHeadline.headline === 'NO MATERIAL CHANGE';

  const [speakState, setSpeakState] = useState<TtsPlaybackState>('idle');

  // TTS reads the command picture (posture, next commitment, Needs You,
  // intelligence headline), not a dashboard inventory — 2026-09-05 switched
  // from browser SpeechSynthesis to generated audio via <audio> playback;
  // see /api/tts/speak for the backend history.
  function speakCommandPicture() {
    const parts: string[] = [`${commandPosture.headline}. ${commandPosture.explanation}`];
    if (calendarStatus === 'ok' && calendarEvents.length > 0) {
      const next = calendarEvents[0];
      parts.push(`Next: ${next.allDay ? 'all day' : next.time ?? ''} ${next.title}.`);
    }
    if (needsYouItems.length > 0) {
      parts.push(`${needsYouItems.length} thing${needsYouItems.length === 1 ? '' : 's'} need you: ${needsYouItems[0].title}.`);
    } else {
      parts.push('Nothing needs you right now.');
    }
    parts.push(intelligenceHeadline.headline === 'NO MATERIAL CHANGE' ? 'No material change in the world.' : intelligenceHeadline.detail);
    const text = parts.join(' ');
    playTts(text, { cacheKey: text, onStateChange: setSpeakState });
  }

  return (
    <WorkbenchShell
      title="LifeOS Hub"
      eyebrow="Glance View"
      tagline="USS TJR · LifeOS Hub · Workbenches →"
      wide
    >
      <div className="mx-auto max-w-xl space-y-6 py-2">
        {/* ── 1. Day / date / time — subtle, always useful ── */}
        <p className="text-center text-xs uppercase tracking-wider text-wb-ink2">
          {new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}
        </p>

        {/* ── 2. Command posture — one headline, one explanation ── */}
        <div className="text-center">
          {stillLoading ? (
            <p className="text-sm text-wb-ink2 animate-pulse">Assessing…</p>
          ) : (
            <>
              <p className={`text-4xl font-bold tracking-tight ${POSTURE_TONE_CLASS[commandPosture.posture]}`}>
                {commandPosture.headline} TODAY
              </p>
              <p className="mx-auto mt-2 max-w-md text-sm text-wb-ink/80">{commandPosture.explanation}</p>
            </>
          )}
        </div>

        {!stillLoading && (
          <>
            {/* ── 3. Next commitments — only meaningful upcoming Calendar items ── */}
            {!sanctuary && (
              <div className="rounded-lg border border-wb-line bg-white p-4">
                <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-wb-ink2">Next</h2>
                {calendarStatus === 'disconnected' ? (
                  <p className="text-sm text-wb-ink2">
                    Calendar isn&apos;t connected.{' '}
                    <a href="/api/auth/google-calendar/connect" className="text-wb-sage-deep hover:underline">Connect it</a>.
                  </p>
                ) : calendarStatus === 'error' ? (
                  <p className="text-sm text-wb-crit-on">Calendar failed to load — not confirmation of an empty day.</p>
                ) : calendarEvents.length === 0 ? (
                  <p className="text-sm text-wb-ink2">Nothing on the calendar today.</p>
                ) : (
                  <ul className="space-y-1.5">
                    {calendarEvents.slice(0, 3).map((event, i) => (
                      <li key={i} className="flex items-baseline gap-2 text-sm">
                        <span className="w-14 shrink-0 font-semibold text-wb-ink">{event.allDay ? 'All day' : event.time ?? '—'}</span>
                        <span className="text-wb-ink">{event.title}{event.location && <span className="text-wb-ink2"> · {event.location}</span>}</span>
                      </li>
                    ))}
                    {calendarEvents.length > 3 && <p className="text-xs text-wb-ink2">+{calendarEvents.length - 3} more</p>}
                  </ul>
                )}
              </div>
            )}

            {/* ── 4. Needs You — prefer 0–3 genuinely actionable items ── */}
            <div className="rounded-lg border border-wb-line bg-white p-4">
              <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-wb-ink2">Needs You</h2>
              {needsYouItems.length === 0 ? (
                <p className="text-sm font-medium text-wb-ink2">✓ Nothing needs your attention.</p>
              ) : (
                <ul className="space-y-1.5">
                  {needsYouItems.slice(0, 3).map((item) => (
                    <li key={item.id} className="text-sm">
                      <span className="font-semibold text-wb-ink">{item.title}</span>
                      <span className="text-wb-ink2"> — {item.detail}</span>
                    </li>
                  ))}
                  {needsYouItems.length > 3 && (
                    <li className="text-xs text-wb-ink2">+{needsYouItems.length - 3} more — see Captain&apos;s Chair</li>
                  )}
                </ul>
              )}
            </div>

            {/* ── 5. World / intelligence — one headline or honest unknown ── */}
            {!hideWorldSection && (
              <div className="rounded-lg border border-wb-line bg-white p-4">
                <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-wb-ink2">World</h2>
                <p className="text-sm font-medium text-wb-ink">{intelligenceHeadline.headline === 'NO MATERIAL CHANGE' ? 'No material change' : intelligenceHeadline.headline}</p>
                <p className="mt-0.5 text-xs text-wb-ink2">{intelligenceHeadline.detail}</p>
              </div>
            )}

            {/* ── 6. HQ — tiny status ── */}
            <p className="text-center text-xs text-wb-ink2">
              {hqStatusError
                ? 'HQ status unknown'
                : hqStatus?.posture === 'NORMAL'
                  ? 'Operating normally'
                  : hqStatus?.posture === 'ATTENTION'
                    ? `Needs you — ${hqStatus.summary}`
                    : hqStatus?.posture === 'DEGRADED'
                      ? 'Degraded — no action required'
                      : 'Status unknown'}
            </p>

            {/* ── 7. Calm end state + Read aloud ── */}
            <div className="flex flex-col items-center gap-2 pt-2">
              {needsYouItems.length === 0 && (
                <p className="text-sm text-wb-ink2">Nothing else needs you.</p>
              )}
              <button
                type="button"
                onClick={speakCommandPicture}
                disabled={speakState === 'generating' || speakState === 'playing'}
                className="text-[11px] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep disabled:opacity-60 disabled:no-underline"
              >
                {speakState === 'generating' ? 'Generating…' : speakState === 'playing' ? '🔊 Playing…' : speakState === 'error' ? '⚠️ Failed — retry' : '🔊 Read aloud'}
              </button>
            </div>
          </>
        )}
      </div>
    </WorkbenchShell>
  );
}
