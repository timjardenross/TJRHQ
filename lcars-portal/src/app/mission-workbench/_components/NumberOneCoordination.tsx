'use client';

// USS-TJR-MSN-0054 — first live surface for core/coordination/number_one.py's
// NumberOne coordination engine (via /api/number-one-brief ->
// context_service.py's /brief/number-one). Escalations and follow-ups only —
// the work-queue/blocked-missions/specialist-workload parts of the brief
// duplicate what this page's own mission list + tabs already show, so this
// stays scoped to what Number One adds that the raw mission list doesn't:
// deterministic, rule-based "needs XO attention" and "gone stale" detection.
//
// 2026-09-08 follow-on: also surfaces get_health_adjusted_queue() (via
// /api/health-adjusted-queue -> /queue/health-adjusted) as a "Today's Focus"
// advisory. Deliberately separate from this page's existing posture/
// "Suitable today" filter (useROSData()'s 5-band STRONG/STABLE/FRAGILE/REST/
// UNKNOWN system, already live) — this is Number One's own 3-band Green/
// Amber/Red read on today's capacity (core/health/capacity_score.py, the
// same source the D-055 Capacity Gate uses), advisory-only and additive.
// Captain direction (2026-09-08): "Number One should also drive what lands
// in my face" — this is that, not a replacement for the existing filter.

import { useEffect, useState } from 'react';
import { Badge, Card } from '@/components/ui';
import type { BadgeStatus } from '@/components/ui';

interface Escalation {
  escalation_type: string;
  mission_id: string;
  level: string;
  reason: string;
  recommendation: string;
}

interface FollowUp {
  mission_id: string;
  type: string;
  reason: string;
  recommendation: string;
}

interface NumberOneBrief {
  escalations: Escalation[];
  follow_ups: FollowUp[];
}

interface HealthAdjustedQueue {
  capacity_status: string;
  recommended_focus: string[];
  advisory: string;
}

const LEVEL_BADGE: Record<string, BadgeStatus> = {
  CRITICAL: 'error',
  HIGH: 'error',
  MEDIUM: 'warning',
  LOW: 'neutral',
};

const CAPACITY_BADGE: Record<string, BadgeStatus> = {
  Red: 'error',
  Amber: 'warning',
  Green: 'success',
  Unknown: 'neutral',
};

function TodaysFocus() {
  const [queue, setQueue] = useState<HealthAdjustedQueue | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/health-adjusted-queue')
      .then(async (res) => {
        const body = await res.json().catch(() => ({}));
        if (!res.ok || 'error' in body) {
          throw new Error(body?.detail ?? body?.error ?? `HTTP ${res.status}`);
        }
        if (!cancelled) { setQueue(body); setLoadError(null); }
      })
      .catch((e) => {
        if (!cancelled) setLoadError(e instanceof Error ? e.message : 'Couldn’t reach Number One right now.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  if (loading) return null;

  if (loadError) {
    return (
      <Card className="border-wb-crit/40 bg-wb-crit/10">
        <p className="text-[11px] uppercase tracking-wider text-wb-ink2">Number One · Today&apos;s Focus</p>
        <p className="mt-1 text-[13px] text-wb-crit-on">
          {loadError} This is a load failure, not a Green capacity reading.
        </p>
      </Card>
    );
  }

  if (!queue) return null;

  return (
    <Card>
      <div className="flex items-center gap-2">
        <p className="text-[11px] uppercase tracking-wider text-wb-ink2">Number One · Today&apos;s Focus</p>
        <Badge status={CAPACITY_BADGE[queue.capacity_status] ?? 'neutral'}>{queue.capacity_status}</Badge>
      </div>
      <p className="mt-1 text-[13px] text-wb-ink">{queue.advisory}</p>
      {queue.recommended_focus.length > 0 && (
        <ul className="mt-2 flex flex-col gap-1">
          {queue.recommended_focus.map((title, i) => (
            <li key={i} className="text-[12px] text-wb-ink2">→ {title}</li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function NumberOneCoordination() {
  const [brief, setBrief] = useState<NumberOneBrief | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/number-one-brief')
      .then(async (res) => {
        const body = await res.json().catch(() => ({}));
        if (!res.ok || 'error' in body) {
          throw new Error(body?.detail ?? body?.error ?? `HTTP ${res.status}`);
        }
        if (!cancelled) { setBrief(body); setLoadError(null); }
      })
      .catch((e) => {
        if (!cancelled) setLoadError(e instanceof Error ? e.message : 'Couldn’t reach Number One right now.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return <TodaysFocus />; // let the focus card render independently while the brief loads
  }

  if (loadError) {
    // A genuine fetch failure must not collapse into "nothing needs attention" —
    // that's indistinguishable from a real clean coordination pass (MSN-LCARS-003).
    return (
      <>
        <TodaysFocus />
        <Card className="border-wb-crit/40 bg-wb-crit/10">
          <p className="text-[11px] uppercase tracking-wider text-wb-ink2">Number One · Coordination</p>
          <p className="mt-1 text-[13px] text-wb-crit-on">
            {loadError} This is a load failure, not confirmation nothing needs attention.
          </p>
        </Card>
      </>
    );
  }

  const escalations = brief?.escalations ?? [];
  const followUps = brief?.follow_ups ?? [];
  if (escalations.length === 0 && followUps.length === 0) {
    return (
      <>
        <TodaysFocus />
        <Card>
          <p className="text-[11px] uppercase tracking-wider text-wb-ink2">Number One · Coordination</p>
          <p className="mt-1 text-[13px] text-wb-ink2">
            Nothing needs escalation right now — no blockers or stale follow-ups found.
          </p>
        </Card>
      </>
    );
  }

  return (
    <>
      <TodaysFocus />
      <Card>
        <p className="mb-2 text-[11px] uppercase tracking-wider text-wb-ink2">Number One · Coordination</p>
        <div className="flex flex-col gap-2">
          {escalations.map((e, i) => (
            <div key={`esc-${i}`} className="flex flex-col gap-1 rounded-md border border-wb-line bg-wb-bg p-3">
              <div className="flex items-center gap-2">
                <Badge status={LEVEL_BADGE[e.level] ?? 'neutral'}>{e.level}</Badge>
                <span className="font-mono text-[11px] text-wb-ink2">{e.mission_id}</span>
              </div>
              <p className="text-[13px] text-wb-ink">{e.reason}</p>
              <p className="text-[12px] text-wb-ink2">→ {e.recommendation}</p>
            </div>
          ))}
          {followUps.map((f, i) => (
            <div key={`fu-${i}`} className="flex flex-col gap-1 rounded-md border border-wb-line bg-wb-bg p-3">
              <div className="flex items-center gap-2">
                <Badge status="warning">{f.type.replace(/_/g, ' ')}</Badge>
                <span className="font-mono text-[11px] text-wb-ink2">{f.mission_id}</span>
              </div>
              <p className="text-[13px] text-wb-ink">{f.reason}</p>
              <p className="text-[12px] text-wb-ink2">→ {f.recommendation}</p>
            </div>
          ))}
        </div>
      </Card>
    </>
  );
}
