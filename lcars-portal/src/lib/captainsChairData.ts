'use client';

// Shared data layer for Captain's Chair (captains-chair-workbench) and the
// LifeOS Hub (/hub) — extracted 2026-09-05 so the trimmed Hub glance page
// and the full Captain's Chair workbench don't duplicate/drift on the same
// fetch logic. Nothing here changes behavior, it's a straight lift of what
// was previously defined locally in captains-chair-workbench/page.tsx.

import { useEffect, useState } from 'react';
import { fetchTasks, attendBucket, type PersonalTask } from '@/lib/personalTasks';
import { fetchCaptureAnalytics, fetchInboxCaptures } from '@/lib/capture';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import type { StateTone } from '@/lib/types';
import type { SystemPostureBand } from '@/app/human-systems-workbench/_components/types';
import type { AssessedContext } from '@/app/api/human-systems/assessed-context';

// ── Situation strip tone/label maps ──────────────────────────────────────────

/** Tone for the canonical Human Systems posture band (assessed-context.ts /
 * deriveSystemPosture). This is the ONLY posture-tone map Captain's Chair
 * and LifeOS should use — see useHumanSystemsContext() below for why. */
export const SYSTEM_POSTURE_STATE_TONE: Record<SystemPostureBand, StateTone> = {
  ENGAGE: 'ok',
  STEADY: 'ok',
  PROTECT: 'warn',
  RESET: 'warn',
  RECOVER: 'crit',
  UNKNOWN: 'unknown',
};

export const RISK_STATE_TONE: Record<string, StateTone> = {
  GREEN: 'ok',
  AMBER: 'warn',
  RED: 'crit',
};

export const CAPACITY_STATE_LABEL: Record<string, string> = {
  green: 'Sustainable',
  orange: 'Stretched',
  red: 'Depleted',
};

// ── Human Systems (canonical assessed context) ───────────────────────────────
//
// This is the ONE Human Systems read Captain's Chair and LifeOS are allowed
// to use. It hits /api/human-systems/context — the same small, fresh/stale-
// aware boundary Ready Room and Weekly Review already consume (see
// assessed-context.ts) — instead of the retired get_recovery_posture() RPC
// (useROSData/ros-data.ts, which reads from analytics_health_daily, a view
// over tables capacity_checkins replaced). Command-surface correctness
// repair (P0): both pages previously derived posture from useROSData()'s
// `?? mockPosture` fallback, so "no check-in today" (a real, empty result)
// rendered identically to a fabricated STABLE/MODERATE day. The canonical
// path never does this — deriveSystemPosture(null) returns UNKNOWN with an
// honest message, no mock fallback exists here at all.
export function useHumanSystemsContext(): {
  context: AssessedContext | null;
  loading: boolean;
  /** True only when the /context fetch itself failed — distinct from a
   *  successful response reporting has_checkin_today: false. */
  error: string | null;
} {
  const [context, setContext] = useState<AssessedContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/human-systems/context')
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((body: AssessedContext) => {
        if (cancelled) return;
        setContext(body);
        setError(null);
      })
      .catch((e) => {
        console.error('[captainsChairData] useHumanSystemsContext failed:', e);
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load Human Systems context');
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return { context, loading, error };
}

// ── Operational Risk ──────────────────────────────────────────────────────────

export interface OperationalRiskData {
  overallRisk: string | null;
  escalateCount: number;
}

export function useOperationalRisk(): { data: OperationalRiskData | null; loading: boolean; error: string | null } {
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
        console.error('[captainsChairData] useOperationalRisk failed:', e);
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

// ── Emergency Alerts summary ──────────────────────────────────────────────────

export interface EmergencyAlertsSummary {
  worstTier: 'emergency_warning' | 'watch_and_act' | null;
  count: number;
  worstHeadline: string | null;
}

export function useEmergencyAlerts(): { data: EmergencyAlertsSummary | null; loading: boolean; error: string | null } {
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
        const urgent = alerts.filter((a) => a.severity === 'emergency_warning' || a.severity === 'watch_and_act');
        const worst = urgent.find((a) => a.severity === 'emergency_warning') ?? urgent[0] ?? null;
        setData({
          worstTier: (worst?.severity as EmergencyAlertsSummary['worstTier']) ?? null,
          count: urgent.length,
          worstHeadline: worst?.headline ?? null,
        });
        setError(null);
      } catch (e) {
        console.error('[captainsChairData] useEmergencyAlerts failed:', e);
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

// ── HQ Status (canonical interpreted summary) ────────────────────────────────
//
// Command-Experience vNext (Phase 2): replaces the old useAgentHealth() hook,
// which re-derived a "failing jobs" count from the raw /api/agent-status job
// list — a second, cruder HQ-health interpretation living outside HQ
// Status's own module. hqStatusInterpreter.ts already builds a small,
// stable, posture-first summary (buildCaptainChairSummary()) specifically
// for Captain's Chair/LifeOS consumption; this hook reads that instead, so
// HQ health has exactly one interpretation, not two disagreeing ones.

export interface HqStatusSummary {
  posture: 'NORMAL' | 'DEGRADED' | 'ATTENTION' | 'UNKNOWN';
  summary: string;
  needsAttentionCount: number;
  attentionItems: Array<{ title: string; detail: string }>;
}

export function useHqStatusSummary(): { data: HqStatusSummary | null; loading: boolean; error: string | null } {
  const [data, setData] = useState<HqStatusSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch('/api/agent-status-workbench/overview');
        if (!res.ok) throw new Error(`HQ Status unavailable (${res.status})`);
        const body = await res.json();
        if (cancelled) return;
        setData({
          posture: body?.captainSummary?.hq_posture ?? 'UNKNOWN',
          summary: body?.captainSummary?.summary ?? body?.headline ?? 'HQ status unknown',
          needsAttentionCount: body?.needsAttentionCount ?? 0,
          attentionItems: Array.isArray(body?.attentionItems) ? body.attentionItems : [],
        });
        setError(null);
      } catch (e) {
        console.error('[captainsChairData] useHqStatusSummary failed:', e);
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load HQ status');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  return { data, loading, error };
}

// ── Today's Brief (interrupt-now count feeds the situation strip) ───────────

export interface TodaysBriefingStats {
  confidence: number | null;
  priorities: number;
  warnings: number;
  recommendations: number;
  nextActions: number;
  interruptNow: number;
}

export function useTodaysBriefing(): {
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

// ── Calendar ───────────────────────────────────────────────────────────────

export interface CalendarTodayEvent {
  time: string | null;
  title: string;
  location: string | null;
  allDay: boolean;
}

export type CalendarTodayStatus = 'ok' | 'disconnected' | 'error';

export function useCalendarToday(): {
  events: CalendarTodayEvent[];
  status: CalendarTodayStatus;
  loading: boolean;
} {
  const [events, setEvents] = useState<CalendarTodayEvent[]>([]);
  const [status, setStatus] = useState<CalendarTodayStatus>('ok');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch('/api/calendar/today');
        const body = await res.json().catch(() => null);
        if (cancelled) return;
        if (res.status === 409 || body?.status === 'disconnected') {
          setStatus('disconnected');
          setEvents([]);
        } else if (!res.ok || body?.status === 'error') {
          setStatus('error');
          setEvents([]);
        } else {
          setStatus('ok');
          setEvents(Array.isArray(body?.events) ? body.events : []);
        }
      } catch (e) {
        console.error('[captainsChairData] useCalendarToday failed:', e);
        if (!cancelled) {
          setStatus('error');
          setEvents([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  return { events, status, loading };
}

// ── Calendar, beyond today (MSN-0364, Captain's Chair "Ahead") ─────────────

export interface UpcomingCalendarEvent {
  time: string | null;
  title: string;
  location: string | null;
  allDay: boolean;
  dateISO: string;
}

export function useCalendarUpcoming(days = 2): {
  events: UpcomingCalendarEvent[];
  status: CalendarTodayStatus;
  loading: boolean;
} {
  const [events, setEvents] = useState<UpcomingCalendarEvent[]>([]);
  const [status, setStatus] = useState<CalendarTodayStatus>('ok');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch(`/api/calendar/upcoming?days=${days}`);
        const body = await res.json().catch(() => null);
        if (cancelled) return;
        if (res.status === 409 || body?.status === 'disconnected') {
          setStatus('disconnected');
          setEvents([]);
        } else if (!res.ok || body?.status === 'error') {
          setStatus('error');
          setEvents([]);
        } else {
          setStatus('ok');
          setEvents(Array.isArray(body?.events) ? body.events : []);
        }
      } catch (e) {
        console.error('[captainsChairData] useCalendarUpcoming failed:', e);
        if (!cancelled) {
          setStatus('error');
          setEvents([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [days]);

  return { events, status, loading };
}

// ── Reminders ──────────────────────────────────────────────────────────────

export function useReminders(): { tasks: PersonalTask[]; loading: boolean } {
  const [tasks, setTasks] = useState<PersonalTask[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchTasks({ limit: 100 })
      .then((all) => {
        if (cancelled) return;
        const due = all
          .filter((t) => attendBucket(t) === 'now' && !t.follow_through_paused)
          .sort((a, b) => (b.nudge_count - a.nudge_count) || (b.urgency - a.urgency));
        setTasks(due.slice(0, 5));
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return { tasks, loading };
}

// ── Needs You raw inputs (Content/Capture/Wellness/Notebook/Evolution) ──────
//
// Moved here from captains-chair-workbench/page.tsx (Command-Experience
// vNext, Phase 2) so LifeOS can feed commandState.ts's buildNeedsYouItems()
// the exact same inputs Captain's Chair does — mission requirement: "no
// duplicate Needs You logic exists between Captain and LifeOS." Sharing the
// fetch here, not just the interpretation, is what keeps them unable to
// disagree on "what needs you."

export interface AttentionCounts {
  contentAwaitingPublish: number | null;
  capturePending: number | null;
  wellnessRiskFlags: number | null;
  oldestContentAwaitingPublish: string | null;
  oldestCapturePending: string | null;
}

export function useAttentionCounts(): { data: AttentionCounts; loading: boolean; errors: string[] } {
  const [data, setData] = useState<AttentionCounts>({
    contentAwaitingPublish: null,
    capturePending: null,
    wellnessRiskFlags: null,
    oldestContentAwaitingPublish: null,
    oldestCapturePending: null,
  });
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const errs: string[] = [];

      const content = await fetch('/api/content-workbench')
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
        .catch((e) => { console.error('[captainsChairData] content pipeline count failed:', e); errs.push('Content pipeline'); return null; });

      const capture = await fetchCaptureAnalytics();
      if (capture === null) { console.error('[captainsChairData] capture pending count failed'); errs.push('Capture pending'); }

      const oldestCapture = await fetchInboxCaptures({ statusFilter: 'pending', limit: 50 })
        .then((rows) => rows.length > 0 ? rows[rows.length - 1] : null)
        .catch((e) => { console.error('[captainsChairData] oldest pending capture failed:', e); return null; });

      const wellness = await fetch('/api/human-systems?domain=recovery')
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
        .catch((e) => { console.error('[captainsChairData] wellness risk flags failed:', e); errs.push('Wellness signals'); return null; });

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
      setErrors(errs);
      setLoading(false);
    }
    load();
    return () => { cancelled = true; };
  }, []);

  return { data, loading, errors };
}

/** HQ Evolution's small morning signal (spec §37) — a count + the
 * highest-value opportunity, never the full Discover/Investigate/Improve/
 * Learned surface. Reuses the same summary endpoint the HQ Evolution page
 * itself uses for morning compression. */
export function useEvolutionSignal(): { pendingCount: number | null; highestValueTitle: string | null; error: string | null } {
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
      .catch((e) => { if (!cancelled) { console.error('[captainsChairData] HQ Evolution summary failed:', e); setError('HQ Evolution'); } });
    return () => { cancelled = true; };
  }, []);

  return { pendingCount, highestValueTitle, error };
}

/** Minimal slice of the old NotebookCard's fetch — just the ready-for-
 * routing count. Full detail is one click away, in Captain's Chair's
 * Notebook sub-page. */
export function useNotebookReadyCount(): { readyCount: number | null; error: string | null } {
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
