'use client';

// USS-TJR-MSN-0054 — first live surface for core/coordination/number_one.py's
// NumberOne coordination engine (via /api/number-one-brief ->
// context_service.py's /brief/number-one). Escalations and follow-ups only —
// the work-queue/blocked-missions/specialist-workload parts of the brief
// duplicate what this page's own mission list + tabs already show, so this
// stays scoped to what Number One adds that the raw mission list doesn't:
// deterministic, rule-based "needs XO attention" and "gone stale" detection.

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

const LEVEL_BADGE: Record<string, BadgeStatus> = {
  CRITICAL: 'error',
  HIGH: 'error',
  MEDIUM: 'warning',
  LOW: 'neutral',
};

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

  if (loading) return null; // avoid a second loading spinner stacked under the page's own

  if (loadError) {
    // A genuine fetch failure must not collapse into "nothing needs attention" —
    // that's indistinguishable from a real clean coordination pass (MSN-LCARS-003).
    return (
      <Card className="border-wb-crit/40 bg-wb-crit/10">
        <p className="text-[11px] uppercase tracking-wider text-wb-ink2">Number One · Coordination</p>
        <p className="mt-1 text-[13px] text-wb-crit-on">
          {loadError} This is a load failure, not confirmation nothing needs attention.
        </p>
      </Card>
    );
  }

  const escalations = brief?.escalations ?? [];
  const followUps = brief?.follow_ups ?? [];
  if (escalations.length === 0 && followUps.length === 0) {
    return (
      <Card>
        <p className="text-[11px] uppercase tracking-wider text-wb-ink2">Number One · Coordination</p>
        <p className="mt-1 text-[13px] text-wb-ink2">
          Nothing needs escalation right now — no blockers or stale follow-ups found.
        </p>
      </Card>
    );
  }

  return (
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
  );
}
