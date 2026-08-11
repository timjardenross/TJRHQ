'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
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
    <div className="flex flex-col gap-4">
      <LCARSPanel title="Physical Readiness" accent="medical" eyebrow="Adaptive gym decision-support">
        <p className="text-xs text-lcars-muted leading-relaxed">
          Tell the ship how you feel right now. It builds a safe session from the equipment actually
          in the gym — no generic fitness plan, no decisions to make once you walk in.
        </p>
      </LCARSPanel>

      {/* 2026-08-10/11: manual readiness check-in retired platform-wide —
          Recovery Pulse is the sole capture path (same treatment already
          applied to the workbench copy of this flow, commit f32ad53a).
          "Start Today's Check-In" removed here too so this legacy (app)
          route stops contradicting that. */}

      <LCARSPanel title="Last Session" accent="medical" eyebrow={loading ? 'Loading…' : undefined}>
        {!loading && !lastSession && (
          <p className="text-sm text-lcars-muted">No sessions on record.</p>
        )}
        {lastSession && (
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-lcars-text">
                {SESSION_TYPE_LABELS[lastSession.session_type] ?? lastSession.session_type}
              </p>
              <p className="text-xs text-lcars-muted">
                {fmtDate(lastSession.started_at)}
                {lastSession.duration_minutes ? ` · ${lastSession.duration_minutes} min` : ''}
              </p>
            </div>
            <StatusBadge label={lastSession.status.replace('_', ' ')} status={lastSession.status} />
          </div>
        )}
        {weeklyCount !== null && (
          <p className="mt-3 text-xs text-lcars-muted">
            {weeklyCount} session{weeklyCount === 1 ? '' : 's'} completed in the last 7 days.
          </p>
        )}
      </LCARSPanel>

      <div className="grid grid-cols-2 gap-3">
        <Link
          href="/physical-readiness/library"
          className="rounded-lcars border border-edge bg-panel/50 px-4 py-3 text-center text-sm font-semibold uppercase tracking-wider text-lcars-text hover:border-medical/60"
        >
          Exercise Library
        </Link>
        <Link
          href="/physical-readiness/history"
          className="rounded-lcars border border-edge bg-panel/50 px-4 py-3 text-center text-sm font-semibold uppercase tracking-wider text-lcars-text hover:border-medical/60"
        >
          History
        </Link>
      </div>
    </div>
  );
}
