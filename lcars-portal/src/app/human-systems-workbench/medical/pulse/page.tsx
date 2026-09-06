'use client';

// Recovery Pulse manual-entry page — RETIRED (2026-08-22).
//
// The Telegram bot's "MY CAPACITY TODAY" flow (capacity_checkins table)
// replaced recovery_pulses as the canonical health-capacity capture path on
// 2026-08-21 and is now the SOLE capture path for this data — extending the
// same consolidation principle the Captain applied to Recovery Pulse itself
// on 2026-08-10. This page previously offered a 3-pulse-type
// (morning/midday/evening) manual form posting to
// /api/human-systems/pulse; that endpoint is itself now retired (410 Gone).
// This page is kept only as an informational redirect-in-place, pointing
// the Captain at the Telegram bot instead, with a read-only glance at the
// most recent capacity check-in so it isn't a dead end.

import { useEffect, useState } from 'react';
import { WorkbenchShell, Card, Badge } from '@/components/ui';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

interface LatestCheckin {
  captured_at: string;
  capacity_state: string | null;
  regulation_state: string | null;
  pain_score: number | null;
}

export default function RecoveryPulsePage() {
  const [latest, setLatest] = useState<LatestCheckin | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const supabase = createSupabaseBrowserClient();
        const { data } = await supabase
          .from('capacity_checkins')
          .select('captured_at,capacity_state,regulation_state,pain_score')
          .eq('checkin_type', 'capacity')
          .order('captured_at', { ascending: false })
          .limit(1);
        if (!cancelled) setLatest((data?.[0] as LatestCheckin | undefined) ?? null);
      } catch {
        if (!cancelled) setLatest(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <WorkbenchShell
      title="Recovery Pulse"
      eyebrow="Health Tracking"
      tagline="USS TJR · Human Systems · Recovery · Medical · Readiness · Evidence-informed, non-diagnostic"
      back={{ href: '/human-systems-workbench', label: 'Human Systems' }}
    >
      <div className="flex flex-col gap-4">
        <Card title="Manual pulse logging has been retired">
          <p className="text-sm leading-relaxed text-wb-ink2">
            Capacity check-ins now happen via the XO Telegram bot — use{' '}
            <span className="font-semibold text-wb-ink">/capacity</span> for a quick check-in,{' '}
            <span className="font-semibold text-wb-ink">/deepcheck</span> to go deeper, or{' '}
            <span className="font-semibold text-wb-ink">/evening</span> for an evening reflection.
          </p>
        </Card>

        <Card title="Most recent check-in">
          {loading && <p className="text-[13px] text-wb-ink2">Loading…</p>}
          {!loading && !latest && (
            <p className="text-[13px] text-wb-ink2">No capacity check-ins recorded yet.</p>
          )}
          {!loading && latest && (
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-md border border-wb-line bg-wb-bg p-3">
                <div className="text-[11px] uppercase tracking-wide text-wb-ink2">Capacity</div>
                <div className="mt-1">
                  <Badge status="info">{latest.capacity_state ?? 'Not recorded'}</Badge>
                </div>
              </div>
              <div className="rounded-md border border-wb-line bg-wb-bg p-3">
                <div className="text-[11px] uppercase tracking-wide text-wb-ink2">Regulation</div>
                <div className="mt-1 text-[14px] capitalize text-wb-ink">
                  {latest.regulation_state ?? 'Not recorded'}
                </div>
              </div>
              <div className="rounded-md border border-wb-line bg-wb-bg p-3">
                <div className="text-[11px] uppercase tracking-wide text-wb-ink2">Pain</div>
                <div className="mt-1 text-[14px] text-wb-ink">
                  {latest.pain_score ?? 'Not recorded'}
                </div>
              </div>
              <div className="sm:col-span-3 text-[12px] text-wb-ink2">
                Captured {new Date(latest.captured_at).toLocaleString('en-AU', {
                  weekday: 'long',
                  day: 'numeric',
                  month: 'long',
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </div>
            </div>
          )}
        </Card>
      </div>
    </WorkbenchShell>
  );
}
