'use client';

// Shared data layer for Captain's Chair (captains-chair-workbench) and the
// LifeOS Hub (/hub) — extracted 2026-09-05 so the trimmed Hub glance page
// and the full Captain's Chair workbench don't duplicate/drift on the same
// fetch logic. Nothing here changes behavior, it's a straight lift of what
// was previously defined locally in captains-chair-workbench/page.tsx.

import { useEffect, useState } from 'react';
import { fetchTasks, attendBucket, type PersonalTask } from '@/lib/personalTasks';
import type { RecoveryPostureBand, StateTone } from '@/lib/types';

// ── Situation strip tone/label maps ──────────────────────────────────────────

export const POSTURE_STATE_TONE: Record<RecoveryPostureBand, StateTone> = {
  STRONG: 'ok',
  STABLE: 'ok',
  FRAGILE: 'warn',
  REST: 'crit',
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

// HQ V1 Integration QA §24 finding: `is_active=true` rows never expire
// themselves — only a *successful* collection cycle flips a gone alert to
// inactive (intelligence/emergency_alerts.py's _expire_stale). If collection
// stops (scheduler down), an active alert — or a genuine all-clear — reads
// as current indefinitely, with nothing here to say otherwise. Mirrors the
// exact staleness threshold the Emergency Alert Hub Workbench's own
// CoveragePanel already uses (90 min = 6 missed 15-min collection cycles,
// see emergency-alert-hub-workbench/page.tsx's STALE_THRESHOLD_MS) against
// the same /api/emergency-alerts/sources heartbeat contract, so "Clear" here
// can never mean "we stopped checking a while ago."
const EMERGENCY_STALE_THRESHOLD_MS = 90 * 60 * 1000;

export interface EmergencyAlertsSummary {
  worstTier: 'emergency_warning' | 'watch_and_act' | null;
  count: number;
  worstHeadline: string | null;
  /** 'fresh' = at least one source's collection heartbeat is within the
   *  threshold; 'stale' = every source's last collection is older than
   *  that (or none ever ran); this app never claims 'unknown' distinct
   *  from 'stale' here — both mean "don't trust this as current." */
  freshness: 'fresh' | 'stale';
  lastCheckedAt: string | null;
}

export function useEmergencyAlerts(): { data: EmergencyAlertsSummary | null; loading: boolean; error: string | null } {
  const [data, setData] = useState<EmergencyAlertsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [alertsRes, sourcesRes] = await Promise.all([
          fetch('/api/emergency-alerts?activeOnly=true'),
          fetch('/api/emergency-alerts/sources'),
        ]);
        if (!alertsRes.ok) throw new Error(`Emergency alerts unavailable (${alertsRes.status})`);
        const body = await alertsRes.json();
        if (cancelled) return;

        // Source-health fetch failing must not hide a real alert — fall
        // back to 'stale' (never silently 'fresh') rather than throwing.
        let lastCheckedAt: string | null = null;
        if (sourcesRes.ok) {
          const sourcesBody = await sourcesRes.json();
          const sources: { lastRun: string | null }[] = Array.isArray(sourcesBody?.sources) ? sourcesBody.sources : [];
          for (const s of sources) {
            if (s.lastRun && (!lastCheckedAt || s.lastRun > lastCheckedAt)) lastCheckedAt = s.lastRun;
          }
        }
        const freshness: EmergencyAlertsSummary['freshness'] =
          lastCheckedAt && Date.now() - new Date(lastCheckedAt).getTime() <= EMERGENCY_STALE_THRESHOLD_MS
            ? 'fresh'
            : 'stale';

        const alerts: { severity: string; headline: string }[] = Array.isArray(body?.alerts) ? body.alerts : [];
        const urgent = alerts.filter((a) => a.severity === 'emergency_warning' || a.severity === 'watch_and_act');
        const worst = urgent.find((a) => a.severity === 'emergency_warning') ?? urgent[0] ?? null;
        setData({
          worstTier: (worst?.severity as EmergencyAlertsSummary['worstTier']) ?? null,
          count: urgent.length,
          worstHeadline: worst?.headline ?? null,
          freshness,
          lastCheckedAt,
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

// ── Agent/Job health ──────────────────────────────────────────────────────────

export interface AgentHealthSummary {
  failedCount: number;
  worstLabel: string | null;
}

export function useAgentHealth(): { data: AgentHealthSummary | null; loading: boolean; error: string | null } {
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
        console.error('[captainsChairData] useAgentHealth failed:', e);
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

// ── Capacity Today (lean — /hub only needs capacityState + postureMessage,
// not the full Signal Snapshot's OSINT/health cross-section) ───────────────

export interface CapacityToday {
  capacityState: string | null;
  postureMessage: string | null;
}

export function useCapacityToday(): { data: CapacityToday; loading: boolean; error: string | null } {
  const [data, setData] = useState<CapacityToday>({ capacityState: null, postureMessage: null });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/human-systems?domain=recovery')
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((wellness) => {
        if (cancelled) return;
        setData({
          capacityState: wellness?.latest_capacity_state ?? null,
          postureMessage: wellness?.system_posture_message ?? null,
        });
        setError(null);
      })
      .catch((e) => {
        console.error('[captainsChairData] useCapacityToday failed:', e);
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load capacity');
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return { data, loading, error };
}
