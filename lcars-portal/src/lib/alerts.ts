/**
 * Push Alerts engine (MSN-IOS-001 WP6).
 *
 * Reuse-first: derives alerts entirely from EXISTING Supabase data via the
 * existing fetchers (loadHumanSystems, loadDelivery, fetchRecoveryPosture,
 * fetchEmotionalLoadFlag) plus a couple of targeted reads. No new alert tables.
 *
 * GUARDRAIL — every alert must answer "Why does Captain TJR need this NOW?".
 * Only five alert classes are permitted, each strictly gated. No FYI / nominal
 * alerts are ever emitted. If a condition is healthy, no alert is produced.
 *
 *   decision         — a Captain decision is required
 *   escalation       — something has escalated and needs attention
 *   delivery_failure — failed delivery / blocked mission
 *   eng_review       — high-priority engineering review waiting
 *   wellness         — critical wellness / readiness signal
 */

import { createSupabaseBrowserClient } from './supabase-browser';
import { loadHumanSystems } from './human-systems';
import { loadDelivery } from './delivery';
import { fetchRecoveryPosture, fetchEmotionalLoadFlag } from './ros-data';

// Session-aware client (2026-07-18): capacity_checkins (recovery_pulses'
// successor)/build_request_inbox/mission_execution_events either never had
// an anon grant or were tightened - same fix as ros-data.ts/human-systems.ts/
// delivery.ts. Constructed fresh per call, matching every other caller.
function client() {
  return createSupabaseBrowserClient();
}

export type AlertKind = 'decision' | 'escalation' | 'delivery_failure' | 'eng_review' | 'wellness';
export type AlertSeverity = 'critical' | 'high' | 'warning';

export interface MobileAlert {
  id: string;
  kind: AlertKind;
  severity: AlertSeverity;
  title: string;
  detail: string;
  /** The single justification gate: why this matters right now. */
  why: string;
  href: string;
  at: string; // ISO timestamp
}

export const ALERT_KIND_LABEL: Record<AlertKind, string> = {
  decision: 'Decision required',
  escalation: 'Escalation',
  delivery_failure: 'Blocked / failed',
  eng_review: 'Engineering review',
  wellness: 'Wellness',
};

const SEVERITY_RANK: Record<AlertSeverity, number> = { critical: 0, high: 1, warning: 2 };

function nowIso() {
  return new Date().toISOString();
}

// ── Wellness + escalation (reuse human-systems + ROS posture) ─────────────────

interface AlertGroupResult {
  alerts: MobileAlert[];
  /** Number of independent source fetches that errored — not exposed as an
   *  alert (keeps the "no alert better than a false alert" design intact),
   *  but surfaced as a quiet "N sources unavailable" note so a genuine
   *  outage isn't indistinguishable from a healthy "no alerts" read. */
  failed: number;
  total: number;
}

async function wellnessAlerts(): Promise<AlertGroupResult> {
  const supabase = client();
  const out: MobileAlert[] = [];
  let failed = 0;
  const total = 2;
  try {
    const [hs, posture, emo] = await Promise.all([
      loadHumanSystems(),
      fetchRecoveryPosture(),
      fetchEmotionalLoadFlag(),
    ]);

    // Red-flag escalation — highest priority of all.
    if (hs.snapshot.escalation) {
      out.push({
        id: 'wellness-redflag',
        kind: 'escalation',
        severity: 'critical',
        title: 'Health red flag detected',
        detail: hs.snapshot.escalation,
        why: 'A safety-relevant signal was logged. This needs attention before anything operational.',
        href: '/medical',
        at: nowIso(),
      });
    }

    // Posture REST or depleted capacity — critical readiness signal.
    const restPosture = posture?.posture === 'REST';
    const depleted = hs.snapshot.dataAvailable && hs.snapshot.overallBand === 'depleted';
    if (restPosture || depleted) {
      out.push({
        id: 'wellness-capacity-critical',
        kind: 'wellness',
        severity: 'critical',
        title: restPosture ? 'Recovery posture: REST' : 'Capacity depleted',
        detail: restPosture
          ? (posture?.posture_message || 'Minimal capacity today — rest is the priority.')
          : hs.snapshot.headline,
        why: 'Committing to load today would draw down capacity you do not have. Protect it.',
        href: '/captains-chair-workbench',
        at: nowIso(),
      });
    }

    // Recovery debt building into high — escalation worth acting on.
    if (hs.debt.level === 'high') {
      out.push({
        id: 'wellness-recovery-debt',
        kind: 'escalation',
        severity: 'high',
        title: 'Recovery debt is high',
        detail: hs.debt.message,
        why: 'Several low-capacity days in a row — a real recovery window now prevents a larger cost later.',
        // Human Systems redesign Phase 10 (2026-09-06): /recovery-brief
        // (now an explainer stub, its real content consolidated into the
        // NOW tab) would bounce a Captain acting on this alert through an
        // extra click — point straight at the live content instead.
        href: '/human-systems-workbench',
        at: nowIso(),
      });
    }

    // Emotional load flag raised (3+ activated/dysregulated days in 7).
    if (emo?.raised) {
      out.push({
        id: 'wellness-emotional-load',
        kind: 'wellness',
        severity: 'high',
        title: 'Nervous-system load elevated',
        detail: emo.message,
        why: 'Sustained activation changes what load is safe. Adjust commitments accordingly.',
        href: '/medical',
        at: nowIso(),
      });
    }
  } catch (e) {
    console.error('[alerts] wellnessAlerts source 1 failed:', e);
    failed++;
  }

  // MSN-0335: folded in from the now-retired duplicate check in
  // /api/proactive-signals — a real pain-trend average genuinely passes
  // this file's own "why now" bar (unlike that route's staleness/log-gap
  // checks, which are hygiene reminders, not urgent alerts — kept
  // separate, not merged here). Realigned 2026-08-22: recovery_pulses ->
  // capacity_checkins (pain_score is optional in the new model's quick
  // check-in, so this naturally averages over whichever recent check-ins
  // actually recorded one).
  if (supabase) {
    try {
      const { data } = await supabase
        .from('capacity_checkins')
        .select('pain_score, captured_at')
        .eq('checkin_type', 'capacity')
        .order('captured_at', { ascending: false })
        .limit(5);
      if (data && data.length > 0) {
        const avg = data.reduce((sum: number, r: { pain_score: number | null }) => sum + (r.pain_score ?? 0), 0) / data.length;
        if (avg > 8) {
          out.push({
            id: 'wellness-pain-critical',
            kind: 'wellness',
            severity: 'critical',
            title: 'Pain critically high',
            detail: `Average pain score over last ${data.length} check-ins is ${avg.toFixed(1)} (threshold: 8).`,
            why: 'A sustained high-pain trend changes what load is safe today, not just how you feel about it.',
            href: '/medical',
            at: nowIso(),
          });
        } else if (avg > 6) {
          out.push({
            id: 'wellness-pain-elevated',
            kind: 'wellness',
            severity: 'high',
            title: 'Pain trend elevated',
            detail: `Average pain score over last ${data.length} check-ins is ${avg.toFixed(1)} (threshold: 6).`,
            why: 'A rising pain trend is worth acting on before it becomes a red-flag escalation.',
            href: '/medical',
            at: nowIso(),
          });
        }
      }
    } catch (e) {
      console.error('[alerts] wellnessAlerts source 2 (pain trend) failed:', e);
      failed++;
    }
  }

  return { alerts: out, failed, total };
}

// ── Delivery failures + engineering review (reuse delivery + targeted reads) ───

async function engineeringAlerts(): Promise<AlertGroupResult> {
  const supabase = client();
  const out: MobileAlert[] = [];
  let failed = 0;
  const total = 3;
  try {
    const del = await loadDelivery();

    // Blocked missions — critical, one alert per blocked item (capped).
    del.rows
      .filter((r) => r.delivery_state === 'blocked')
      .slice(0, 4)
      .forEach((r, i) =>
        out.push({
          id: `delivery-blocked-${i}`,
          kind: 'delivery_failure',
          severity: 'critical',
          title: `Blocked: ${r.title}`,
          detail: `Blocked for ${r.age_days ?? '?'}d — work cannot progress until cleared.`,
          why: 'A blocked mission stalls everything downstream of it. It needs a decision to move.',
          // Captain's Chair's dedicated Engineering Queue sub-page was
          // removed 2026-08-22 — /engineering (legacy build-request inbox,
          // read-only) is the nearest remaining live view of this data.
          href: '/engineering',
          at: nowIso(),
        }),
      );

    // High-priority items awaiting review — gated to P0/P1 only.
    del.rows
      .filter((r) => r.delivery_state === 'in_review' && /p0|p1/.test((r.priority_norm ?? '').toLowerCase()))
      .slice(0, 4)
      .forEach((r, i) =>
        out.push({
          id: `eng-review-${i}`,
          kind: 'eng_review',
          severity: 'high',
          title: `Review needed: ${r.title}`,
          detail: `${(r.priority_norm ?? '').toUpperCase()} awaiting review${(r.pr_url ?? '').trim() ? '' : ' (no PR/evidence)'}.`,
          why: 'High-priority work is finished but parked until you approve or reject it.',
          href: '/engineering',
          at: nowIso(),
        }),
      );
  } catch (e) {
    console.error('[alerts] engineeringAlerts source 1 (delivery) failed:', e);
    failed++;
  }

  // Build-inbox items awaiting review → required Captain review.
  if (supabase) {
    try {
      const { data } = await supabase
        .from('build_request_inbox')
        .select('request_id, title, status, created_at')
        .in('status', ['in_review', 'awaiting_review'])
        .order('created_at', { ascending: false })
        .limit(5);
      (data ?? []).forEach((r: { request_id: string; title: string }, i: number) =>
        out.push({
          id: `build-review-${r.request_id ?? i}`,
          kind: 'eng_review',
          severity: 'high',
          title: `Approve / reject: ${r.title}`,
          detail: 'Build request is awaiting your review in the engineering queue.',
          why: 'This item will not ship until you approve it. It is blocked on your decision.',
          href: '/engineering',
          at: nowIso(),
        }),
      );
    } catch (e) {
      console.error('[alerts] engineeringAlerts source 2 (build_request_inbox) failed:', e);
      failed++;
    }

    // Failed dispatch / execution — delivery failure.
    try {
      const since = new Date(Date.now() - 3 * 86_400_000).toISOString();
      const { count } = await supabase
        .from('mission_execution_events')
        .select('*', { count: 'exact', head: true })
        .eq('status', 'failed')
        .gte('created_at', since);
      if (count && count > 0) {
        out.push({
          id: 'delivery-failed-dispatch',
          kind: 'delivery_failure',
          severity: 'critical',
          title: `${count} failed dispatch${count > 1 ? 'es' : ''}`,
          detail: 'One or more mission dispatches failed in the last 3 days.',
          why: 'Failed dispatches mean work you expected to be running silently is not. It needs re-driving.',
          href: '/engineering',
          at: nowIso(),
        });
      }
    } catch (e) {
      console.error('[alerts] engineeringAlerts source 3 (mission_execution_events) failed:', e);
      failed++;
    }
  }

  return { alerts: out, failed, total };
}

// ── Decision required (captured missions awaiting triage) ─────────────────────

async function decisionAlerts(): Promise<AlertGroupResult> {
  const supabase = client();
  const out: MobileAlert[] = [];
  let failed = 0;
  const total = 1;
  try {
    const { count } = await supabase
      .from('captured_items')
      .select('*', { count: 'exact', head: true })
      .eq('classification', 'mission')
      .eq('review_status', 'unreviewed');
    if (count && count > 0) {
      out.push({
        id: 'decision-captured-missions',
        kind: 'decision',
        severity: 'high',
        title: `${count} captured mission${count > 1 ? 's' : ''} awaiting triage`,
        detail: 'Items you captured as missions have not yet been triaged into the pipeline.',
        why: 'You flagged these as missions — they stay invisible to Engineering until you triage them.',
        // MSN-0328 (WP-C): was '/engineering-queue', which queries
        // build_request_inbox, not captured_items — the alert routed
        // to a page that could never show what it counted. /capture
        // is the real captured_items consumer; ?filter=mission
        // deep-links straight to the classification this alert counts.
        href: '/capture-workbench?filter=mission',
        at: nowIso(),
      });
    }
  } catch (e) {
    console.error('[alerts] decisionAlerts failed:', e);
    failed++;
  }
  return { alerts: out, failed, total };
}

export interface ComputeAlertsResult {
  alerts: MobileAlert[];
  /** How many of the underlying source fetches (6 total across the 3
   *  groups) errored on this run — surfaced as a quiet degraded-source
   *  note, kept separate from the alert list itself so a real outage
   *  never masquerades as a false alarm. */
  failedSources: number;
  totalSources: number;
}

/** Compute the full, gated alert set. Alert list is [] on total failure;
 *  failedSources/totalSources report how much of that emptiness is a real
 *  outage vs. a genuinely healthy read. */
export async function computeAlerts(): Promise<ComputeAlertsResult> {
  const groups = await Promise.all([wellnessAlerts(), engineeringAlerts(), decisionAlerts()]);
  const all = groups.flatMap((g) => g.alerts);
  const failedSources = groups.reduce((sum, g) => sum + g.failed, 0);
  const totalSources = groups.reduce((sum, g) => sum + g.total, 0);
  // Dedup by id, then sort by severity then kind.
  const seen = new Set<string>();
  const deduped = all.filter((a) => (seen.has(a.id) ? false : (seen.add(a.id), true)));
  deduped.sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]);
  return { alerts: deduped, failedSources, totalSources };
}

/** Stable signature of the current alert set — used to fire a notification only on change. */
export function alertsSignature(alerts: MobileAlert[]): string {
  return alerts.map((a) => a.id).sort().join('|');
}
