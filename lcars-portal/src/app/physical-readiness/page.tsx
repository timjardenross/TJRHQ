'use client';

// Physical Readiness — migrated onto WorkbenchShell 2026-09-05 (Captain's
// direct request, iPad retrofit pass: "old LCARS page not a workbench").
// Same URL, same data (physical_workout_sessions), previously served from
// the (app) route group on LCARSPanel/StatusBadge — that group is now
// retired for this feature entirely, not just re-skinned in place.
// Confirmed live before migrating (human-systems-workbench/page.tsx's own
// header comment, 2026-08-29): this page is "the live, mobile-primary
// readiness experience" — the human-systems-workbench/readiness/* routes
// referenced by this feature's own retired /start and /session/[id] sub-
// pages were deleted outright the same day, so those two stubs' links
// were already dead; fixed in the same pass (see their files).

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { WorkbenchShell } from '@/components/ui';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { SESSION_TYPE_LABELS, type SessionType } from '@/lib/physical-readiness';

interface LastSessionRow {
  id: string;
  session_type: SessionType;
  status: string;
  started_at: string;
  duration_minutes: number | null;
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: 'short' });
}

const STATUS_LABEL: Record<string, string> = {
  completed: 'Completed',
  partially_completed: 'Partial',
  in_progress: 'In progress',
  abandoned: 'Abandoned',
};

export default function PhysicalReadinessHome() {
  const [lastSession, setLastSession] = useState<LastSessionRow | null>(null);
  const [weeklyCount, setWeeklyCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const supabase = createSupabaseBrowserClient();
    (async () => {
      const { data: last } = await supabase
        .from('physical_workout_sessions')
        .select('id, session_type, status, started_at, duration_minutes')
        .order('started_at', { ascending: false })
        .limit(1)
        .maybeSingle();
      setLastSession(last as LastSessionRow | null);

      const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
      const { count } = await supabase
        .from('physical_workout_sessions')
        .select('id', { count: 'exact', head: true })
        .eq('status', 'completed')
        .gte('started_at', sevenDaysAgo);
      setWeeklyCount(count ?? 0);
      setLoading(false);
    })();
  }, []);

  return (
    <WorkbenchShell title="Physical Readiness" eyebrow="Adaptive Gym Decision-Support" tagline="USS TJR · Physical Readiness" wide>
      <div className="space-y-4">
        <div className="rounded-lg border border-wb-line bg-white p-4">
          <p className="text-xs leading-relaxed text-wb-ink2">
            Tell the ship how you feel right now. It builds a safe session from the equipment actually
            in the gym — no generic fitness plan, no decisions to make once you walk in.
          </p>
        </div>

        <div className="rounded-lg border border-wb-line bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold text-wb-ink">Last Session</h2>
          {loading ? (
            <p className="text-xs text-wb-ink2 animate-pulse">Loading…</p>
          ) : !lastSession ? (
            <p className="text-xs text-wb-ink2">No sessions on record.</p>
          ) : (
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-wb-ink">
                  {SESSION_TYPE_LABELS[lastSession.session_type] ?? lastSession.session_type}
                </p>
                <p className="text-xs text-wb-ink2">
                  {fmtDate(lastSession.started_at)}
                  {lastSession.duration_minutes ? ` · ${lastSession.duration_minutes} min` : ''}
                </p>
              </div>
              <span className="rounded-full border border-wb-line bg-wb-bg px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-wb-ink2">
                {STATUS_LABEL[lastSession.status] ?? lastSession.status.replace('_', ' ')}
              </span>
            </div>
          )}
          {weeklyCount !== null && (
            <p className="mt-3 text-xs text-wb-ink2">
              {weeklyCount} session{weeklyCount === 1 ? '' : 's'} completed in the last 7 days.
            </p>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Link
            href="/physical-readiness/library"
            className="rounded-lg border border-wb-line bg-white px-4 py-3 text-center text-sm font-semibold text-wb-ink transition-colors hover:border-wb-sage-deep/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
          >
            Exercise Library
          </Link>
          <Link
            href="/physical-readiness/history"
            className="rounded-lg border border-wb-line bg-white px-4 py-3 text-center text-sm font-semibold text-wb-ink transition-colors hover:border-wb-sage-deep/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
          >
            History
          </Link>
        </div>
      </div>
    </WorkbenchShell>
  );
}
