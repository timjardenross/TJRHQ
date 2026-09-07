// Operational History API (HQ Status uplift) — a compact incident timeline,
// not a raw log viewer. Reads the raw domain_heartbeats EVENT LOG (not the
// domain_heartbeats_latest view — History needs a per-domain time series,
// not "current state only") for the known scheduler jobs, then collapses
// each domain's run attempts down to real down/up TRANSITIONS in JS. Repeat
// failures and skipped rows are deliberately not emitted, so a job retrying
// every 5 minutes doesn't flood this feed — only the first failure of a run
// and its eventual recovery are surfaced.

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { SCHEDULER_JOBS } from '@/lib/agentStatusJobs';

// NON_LIVE_DOMAIN_KEYS (retired/never-live domainKeys such as
// shakedown_digest, human_systems) is intentionally not imported here: their
// heartbeat rows still transition like any other domain's, and this route
// deliberately does not special-case them — consistent transition logic for
// every domain beats an "is this one alarming" branch.

const WINDOW_HOURS = 72;
const ROW_LIMIT = 3000;
const EVENT_LIMIT = 50;

type HeartbeatRow = {
  domain_key: string;
  checked_at: string;
  status: string;
  detail: string | null;
  error_message: string | null;
};

export type HistoryEvent =
  | {
      domainKey: string;
      label: string;
      at: string;
      kind: 'down';
      detail: string | null;
    }
  | {
      domainKey: string;
      label: string;
      at: string;
      kind: 'up';
      detail: string | null;
      downSinceIso: string;
      durationMinutes: number;
    };

const LABEL_BY_DOMAIN_KEY = new Map(SCHEDULER_JOBS.map((job) => [job.domainKey, job.label]));

/** Walks one domain's own ascending time series and emits down/up transition
 *  events only — never a per-row entry and never a repeated consecutive
 *  'failed' row. `NON_LIVE_DOMAIN_KEYS` entries are not special-cased here;
 *  their transitions are reported the same as any other domain. */
function transitionsForDomain(domainKey: string, rows: HeartbeatRow[]): HistoryEvent[] {
  const label = LABEL_BY_DOMAIN_KEY.get(domainKey) ?? domainKey;
  const events: HistoryEvent[] = [];

  let previousStatus: string | null = null;
  let downSinceIso: string | null = null;

  for (const row of rows) {
    const status = row.status;

    if (status === 'failed' && previousStatus !== 'failed') {
      // Transition into failed — either from a different prior status, or
      // this is the first row in the window (no prior success visible here).
      downSinceIso = row.checked_at;
      events.push({
        domainKey,
        label,
        at: row.checked_at,
        kind: 'down',
        detail: row.error_message ?? row.detail ?? null,
      });
    } else if (status === 'ok' && previousStatus === 'failed') {
      const since = downSinceIso ?? row.checked_at;
      const durationMinutes = Math.max(
        0,
        Math.round((new Date(row.checked_at).getTime() - new Date(since).getTime()) / 60_000),
      );
      events.push({
        domainKey,
        label,
        at: row.checked_at,
        kind: 'up',
        detail: row.detail ?? null,
        downSinceIso: since,
        durationMinutes,
      });
      downSinceIso = null;
    }
    // 'skipped' transitions and repeated consecutive 'failed' rows never
    // emit an event — that's the "not a log viewer" discipline.

    previousStatus = status;
  }

  return events;
}

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    const knownKeys = SCHEDULER_JOBS.map((job) => job.domainKey);
    const cutoffIso = new Date(Date.now() - WINDOW_HOURS * 3600_000).toISOString();

    const { data, error } = await sb
      .from('domain_heartbeats')
      .select('domain_key, checked_at, status, detail, error_message')
      .in('domain_key', knownKeys)
      .gte('checked_at', cutoffIso)
      .order('checked_at', { ascending: true })
      .limit(ROW_LIMIT);

    if (error) throw error;

    const rowsByDomainKey = new Map<string, HeartbeatRow[]>();
    for (const row of (data ?? []) as HeartbeatRow[]) {
      const existing = rowsByDomainKey.get(row.domain_key);
      if (existing) {
        existing.push(row);
      } else {
        rowsByDomainKey.set(row.domain_key, [row]);
      }
    }

    const allEvents: HistoryEvent[] = [];
    for (const [domainKey, rows] of rowsByDomainKey) {
      allEvents.push(...transitionsForDomain(domainKey, rows));
    }

    allEvents.sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime());

    return NextResponse.json({
      events: allEvents.slice(0, EVENT_LIMIT),
      windowHours: WINDOW_HOURS,
      fetchedAt: new Date().toISOString(),
    });
  } catch (err) {
    console.error('[agent-status-workbench/history] read failed:', err);
    return NextResponse.json(
      { error: 'history_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
