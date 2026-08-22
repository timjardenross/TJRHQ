'use client';

import { Badge, Card } from '@/components/ui';
import { CollapsibleSection } from './CollapsibleSection';
import { WhatHelpsMeCard } from './WhatHelpsMeCard';
import { CAPACITY_BALANCE_LABEL, CAPACITY_STATE_LABEL as CAPACITY_LABEL, capacityStateStatus, type InterventionEffectiveness, type RecoveryPayload } from './types';

const STIMULATION_LABEL: Record<string, string> = { low: '⬇ Not enough', balanced: '⚖ Balanced', high: '⬆ Too much' };
const PAIN_LABEL: Record<string, string> = {
  low: 'Lower than usual', baseline: 'Around baseline', elevated: 'Higher than usual', high: 'Much higher than usual',
};
const REGULATION_LABEL: Record<string, string> = {
  settled: 'Settled', manageable: 'Manageable', activated: 'Activated', overloaded: 'Overloaded',
};
const EF_LABEL: Record<string, string> = {
  good: 'Working well', strained: 'More effort than usual', difficult: 'Difficult', very_difficult: 'Very difficult',
};
const COMPENSATION_LABEL: Record<string, string> = {
  low: 'Very little', moderate: 'Some', high: 'A lot', extreme: 'Forcing through',
};
const LEVER_LABEL: Record<string, string> = {
  reduce_load: 'REDUCE LOAD', regulate: 'REGULATE', recover: 'RECOVER', redesign: 'REDESIGN',
};

function StateTile({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="rounded-md border border-wb-line bg-wb-bg p-3">
      <div className="text-[11px] uppercase tracking-wide text-wb-ink2">{label}</div>
      <div className="mt-1 text-[13px] text-wb-ink">{value ?? 'Not recorded'}</div>
    </div>
  );
}

/** Recovery tab — "What does my system need today?" VNext consolidation
 *  (Human_Systems_Workbench_VNext_Consolidation_Mission_Scope.md WP02-04):
 *  leads with Capacity Today, the current-state grid, Capacity Balance,
 *  what's driving it, what the system needs, compensation cost, and the
 *  next recommended move — in that order, matching the doc's
 *  STATE→INFLUENCES→NEED→ACTION model (§3). */
export function RecoveryView({ data, interventionEffectiveness }: { data: RecoveryPayload; interventionEffectiveness: InterventionEffectiveness[] }) {
  const nm = data.next_move;
  const hasNextMove = !!(nm.intervention_title);
  const testingSuggestion = worthTesting(data);

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      {!data.data_available && (
        <div className="rounded-lg border border-wb-warn/40 bg-wb-warn/10 p-3 text-[13px] text-wb-warn-on md:col-span-2">
          No capacity check-in recorded for today yet. Log one with the Capacity Bot&rsquo;s /capacity command to
          refresh this view.
        </div>
      )}

      {/* ── MY SYSTEM NOW (spec §5) ──────────────────────────────────────── */}
      <Card className="md:col-span-2">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.12em] text-wb-ink2">Capacity Today</div>
            <div className="mt-1 font-serif text-3xl text-wb-ink">
              {data.latest_capacity_state ? CAPACITY_LABEL[data.latest_capacity_state] ?? data.latest_capacity_state : 'No data'}
            </div>
          </div>
          {data.latest_capacity_state && (
            <Badge status={capacityStateStatus(data.latest_capacity_state)}>{data.latest_capacity_state.toUpperCase()}</Badge>
          )}
        </div>
        <p className="mt-3 text-[14px] leading-relaxed text-wb-ink2">{data.system_posture_message}</p>

        <div className="mt-4 grid gap-2 sm:grid-cols-3 lg:grid-cols-5">
          <StateTile label="Stimulation" value={data.stimulation_state ? STIMULATION_LABEL[data.stimulation_state] ?? data.stimulation_state : null} />
          <StateTile label="Pain" value={data.pain_state ? `${PAIN_LABEL[data.pain_state] ?? data.pain_state}${data.pain_score != null ? ` (${data.pain_score}/10)` : ''}` : null} />
          <StateTile label="Nervous System" value={data.latest_regulation_state ? REGULATION_LABEL[data.latest_regulation_state] ?? data.latest_regulation_state : null} />
          <StateTile label="Executive Function" value={data.executive_function ? EF_LABEL[data.executive_function] ?? data.executive_function : null} />
          <StateTile label="Masking / Compensation" value={data.compensation_load ? COMPENSATION_LABEL[data.compensation_load] ?? data.compensation_load : null} />
        </div>
      </Card>

      {/* ── CAPACITY BALANCE (spec §11) ──────────────────────────────────── */}
      <Card title="Capacity Balance">
        <div className="flex items-center justify-between gap-2 text-[12px] font-medium uppercase tracking-wide">
          <span className={data.capacity_balance === 'too_much' ? 'text-wb-crit-on' : 'text-wb-ink2'}>Too Much</span>
          <span className={data.capacity_balance === 'sustainable' ? 'font-semibold text-wb-ok-on' : 'text-wb-ink2'}>Sustainable</span>
          <span className={data.capacity_balance === 'not_enough' ? 'text-wb-warn-on' : 'text-wb-ink2'}>Not Enough</span>
        </div>
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-wb-line">
          <div
            className={`h-full transition-all ${
              data.capacity_balance === 'too_much' ? 'ml-0 w-1/3 bg-wb-crit' :
              data.capacity_balance === 'sustainable' ? 'ml-[33%] w-1/3 bg-wb-ok' :
              data.capacity_balance === 'not_enough' ? 'ml-[66%] w-1/3 bg-wb-warn' : 'w-0'
            }`}
          />
        </div>
        <p className="mt-3 text-[12px] text-wb-ink2">{CAPACITY_BALANCE_LABEL[data.capacity_balance]} — regulation may mean reducing input or adding the right input.</p>
      </Card>

      {/* ── WHAT IS DRIVING IT (spec §7) ─────────────────────────────────── */}
      <Card title="What Is Driving It">
        {data.active_loads_today.length === 0 ? (
          <p className="text-[13px] text-wb-ink2">No active loads recorded today.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {data.active_loads_today.map((l, i) => (
              <Badge key={l.label} status={i === 0 ? 'warning' : 'neutral'}>
                {l.label} · {l.count}/{data.checkins_today || l.count}
              </Badge>
            ))}
          </div>
        )}
      </Card>

      {/* ── WHAT MY SYSTEM NEEDS (spec §9) ───────────────────────────────── */}
      <Card title="What My System Needs">
        {data.identified_needs_latest.length === 0 ? (
          <p className="text-[13px] text-wb-ink2">No current need recorded.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {data.identified_needs_latest.map((n) => (
              <Badge key={n} status="info">{n}</Badge>
            ))}
          </div>
        )}
      </Card>

      {/* ── MY NEXT MOVE (spec §10) ──────────────────────────────────────── */}
      <Card title="My Next Move">
        {!hasNextMove ? (
          <p className="text-[13px] text-wb-ink2">No action logged yet today. Use /capacity or /helpme on the Capacity Bot to get one.</p>
        ) : (
          <>
            {nm.lever && (
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-wb-ink2">{LEVER_LABEL[nm.lever] ?? nm.lever}</div>
            )}
            <p className="mt-1 text-[15px] leading-relaxed text-wb-ink">{nm.intervention_description ?? nm.intervention_title}</p>
            {nm.accepted_at && (
              <p className="mt-2 text-[12px] text-wb-ink2">
                Last tried {new Date(nm.accepted_at).toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' })}
                {nm.outcome && nm.outcome !== 'unknown' && (
                  <> — <span className="font-medium capitalize text-wb-ink">{nm.outcome.replace('_', ' ')}</span></>
                )}
              </p>
            )}
          </>
        )}
      </Card>

      {/* ── SYSTEM LEARNING (spec §17, renamed from Wellness Intelligence) ── */}
      <CollapsibleSection title="System Learning" className="md:col-span-2">
        <div className="flex flex-col gap-3">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-wb-ink2">What I Know</div>
            <p className="mt-1 text-[13px] text-wb-ink">
              {data.checkins_last_7d} check-in{data.checkins_last_7d === 1 ? '' : 's'} recorded in the last 7 days.
            </p>
          </div>

          {(data.wellness.narrative || data.wellness.risk_flags.length > 0 || data.wellness.positive_flags.length > 0) && (
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-wb-ink2">Possible Pattern</div>
              {data.wellness.narrative && (
                <p className="mt-1 text-[13px] leading-relaxed text-wb-ink2">{data.wellness.narrative}</p>
              )}
              {(data.wellness.risk_flags.length > 0 || data.wellness.positive_flags.length > 0) && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {data.wellness.positive_flags.map((f, i) => (
                    <Badge key={`p${i}`} status="success">{f}</Badge>
                  ))}
                  {data.wellness.risk_flags.map((f, i) => (
                    <Badge key={`r${i}`} status="warning">{f}</Badge>
                  ))}
                </div>
              )}
            </div>
          )}

          {testingSuggestion && (
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-wb-ink2">Worth Testing</div>
              <p className="mt-1 text-[13px] leading-relaxed text-wb-ink2">{testingSuggestion}</p>
            </div>
          )}
        </div>
      </CollapsibleSection>

      {/* ── WHAT HELPS ME (spec §18) — placed next to REVS, same row ────────── */}
      <WhatHelpsMeCard data={interventionEffectiveness} />

      {/* ── MY REVS POSITION (spec §22) — orientation, not a maturity score ── */}
      <CollapsibleSection title="My REVS Position">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div className="rounded-md border border-wb-line bg-wb-bg p-3 text-center">
            <div className="text-[11px] uppercase tracking-wide text-wb-ink2">Recognise</div>
            <div className="mt-1 text-[12px] text-wb-ink2">Ongoing</div>
          </div>
          <div className="rounded-md border-2 border-wb-sage-deep bg-wb-sage-deep/10 p-3 text-center">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-wb-sage-deep">Regulate</div>
            <div className="mt-1 text-[12px] font-medium text-wb-ink">Current priority</div>
          </div>
          <div className="rounded-md border border-wb-line bg-wb-bg p-3 text-center">
            <div className="text-[11px] uppercase tracking-wide text-wb-ink2">Rebuild</div>
            <div className="mt-1 text-[12px] text-wb-ink2">Not yet</div>
          </div>
          <div className="rounded-md border border-wb-line bg-wb-bg p-3 text-center">
            <div className="text-[11px] uppercase tracking-wide text-wb-ink2">Redesign</div>
            <div className="mt-1 text-[12px] text-wb-ink2">As patterns emerge</div>
          </div>
        </div>
        <p className="mt-3 text-[12px] text-wb-ink2">
          A management orientation, not a completion score. See &ldquo;Things I Should Change&rdquo; below for redesign candidates.
        </p>
      </CollapsibleSection>
    </div>
  );
}

/** WP09 "Worth Testing" — a single behavioural-experiment prompt derived
 *  from today's top active load, when there's enough signal to suggest
 *  one (spec §17 example format: "On high-pain mornings, try reducing
 *  task switching before midday and compare evening capacity"). Returns
 *  null rather than a generic filler when there isn't enough today's-data
 *  to ground a specific suggestion — an empty section beats a made-up one. */
function worthTesting(data: RecoveryPayload): string | null {
  const top = data.active_loads_today[0];
  if (!top || top.count < 2) return null;
  return `${top.label} has come up in ${top.count} check-ins today. Worth testing whether addressing it earlier changes how the rest of the day goes.`;
}
