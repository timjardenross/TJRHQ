'use client';

// GOOD DAYS — the headline of the Now tab: how many of the last 14 evenings were good days, the longest
// run, and a per-day timeline (good / not good / unknown, with the day's capacity zone underneath), plus
// the latest evening's whole-day answers.
//
// The rule is provisional and lives in ../../api/human-systems/good-day.ts (mirror of
// core/health/good_day.py); the Captain's own "Was today a good day?" answer always wins over it. A day
// with no evening answer is unknown, never "bad", and not-good days are shown neutral, not alarming.

import { Card } from '@/components/ui';
import type { GoodDaysPayload } from '@/app/api/human-systems/good-days-data';

const TRAJECTORY: Record<string, string> = { improved: 'Improved', same: 'About the same', declined: 'Declined' };
const COMPENSATION: Record<string, string> = {
  low: 'Very little', moderate: 'Some', high: 'A lot', extreme: 'Forcing myself through',
};
const GOOD_DAY: Record<string, string> = { yes: 'Yes', kind_of: 'Kind of', no: 'No' };
const ZONE_LABEL: Record<string, string> = { green: 'Sustainable', orange: 'Stretched', red: 'Depleted' };
const ZONE_DOT: Record<string, string> = { green: 'bg-wb-ok', orange: 'bg-wb-warn', red: 'bg-wb-crit' };

function formatDay(date: string): string {
  return new Date(`${date}T00:00:00Z`).toLocaleDateString('en-AU', {
    day: 'numeric', month: 'short', weekday: 'short', timeZone: 'UTC',
  });
}

function verdictText(v: boolean | null): string {
  return v === true ? 'good day' : v === false ? 'not a good day' : 'no evening answer';
}

export function GoodDaysCard({ data, error }: { data: GoodDaysPayload | null; error: string | null }) {
  const s = data?.summary;
  const run = s?.longest_run ?? 0;
  return (
    <Card title="Good days" className="md:col-span-2">
      {error && <p className="text-wb-body text-wb-crit-on">Couldn&rsquo;t load good days: {error}</p>}
      {!error && !data && <p className="text-wb-body text-wb-ink2">Loading…</p>}
      {!error && data && s && (
        <>
          {s.judged === 0 ? (
            <p className="text-wb-body text-wb-ink2">
              No evenings logged in the last {data.window_days} days yet. Your evening answers build this up.
            </p>
          ) : (
            <>
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="font-serif text-3xl text-wb-ink">{s.good} of {s.judged}</span>
                <span className="text-wb-body text-wb-ink2">
                  evenings were good days · longest run {run} day{run === 1 ? '' : 's'} · last {data.window_days} days
                </span>
              </div>
              <ol className="mt-4 grid list-none grid-cols-7 gap-1.5 p-0 sm:grid-cols-[repeat(14,minmax(0,1fr))]" aria-label={`Good days, last ${data.window_days} days`}>
                {data.days.map((d) => (
                  <li
                    key={d.date}
                    className="flex flex-col items-center gap-1"
                    aria-label={`${formatDay(d.date)}: ${verdictText(d.verdict)}${d.zone ? `, ${ZONE_LABEL[d.zone] ?? d.zone}` : ''}`}
                  >
                    <span
                      className={`h-7 w-full rounded ${
                        d.verdict === true ? 'bg-wb-ok'
                        : d.verdict === false ? 'border-2 border-wb-ink2/40 bg-wb-surface'
                        : 'bg-wb-line/50'
                      }`}
                    />
                    <span className={`h-1.5 w-1.5 rounded-full ${d.zone ? ZONE_DOT[d.zone] ?? 'bg-wb-line' : 'bg-transparent'}`} />
                  </li>
                ))}
              </ol>
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-wb-label text-wb-ink2">
                <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded bg-wb-ok" />Good day</span>
                <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded border-2 border-wb-ink2/40" />Not a good day</span>
                <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded bg-wb-line/50" />No evening answer</span>
                <span>Dot under each day: that day&rsquo;s capacity zone</span>
              </div>
            </>
          )}

          {data.latest_evening && (
            <p className="mt-4 text-wb-label text-wb-ink2">
              Latest evening ({formatDay(data.latest_evening.log_date)}):{' '}
              {[
                data.latest_evening.day_trajectory && (TRAJECTORY[data.latest_evening.day_trajectory] ?? data.latest_evening.day_trajectory),
                data.latest_evening.day_compensation_load &&
                  `whole-day pushing/masking: ${COMPENSATION[data.latest_evening.day_compensation_load] ?? data.latest_evening.day_compensation_load}`,
                data.latest_evening.good_day && `you called it a good day: ${GOOD_DAY[data.latest_evening.good_day] ?? data.latest_evening.good_day}`,
              ].filter(Boolean).join(' · ') || 'no answers recorded'}
              .
            </p>
          )}
          <p className="mt-3 text-wb-label text-wb-ink2">
            A rough count while data builds up: your own &ldquo;good day&rdquo; answer wins over the rule (stayed the same or improved,
            and whole-day pushing/masking was moderate or lower). Days without an evening answer aren&rsquo;t counted.
          </p>
        </>
      )}
    </Card>
  );
}
