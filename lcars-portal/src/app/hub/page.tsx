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
//
// Mission 3 (Capture, Remember & Follow-Through) Remember decision: Hub
// deliberately gets NO dedicated Remember section. useNumberOneAttentionItems()
// below reads context_service.py's /brief/number-one `attention_items`
// field, which now additively includes Personal Task Attention Adapter
// output (core/coordination/personal_task_attention_adapter.py) alongside
// Number One's own items — the exact same field Captain's Chair's Needs
// You reads. That means NEEDS_NOW/DECISION_REQUIRED-tier personal tasks
// already surface here today, through the one canonical pipe, with zero
// Hub-specific code. Remember's broader content (IMPORTANT_NOT_IMMEDIATE-
// tier resurfacing + unresolved captured_items, via GET /remember) is
// intentionally Chair-only: Hub's own mandate above ("not a mini
// Captain's Chair", quiets itself under reduced capacity) argues against
// a second, broader attention section here. Do not add one without first
// re-reading this note — it would duplicate Chair's Remember panel
// (captains-chair-workbench/_components/Remember.tsx) rather than add
// new information.
//
// Mission 6B addendum (2026-09-19 Hub closure pass): the "pick up where
// you left off" card below is NOT the Remember panel this note warns
// against — Remember is IMPORTANT_NOT_IMMEDIATE-tier resurfacing +
// unresolved captures (a breadth of things worth remembering); this is a
// single already-in-progress, explicitly-paused task the Captain
// themselves started (interruption recovery, Mission 4's PickUpBanner
// concept). Capped at exactly one item, using pickUpItems()'s existing
// selection logic verbatim — if this ever needs a second item or its own
// "show more," that would be scope creep back into Remember and should be
// re-read against this note first.

import { useEffect, useState } from 'react';
import Link from 'next/link';
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
  useNumberOneAttentionItems,
} from '@/lib/captainsChairData';
import { useAlerts } from '@/lib/useAlerts';
import { deriveCommandStatus } from '@/lib/captainsChairSynthesis';
import { deriveCommandPosture, buildNeedsYouItems, deriveIntelligenceHeadline } from '@/lib/commandState';
import { playTts, type TtsPlaybackState } from '@/lib/ttsPlayer';
import { useWakeLock } from '@/lib/useWakeLock';
import { fetchTasks, pickUpItems, type PersonalTask } from '@/lib/personalTasks';
import { systemPostureStatus, type SystemPostureBand } from '@/app/human-systems-workbench/_components/types';
import { stateToneClasses } from '@/lib/departments';
import type { StateTone } from '@/lib/types';

const POSTURE_TONE_CLASS: Record<string, string> = {
  RESPOND: 'text-state-crit',
  RECOVER: 'text-state-crit',
  PROTECT: 'text-state-warn',
  FOCUS: 'text-state-ok',
  STEADY: 'text-state-ok',
  UNKNOWN: 'text-state-unknown',
};

// Endeavour 27 (USS-TJR-MSN-0394) Stream B: the mockup's 4-tile status grid
// (Capacity/Focus/In Progress/Wellbeing). Reuses the real canonical posture
// judgement (systemPostureStatus(), human-systems-workbench's own badge-
// status map) rather than inventing a second tone scale for the same
// signal -- Capacity and Wellbeing both read off the one real Human
// Systems posture, same as the mockup's own two related-but-distinct
// framings of one assessment, not two independent measurements.
const BADGE_TO_STATE_TONE: Record<'success' | 'info' | 'warning' | 'error' | 'neutral', StateTone> = {
  success: 'ok',
  info: 'info',
  warning: 'warn',
  error: 'crit',
  neutral: 'unknown',
};

function daypartGreeting(): string {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
}

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
  const { items: numberOneAttentionItems } = useNumberOneAttentionItems();

  // Mission 6B Hub closure gap (Captain review, 2026-09-19): Hub had no
  // "where I left off" signal at all — only Ready Room's own PickUpBanner/
  // TodayStream showed a paused, restart-cued task. A Captain landing on
  // Hub after being away had to already know to open Ready Room. This is
  // deliberately NOT a second Remember panel (see this file's header note
  // above on why Remember stays Chair-only) — it's the single highest-
  // priority resumable task, reusing pickUpItems()'s existing selection
  // logic verbatim, same one already ported for Number One's "where was
  // I?" dispatcher intent in this mission.
  const [pickUpCandidate, setPickUpCandidate] = useState<PersonalTask | null>(null);
  // Endeavour 27 Stream B: the mockup's "In Progress" tile needs a real
  // count, not a placeholder -- work_state === 'in_progress' is the same
  // canonical field pickUpItems() itself already reads (personalTasks.ts),
  // fetched here once and reused for both rather than a second query.
  const [inProgressCount, setInProgressCount] = useState<number | null>(null);
  useEffect(() => {
    let alive = true;
    fetchTasks({ includeCompleted: false }).then((tasks) => {
      if (!alive) return;
      const candidates = pickUpItems(tasks);
      setPickUpCandidate(candidates[0] ?? null);
      setInProgressCount(tasks.filter((t) => t.work_state === 'in_progress').length);
    });
    return () => { alive = false; };
  }, []);

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
    emergencyFreshness: emergency?.freshness ?? 'stale',
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
    numberOneAttentionItems,
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

  // Endeavour 27 Stream B tiles — real Human Systems posture, reused for
  // both Capacity and Wellbeing (one assessment, two framings — see this
  // file's header note above).
  const postureBand = (humanSystems?.posture ?? 'UNKNOWN') as SystemPostureBand;
  const postureTone = stateToneClasses(BADGE_TO_STATE_TONE[systemPostureStatus(postureBand)]);
  const capacityLabel = humanSystems?.available_capacity ?? (postureBand === 'UNKNOWN' ? 'No check-in yet' : postureBand);
  const wellbeingLabel = postureBand === 'ENGAGE' ? 'Steady'
    : postureBand === 'STEADY' ? 'Steady'
    : postureBand === 'PROTECT' ? 'Protecting capacity'
    : postureBand === 'RESET' ? 'Regulation first'
    : postureBand === 'RECOVER' ? 'Recovering'
    : 'Unknown';

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
      // Mission 7 §35 adversarial pass: this previously read "Workbenches
      // →" — a trailing arrow with no link behind it (WorkbenchShell
      // renders `tagline` as plain text), which reads as a promised
      // affordance that goes nowhere on tap. The real path to the
      // directory is the header logo (and desktop Sidebar's own
      // Workbenches entry) — this is now honestly just a footer label.
      tagline="USS TJR · LifeOS Hub"
      mode="command"
      wide
    >
      <div className="mx-auto max-w-3xl space-y-6 py-2">
        {/* ── 0. Greeting — Endeavour 27 Stream B: reuses HomeScreen.tsx's
            daypart pattern, previously dead code since /home's retirement
            (mission §1.1) ── */}
        <p className="text-lg font-serif text-wb-ink">{daypartGreeting()}, Captain.</p>
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
              {/* HQ V1 Integration QA §24: "Stable/Steady" must never
                  silently mean "we stopped checking alerts a while ago" —
                  surface the stale collection check rather than hide it. */}
              {emergency?.freshness === 'stale' && (
                <p className="mx-auto mt-1 max-w-md text-xs text-wb-ink2">
                  Emergency alert check is overdue — may not reflect the latest alerts.
                </p>
              )}
            </>
          )}
        </div>

        {/* ── 2b. Status tiles — Endeavour 27 Stream B (mission §1.1's
            4-tile grid), each wired to the same real data this page
            already computed above, not a second data source. ── */}
        {!stillLoading && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-lg border border-wb-line bg-wb-surface p-3">
              <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Capacity</p>
              <p className={`mt-0.5 text-sm font-semibold ${postureTone.text}`}>{capacityLabel}</p>
            </div>
            <div className="rounded-lg border border-wb-line bg-wb-surface p-3">
              <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Focus</p>
              <p className="mt-0.5 text-sm font-semibold text-wb-ink">
                {needsYouItems.length} {needsYouItems.length === 1 ? 'priority' : 'priorities'}
              </p>
            </div>
            <div className="rounded-lg border border-wb-line bg-wb-surface p-3">
              <p className="text-[10px] uppercase tracking-wider text-wb-ink2">In Progress</p>
              <p className="mt-0.5 text-sm font-semibold text-wb-ink">
                {inProgressCount === null ? '—' : `${inProgressCount} ${inProgressCount === 1 ? 'task' : 'tasks'}`}
              </p>
            </div>
            <div className="rounded-lg border border-wb-line bg-wb-surface p-3">
              <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Wellbeing</p>
              <p className={`mt-0.5 text-sm font-semibold ${postureTone.text}`}>{wellbeingLabel}</p>
            </div>
          </div>
        )}

        {!stillLoading && (
          <>
            {/* ── 3. Next commitments — only meaningful upcoming Calendar items ── */}
            {!sanctuary && (
              <div className="rounded-lg border border-wb-line bg-wb-surface p-4">
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

            {/* ── 4. Needs You — prefer 0–3 genuinely actionable items ──
                Mission 7 §7/§8/§22: each item's actionLabel (deriveCommandStatus
                already assigns one per source — "Review", "Publish / Schedule",
                "Do this") existed but rendered as trailing 11px text easy to miss
                entirely, which is what let this section read as an announcement
                with nowhere to go rather than something to act on. Now a real
                button-styled affordance, still the item's one canonical href —
                no second engine, no invented action, just made visible. */}
            <div className="rounded-lg border border-wb-line bg-wb-surface p-4">
              <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-wb-ink2">Needs You</h2>
              {needsYouItems.length === 0 ? (
                <p className="text-sm font-medium text-wb-ink2">✓ Nothing needs your attention.</p>
              ) : (
                <ul className="space-y-2">
                  {needsYouItems.slice(0, 3).map((item) => (
                    <li key={item.id}>
                      <Link
                        href={item.href}
                        className="group flex items-center gap-3 rounded-md p-1.5 -m-1.5 transition-colors hover:bg-wb-surface-raised focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
                      >
                        <span className="min-w-0 flex-1 text-sm">
                          <span className="font-semibold text-wb-ink group-hover:underline">{item.title}</span>
                          <span className="text-wb-ink2"> — {item.detail}</span>
                        </span>
                        <span className="shrink-0 rounded-md bg-wb-sage-deep px-2.5 py-1 text-[11px] font-semibold text-white">
                          {item.actionLabel}
                        </span>
                      </Link>
                      {/* Mission 7 item 2: same task, straight into Unstick
                          Me — Captain's choice alongside "Do this", not a
                          second engine deciding which tasks need it. */}
                      {item.helpMeStartHref && (
                        <Link
                          href={item.helpMeStartHref}
                          className="mt-1 inline-block rounded-md border border-wb-line px-2.5 py-1 text-[11px] font-semibold text-wb-ink2 hover:border-wb-sage-deep hover:text-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
                        >
                          Help me start
                        </Link>
                      )}
                    </li>
                  ))}
                  {needsYouItems.length > 3 && (
                    <li className="text-xs text-wb-ink2">
                      +{needsYouItems.length - 3} more — see{' '}
                      <Link href="/captains-chair-workbench" className="text-wb-sage-deep hover:underline">Captain&apos;s Chair</Link>
                    </li>
                  )}
                </ul>
              )}
            </div>

            {/* ── 4b. Pick up where you left off — at most one item, distinct
                from Needs You (this is the Captain's own paused work
                resuming, not something newly requiring attention) ── */}
            {pickUpCandidate && (
              <div className="rounded-lg border border-wb-sage/40 bg-wb-sage/10 p-4">
                <h2 className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-wb-sage-deep">Pick up where you left off</h2>
                <Link
                  href={`/ready-room?task=${encodeURIComponent(pickUpCandidate.id)}`}
                  className="group focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
                >
                  <span className="text-sm font-semibold text-wb-ink group-hover:underline">{pickUpCandidate.title}</span>
                </Link>
                {pickUpCandidate.restart_cue && (
                  <p className="mt-0.5 text-xs text-wb-ink2">{pickUpCandidate.restart_cue}</p>
                )}
              </div>
            )}

            {/* ── 4c. Quick Access — mission §1.1's peer card, every link an
                existing real destination, no new capability. ── */}
            <div className="rounded-lg border border-wb-line bg-wb-surface p-4">
              <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-wb-ink2">Quick Access</h2>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <Link href="/capture-workbench" className="rounded-md border border-wb-line px-2.5 py-2 text-center text-[12px] font-medium text-wb-ink2 hover:border-wb-sage-deep hover:text-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
                  Capture a thought
                </Link>
                <Link href="/ready-room" className="rounded-md border border-wb-line px-2.5 py-2 text-center text-[12px] font-medium text-wb-ink2 hover:border-wb-sage-deep hover:text-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
                  Open Ready Room
                </Link>
                <Link href="/ready-room?domain=do" className="rounded-md border border-wb-line px-2.5 py-2 text-center text-[12px] font-medium text-wb-ink2 hover:border-wb-sage-deep hover:text-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
                  View Today Stream
                </Link>
                <Link href="/advisory-workbench?advisor=number_one" className="rounded-md border border-wb-line px-2.5 py-2 text-center text-[12px] font-medium text-wb-ink2 hover:border-wb-sage-deep hover:text-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
                  Ask Number One
                </Link>
              </div>
            </div>

            {/* ── 5. World / intelligence — one headline or honest unknown ── */}
            {!hideWorldSection && (
              <div className="rounded-lg border border-wb-line bg-wb-surface p-4">
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

            {/* ── 7. Calm end state + Read aloud + Ask Number One ── */}
            <div className="flex flex-col items-center gap-2 pt-2">
              {needsYouItems.length === 0 && (
                <p className="text-sm text-wb-ink2">Nothing else needs you.</p>
              )}
              {/* Mission 6B Hub closure gap: Number One's new orchestration
                  capability was previously reachable only by knowing to
                  open Workbenches -> Advisory -> Think -> Advanced -> Number
                  One.
                  Mission 7 update: the ambient Number One widget
                  (components/ui/NumberOne.tsx, mounted globally via
                  WorkbenchShell — the sparkle button, bottom-left) now
                  covers the quick "what matters / I'm stuck / not now"
                  cases this link used to be the only way to reach, in two
                  taps with no page leave. This link is kept, reworded, for
                  the genuinely different job it still does: a full,
                  persisted, multi-turn thread (ConsultView saves the
                  conversation) rather than the widget's ephemeral
                  per-session turns — two purposes, not duplicate
                  navigation for the same one (mission §17). */}
              <Link
                href="/advisory-workbench?advisor=number_one"
                className="text-[11px] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
              >
                Open a full Number One session
              </Link>
              <button
                type="button"
                onClick={speakCommandPicture}
                disabled={speakState === 'generating' || speakState === 'playing'}
                className="text-[11px] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep disabled:cursor-not-allowed disabled:opacity-60 disabled:no-underline"
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
