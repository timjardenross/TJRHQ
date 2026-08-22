'use client';

// Daily Check-In manual-entry page — RETIRED (2026-08-22).
//
// The Telegram bot's "MY CAPACITY TODAY" flow (capacity_checkins table)
// is now the platform's sole manual health-data capture mechanism — this
// was the last holdout still writing health_daily_logs directly (nervous
// system, energy, sleep, CPAP, body signals, sitting tolerance, workload).
// Its POST target (/api/human-systems/check-in) is itself now retired
// (410 Gone). This page is kept only as an informational redirect-in-place,
// pointing the Captain at the Telegram bot, with a read-only glance at the
// most recent capacity check-in so it isn't a dead end — same pattern as
// medical/pulse/page.tsx.
//
// Disclosed gap: capacity_checkins does not track sleep hours/quality,
// CPAP, or sitting tolerance — the Telegram bot's spec deliberately hasn't
// built those fields yet. Retiring this form means those specific signals
// have no live capture path right now, not just a relocated one. The
// Sleep index on the Medical tab (and Life Participation's sitting-
// tolerance component) will stay frozen at whatever health_daily_logs last
// recorded until/unless that gap is closed.

import { useEffect, useState } from 'react';
import { WorkbenchShell, Card, Badge } from '@/components/ui';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

interface LatestCheckin {
  captured_at: string;
  capacity_state: string | null;
  regulation_state: string | null;
  pain_score: number | null;
}

export default function HealthCheckInPage() {
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
      title="Daily Check-In"
      eyebrow="Health Tracking"
      tagline="USS TJR · Human Systems · Recovery · Medical · Readiness · Evidence-informed, non-diagnostic"
      back={{ href: '/human-systems-workbench?domain=medical', label: 'Medical' }}
    >
      <div className="flex flex-col gap-4">
        <Card title="Manual daily check-in has been retired">
          <p className="text-sm leading-relaxed text-wb-ink2">
            Capacity check-ins now happen via the XO Telegram bot — use{' '}
            <span className="font-semibold text-wb-ink">/capacity</span> for a quick check-in,{' '}
            <span className="font-semibold text-wb-ink">/deepcheck</span> to go deeper, or{' '}
            <span className="font-semibold text-wb-ink">/evening</span> for an evening reflection.
          </p>
          <p className="mt-3 text-sm leading-relaxed text-wb-ink2">
            Sleep hours/quality, CPAP, and sitting tolerance aren&rsquo;t captured by the Telegram
            flow yet — those fields have no live capture path right now, not a relocated one. The
            Medical tab&rsquo;s Sleep index reflects that honestly.
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
