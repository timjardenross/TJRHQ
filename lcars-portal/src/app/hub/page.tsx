'use client';

// LifeOS Hub — 2026-09-05, per Captain's design session extending
// docs/LifeOS-Wall-Tablet-V1-Component-Scope.md. The always-on/unattended
// wall-display design intent from that doc is unchanged (kiosk device auth
// §2.5, auto-cycling panels — none of that is built, it's just moot for
// now since an iPad with normal login is standing in for real kiosk
// hardware while the Captain evaluates devices). This page IS the eventual
// kiosk's content: a deliberately trimmed, glance-from-across-the-room
// subset of Captain's Chair, not a re-derivation of it — Captain's Chair
// itself is untouched and stays the full executive-summary workbench.
//
// Cut vs Captain's Chair (Captain's own call): the 3 "Needs Attention"
// count tiles (Content Awaiting Publish/Capture Pending/Wellness Risk
// Flags — workbench-triage detail, not household-glance material), Top
// OSINT Signal (the consultancy/business pipeline, not home-relevant),
// Top Health Signal (deferred for now, Captain's call), Today's Briefing
// card + the separate Today's Brief panel (both "read in detail," not
// glance), and the Notebook card.
//
// Architecture: /hub is the new start_url (manifest.webmanifest) — the
// front door. The WorkbenchShell logo click goes to /workbenches (the
// full directory) — "workbenches behind it," one tap away. Captain's
// Chair is just one of those workbenches now, reachable the same as any
// other, not the same page as this one.
//
// Command-Experience correctness repair (P0, 2026-09-06): the Recovery
// Posture badge used to read useROSData() (the retired get_recovery_
// posture() RPC, `?? mockPosture` fallback) — a day with no capacity
// check-in silently rendered a fabricated STABLE posture. It now reads
// useHumanSystemsContext() (/api/human-systems/context), the same
// canonical assessed-context.ts boundary Ready Room and Captain's Chair
// consume — see docs/architecture/COMMAND-EXPERIENCE.md. Both surfaces
// now agree on Human Systems state; neither can show a mock value as
// current truth.

import Link from 'next/link';
import { useState } from 'react';
import { WorkbenchShell } from '@/components/ui';
import { SituationBadge } from '@/components/SituationBadge';
import { TodaysBriefPanel } from '@/components/TodaysBriefPanel';
import { stateToneClasses, alertSeverityToTone } from '@/lib/departments';
import { useAlerts } from '@/lib/useAlerts';
import { categoryMeta } from '@/lib/personalTasks';
import {
  CAPACITY_STATE_LABEL,
  RISK_STATE_TONE,
  SYSTEM_POSTURE_STATE_TONE,
  useHumanSystemsContext,
  useOperationalRisk,
  useEmergencyAlerts,
  useAgentHealth,
  useTodaysBriefing,
  useCalendarToday,
  useReminders,
} from '@/lib/captainsChairData';
import { playTts, type TtsPlaybackState } from '@/lib/ttsPlayer';
import { useWakeLock } from '@/lib/useWakeLock';
import type { StateTone } from '@/lib/types';

export default function LifeOSHub() {
  // Always-on wall-tablet use (this page's whole purpose) — keeps the
  // screen awake while it's open. Deliberately only on this page, not
  // Captain's Chair or any other workbench, since those aren't meant to
  // stay open 24/7. Still needs Auto-Lock set to Never / Guided Access /
  // Configurator kiosk mode on the device itself — this covers "someone
  // forgot to set that," not the reboot/power-loss case.
  useWakeLock();

  const { context: humanSystems, error: humanSystemsError } = useHumanSystemsContext();
  const { alerts: liveAlerts, isLoading: alertsLoading, failedSources: alertsFailedSources, totalSources: alertsTotalSources } = useAlerts();
  const { data: opRisk, loading: opRiskLoading, error: opRiskError } = useOperationalRisk();
  const { stats: briefingStats, loading: briefingLoading, error: briefingError } = useTodaysBriefing();
  const { data: emergency, loading: emergencyLoading, error: emergencyError } = useEmergencyAlerts();
  const { data: agentHealth, loading: agentHealthLoading, error: agentHealthError } = useAgentHealth();
  const { events: calendarEvents, status: calendarStatus, loading: calendarLoading } = useCalendarToday();
  const { tasks: reminders, loading: remindersLoading } = useReminders();

  const hasCheckinToday = humanSystems?.has_checkin_today ?? false;
  const postureBand = humanSystems?.posture ?? 'UNKNOWN';
  const postureTone = SYSTEM_POSTURE_STATE_TONE[postureBand];
  const riskTone = opRisk?.overallRisk ? (RISK_STATE_TONE[opRisk.overallRisk] ?? 'unknown') : 'unknown';
  const interruptTone: StateTone = (briefingStats?.interruptNow ?? 0) > 0 ? 'crit' : 'ok';
  const emergencyTone: StateTone = emergency?.worstTier === 'emergency_warning' ? 'crit' : emergency?.worstTier === 'watch_and_act' ? 'warn' : 'ok';
  const agentHealthTone: StateTone = (agentHealth?.failedCount ?? 0) > 0 ? 'crit' : 'ok';

  const [speakState, setSpeakState] = useState<TtsPlaybackState>('idle');

  // 2026-09-05: switched from browser SpeechSynthesis (src/lib/speakAloud.ts,
  // five confirmed iOS Safari bugs in a row) to real generated audio via
  // <audio> playback. Backend went through two iterations same day:
  // self-hosted Chatterbox (Nano — too fast, unintelligible; Turbo —
  // intelligible, but ~66s/request on this VM's CPU) then Google Cloud
  // TTS (Neural2 — fast and clear, current default; see /api/tts/speak
  // for the full history).
  function speakAlertsAloud() {
    const parts: string[] = [];
    if (emergency?.count) {
      parts.push(`${emergency.count} active emergency alert${emergency.count === 1 ? '' : 's'}${emergency.worstHeadline ? `. Worst: ${emergency.worstHeadline}` : ''}.`);
    } else {
      parts.push('No active emergency alerts.');
    }
    const interruptNow = briefingStats?.interruptNow ?? 0;
    if (interruptNow > 0) {
      parts.push(`${interruptNow} item${interruptNow === 1 ? '' : 's'} need you right now.`);
    }
    if (liveAlerts.length > 0) {
      parts.push(`Top alert: ${liveAlerts[0].title}.`);
    }
    // cacheKey kept for backward compatibility (see ttsPlayer.ts/
    // /api/tts/speak) but unused now that Google Cloud TTS is fast
    // enough that caching isn't needed here.
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
      <div className="space-y-4">
        {/* ── Situation strip ── */}
        <div className="flex flex-col flex-wrap gap-3 sm:flex-row">
          <SituationBadge
            label="Recovery Posture"
            value={humanSystemsError ? 'Data error' : !hasCheckinToday ? 'No check-in' : postureBand}
            tone={humanSystemsError ? 'unknown' : postureTone}
            sublabel={
              humanSystemsError
                ? 'Check connection — see console'
                : !hasCheckinToday
                  ? 'No check-in today'
                  : (CAPACITY_STATE_LABEL[humanSystems?.available_capacity ?? ''] ?? 'No data')
            }
            href="/human-systems-workbench"
          />
          <SituationBadge
            label="Operational Risk"
            value={opRiskLoading ? '…' : opRiskError ? 'Unknown' : (opRisk?.overallRisk ?? 'No data')}
            tone={opRiskError ? 'unknown' : riskTone}
            sublabel={opRisk && opRisk.escalateCount > 0 ? `${opRisk.escalateCount} threat${opRisk.escalateCount === 1 ? '' : 's'} at escalate` : undefined}
            href="/intelligence-workbench"
          />
          <SituationBadge
            label="Interrupt Now"
            value={briefingLoading ? '…' : briefingError ? 'Unknown' : `${briefingStats?.interruptNow ?? 0}`}
            tone={briefingError ? 'unknown' : interruptTone}
            sublabel={(briefingStats?.interruptNow ?? 0) > 0 ? 'Needs you right now' : undefined}
            href="/captains-brief-workbench"
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

        {(postureBand === 'PROTECT' || postureBand === 'RECOVER' || postureBand === 'RESET') && !humanSystemsError && hasCheckinToday && (
          <div className={postureBand === 'RECOVER' ? 'rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3' : 'rounded-lg border border-wb-warn/40 bg-wb-warn/10 p-3'}>
            <p className={postureBand === 'RECOVER' ? 'text-sm text-wb-crit-on' : 'text-sm text-wb-warn-on'}>
              Recovery posture is {postureBand} — consider deferring anything below that isn&apos;t genuinely urgent.
            </p>
          </div>
        )}

        {/* P0 correctness repair: "no check-in today" must never render as
            a healthy/clear posture — this reads honestly as unknown rather
            than silently disappearing or falling back to a mock value. */}
        {!hasCheckinToday && !humanSystemsError && (
          <div className="rounded-lg border border-wb-line bg-wb-bg/50 p-3">
            <p className="text-sm text-wb-ink2">No capacity check-in yet today — recovery posture is unknown.</p>
          </div>
        )}

        {/* ── Live Alerts ── */}
        <div className="rounded-lg border border-wb-line bg-white p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-wb-ink">Live Alerts</h2>
            <div className="flex items-center gap-3">
              {alertsFailedSources > 0 && (
                <span className="text-[10px] text-wb-ink2">{alertsFailedSources} of {alertsTotalSources} sources unavailable</span>
              )}
              <button
                type="button"
                onClick={speakAlertsAloud}
                disabled={speakState === 'generating' || speakState === 'playing'}
                className="text-[11px] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep disabled:opacity-60 disabled:no-underline"
              >
                {speakState === 'generating' ? 'Generating…' : speakState === 'playing' ? '🔊 Playing…' : speakState === 'error' ? '⚠️ Failed — retry' : '🔊 Read aloud'}
              </button>
            </div>
          </div>
          {alertsLoading ? (
            <p className="text-xs text-wb-ink2 animate-pulse">Loading…</p>
          ) : liveAlerts.length === 0 ? (
            <p className="text-xs text-wb-ink2">No alerts.</p>
          ) : (
            <ul className="space-y-2">
              {liveAlerts.slice(0, 5).map((alert) => (
                <li key={alert.id} className={`border-l-2 ${stateToneClasses(alertSeverityToTone(alert.severity)).border} pl-2 text-xs`}>
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

        {/* ── Calendar + Reminders (two columns) ── */}
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border border-wb-line bg-white p-4">
            <h2 className="mb-3 text-sm font-semibold text-wb-ink">Today&apos;s Calendar</h2>
            {calendarLoading ? (
              <p className="text-xs text-wb-ink2 animate-pulse">Loading…</p>
            ) : calendarStatus === 'disconnected' ? (
              <p className="text-xs text-wb-ink2">
                Google Calendar isn&apos;t connected.{' '}
                <a href="/api/auth/google-calendar/connect" className="text-wb-sage-deep hover:underline">
                  Connect it
                </a>
                .
              </p>
            ) : calendarStatus === 'error' ? (
              <p className="text-xs text-wb-crit-on">Failed to load calendar — see console for detail.</p>
            ) : calendarEvents.length === 0 ? (
              <p className="text-xs text-wb-ink2">No events today.</p>
            ) : (
              <ul className="space-y-2">
                {calendarEvents.map((event, i) => (
                  <li key={i} className="flex items-baseline gap-2 text-xs">
                    <span className="w-14 shrink-0 font-semibold text-wb-ink">
                      {event.allDay ? 'All day' : event.time ?? '—'}
                    </span>
                    <span className="text-wb-ink">
                      {event.title}
                      {event.location && <span className="text-wb-ink2"> · {event.location}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="rounded-lg border border-wb-line bg-white p-4">
            <h2 className="mb-3 text-sm font-semibold text-wb-ink">Reminders</h2>
            {remindersLoading ? (
              <p className="text-xs text-wb-ink2 animate-pulse">Loading…</p>
            ) : reminders.length === 0 ? (
              <p className="text-xs text-wb-ink2">Nothing needs a nudge right now.</p>
            ) : (
              <ul className="space-y-2">
                {reminders.map((task) => (
                  <li key={task.id} className="flex items-start gap-2 text-xs">
                    <span className="mt-0.5 text-wb-ink2">{categoryMeta(task.category).glyph}</span>
                    <span className="flex-1 text-wb-ink">
                      {task.title}
                      {task.nudge_count > 3 && (
                        <span className="ml-1 text-wb-ink2">(nudged {task.nudge_count}×)</span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <Link href="/ready-room" className="mt-2 inline-block text-[11px] text-wb-sage-deep hover:underline">
              Ready Room →
            </Link>
          </div>
        </div>

        {/* ── Today's Briefing (real LLM-generated Executive Brief, not
              just stats — captains_daily_briefs.brief_text) ── */}
        <TodaysBriefPanel />
      </div>
    </WorkbenchShell>
  );
}
