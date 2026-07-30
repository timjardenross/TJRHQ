import { createClient } from '@supabase/supabase-js';
import { NextResponse } from 'next/server';
import { REVIEW_PENDING_STATUSES } from '@/lib/missionStatus';
import { dedupeMissionSignals, isHygieneEligible } from '@/lib/hygieneRules';
import { requireSession } from '@/lib/supabase-server';

export const dynamic = 'force-dynamic';

// MSN-0335: deliberately scoped to genuine operational HYGIENE
// reminders only (staleness, log gaps, tracking gaps) -- not urgent
// "why now" alerts. 2 checks that were real duplicates of
// lib/alerts.ts's own urgent-alert engine (blocked missions with no
// age gate; pain-trend average) were removed here and folded into
// alerts.ts, the one authoritative urgent-alert engine. What remains
// answers a genuinely different question ("what's been quietly
// drifting") than AlertsSidebar's "what needs action right now".
//
// Operational Hygiene Cleanup mission: rule 1's exclusion list
// ("COMPLETE","DEFERRED","CLOSED") never matched real data — the
// missions.status CHECK constraint uses 'Closed'/'Archived' (Title
// Case), so 108 Closed and 13 Archived missions (all of them
// Slack/force-triage era stub missions like "force-20260610225359")
// were being evaluated as if active. Every mission-scoped signal below
// now goes through isHygieneEligible(), one shared guard, instead of a
// per-rule status string.

type Severity = 'critical' | 'high' | 'medium';

interface Signal {
  id: string;
  severity: Severity;
  category: string;
  title: string;
  detail: string;
  mission_id?: string;
  action?: string;
}

const SEVERITY_ORDER: Record<Severity, number> = { critical: 0, high: 1, medium: 2 };

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );

  const signals: Signal[] = [];

  // 1. Active missions stalled > 14 days
  try {
    const cutoff = new Date(Date.now() - 14 * 24 * 60 * 60 * 1000).toISOString();
    const { data } = await supabase
      .from('missions')
      .select('mission_id, title, status, updated_at')
      .lt('updated_at', cutoff);
    if (data) {
      for (const m of data) {
        if (!isHygieneEligible(m.status, m.mission_id)) continue;
        signals.push({
          id: `stalled-${m.mission_id}`,
          severity: 'medium',
          category: 'Mission',
          title: 'Stalled mission',
          detail: `"${m.title}" (${m.status}) has not been updated in over 14 days.`,
          mission_id: m.mission_id,
        });
      }
    }
  } catch {}

  // 2. Most recent captain's log older than 3 days
  try {
    const { data } = await supabase
      .from('captains_log_entries')
      .select('log_date')
      .order('log_date', { ascending: false })
      .limit(1);
    if (data && data.length > 0) {
      const latest = new Date(data[0].log_date);
      const diffDays = (Date.now() - latest.getTime()) / (1000 * 60 * 60 * 24);
      if (diffDays > 3) {
        signals.push({
          id: 'log-gap',
          severity: 'medium',
          category: 'Operations',
          title: 'No log entry in 3+ days',
          detail: `Last captain's log was ${Math.floor(diffDays)} days ago (${data[0].log_date}).`,
        });
      }
    } else {
      signals.push({
        id: 'log-none',
        severity: 'medium',
        category: 'Operations',
        title: 'No log entry in 3+ days',
        detail: 'No captain\'s log entries found.',
      });
    }
  } catch {}

  // 3. Missions awaiting review/approval for more than 48 hours
  try {
    const cutoff = new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString();
    const { data } = await supabase
      .from('missions')
      .select('mission_id, title, status, updated_at')
      .in('status', REVIEW_PENDING_STATUSES)
      .lt('updated_at', cutoff);
    if (data) {
      for (const m of data) {
        if (!isHygieneEligible(m.status, m.mission_id)) continue;
        signals.push({
          id: `review-${m.mission_id}`,
          severity: 'high',
          category: 'Mission',
          title: 'Awaiting review',
          detail: `"${m.title}" (${m.status}) has been awaiting review for over 48 hours.`,
          mission_id: m.mission_id,
        });
      }
    }
  } catch {}

  // 4. No recovery_pulses in last 48 hours
  try {
    const cutoff = new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString();
    const { data } = await supabase
      .from('recovery_pulses')
      .select('id')
      .gte('captured_at', cutoff)
      .limit(1);
    if (!data || data.length === 0) {
      signals.push({
        id: 'recovery-gap',
        severity: 'medium',
        category: 'Health',
        title: 'Recovery gap detected',
        detail: 'No recovery pulses recorded in the last 48 hours.',
      });
    }
  } catch {}

  const deduped = dedupeMissionSignals(signals);
  deduped.sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]);

  return NextResponse.json({ signals: deduped });
}
