'use client';

import { Badge, Card } from '@/components/ui';
import { CollapsibleSection } from './CollapsibleSection';
import {
  CAPACITY_BALANCE_LABEL,
  CAPACITY_STATE_LABEL as CAPACITY_LABEL,
  capacityStateStatus,
  EXPERIMENT_STATUS_LABEL,
  type CapacityBalance,
  type CapacityExperiment,
  type RecoveryPayload,
} from './types';

const STIMULATION_LABEL: Record<string, string> = { low: '⬇ Not enough', balanced: '⚖ About right', high: '⬆ Too much' };
const PAIN_LABEL: Record<string, string> = {
  low: 'Lower than usual', baseline: 'Around usual', elevated: 'Higher than usual', high: 'Much higher than usual',
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
      <div className="text-wb-label uppercase tracking-wide text-wb-ink2">{label}</div>
      <div className="mt-1 text-wb-body text-wb-ink">{value ?? 'Not recorded'}</div>
    </div>
  );
}

/** No current-day check-in — a single consolidated message rather than a
 *  hero card plus a grid of five individually-"Not recorded" tiles (Human
 *  Systems redesign Phase 4). Says plainly that there is no reading yet
 *  today, rather than guessing a state. */
function NoCurrentCheckinMessage() {
  return (
    <Card className="md:col-span-2">
      <div className="text-wb-label uppercase tracking-[0.12em] text-wb-ink2">Capacity Today</div>
      <p className="mt-2 text-wb-body leading-relaxed text-wb-ink">
        No check-in yet today, so there is no reading to show.
      </p>
      <p className="mt-2 text-wb-body text-wb-ink2">
        Want a current read? Use <span className="font-medium text-wb-ink">/capacity</span> in Telegram.
      </p>
    </Card>
  );
}

/** ── MY SYSTEM NOW (spec §5) — "Capacity Today" hero. Renders the
 *  consolidated no-check-in message instead of the state grid when there's
 *  genuinely no reading for today (Phase 4); the five-tile grid below is
 *  only ever shown once there IS a current check-in to ground it, so it
 *  never has to say "Not recorded" five times in a row. */
export function CapacityTodayCard({ data }: { data: RecoveryPayload }) {
  if (!data.data_available) return <NoCurrentCheckinMessage />;

  return (
    <Card className="md:col-span-2">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-wb-label uppercase tracking-[0.12em] text-wb-ink2">Capacity Today</div>
          <div className="mt-1 font-serif text-3xl text-wb-ink">
            {data.latest_capacity_state ? CAPACITY_LABEL[data.latest_capacity_state] ?? data.latest_capacity_state : 'No data'}
          </div>
        </div>
        {data.latest_capacity_state && (
          <Badge status={capacityStateStatus(data.latest_capacity_state)}>{data.latest_capacity_state.toUpperCase()}</Badge>
        )}
      </div>
      <p className="mt-3 text-wb-body leading-relaxed text-wb-ink2">{data.system_posture_message}</p>

      <div className="mt-4 grid gap-2 sm:grid-cols-3 lg:grid-cols-5">
        <StateTile label="Stimulation" value={data.stimulation_state ? STIMULATION_LABEL[data.stimulation_state] ?? data.stimulation_state : null} />
        <StateTile label="Pain" value={data.pain_state ? `${PAIN_LABEL[data.pain_state] ?? data.pain_state}${data.pain_score != null ? ` (older 0–10 record: ${data.pain_score}/10)` : ''}` : (data.pain_score != null ? `Older 0–10 record: ${data.pain_score}/10` : null)} />
        <StateTile label="Nervous System" value={data.latest_regulation_state ? REGULATION_LABEL[data.latest_regulation_state] ?? data.latest_regulation_state : null} />
        <StateTile label="Executive Function" value={data.executive_function ? EF_LABEL[data.executive_function] ?? data.executive_function : null} />
        <StateTile label="Masking / Compensation" value={data.compensation_load ? COMPENSATION_LABEL[data.compensation_load] ?? data.compensation_load : null} />
      </div>
    </Card>
  );
}

/** Phase 5 (health-context reframe) — explicit "reduce demand" language for
 *  TOO MUCH, not just "add more capacity/rest harder"; explicit "may not be
 *  overload" language for NOT ENOUGH so under-stimulation reads as its own
 *  distinct thing rather than a lesser version of TOO MUCH. Underlying
 *  CapacityBalance classification (route.ts) is unchanged — copy only. */
const CAPACITY_BALANCE_DETAIL: Record<CapacityBalance, string> = {
  too_much: "the available responses include reducing what’s being asked of you today — not only pushing through it or resting harder once it's over.",
  sustainable: 'capacity and what’s being asked of you are broadly matched right now.',
  not_enough: 'capacity looks available — the gap may be under-stimulation rather than overload, so the right input can help as much as rest can.',
  unknown: 'no data yet to read capacity against demand.',
};

/** ── CAPACITY BALANCE (spec §11) ── */
export function CapacityBalanceCard({ data }: { data: RecoveryPayload }) {
  return (
    <Card title="Capacity Balance">
      <div className="flex items-center justify-between gap-2 text-wb-label font-medium uppercase tracking-wide">
        <span className={data.capacity_balance === 'too_much' ? 'text-wb-crit-on' : 'text-wb-ink2'}>Too Much</span>
        <span className={data.capacity_balance === 'sustainable' ? 'font-semibold text-wb-ok-on' : 'text-wb-ink2'}>Sustainable</span>
        <span className={data.capacity_balance === 'not_enough' ? 'text-wb-warn-on' : 'text-wb-ink2'}>Not Enough</span>
      </div>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-wb-line">
        <div
          className={`h-full transition-[margin,width,background-color] ${
            data.capacity_balance === 'too_much' ? 'ml-0 w-1/3 bg-wb-crit' :
            data.capacity_balance === 'sustainable' ? 'ml-[33%] w-1/3 bg-wb-ok' :
            data.capacity_balance === 'not_enough' ? 'ml-[66%] w-1/3 bg-wb-warn' : 'w-0'
          }`}
        />
      </div>
      <p className="mt-3 text-wb-label text-wb-ink2">
        {CAPACITY_BALANCE_LABEL[data.capacity_balance]} — {CAPACITY_BALANCE_DETAIL[data.capacity_balance]}
      </p>
    </Card>
  );
}

/** Phase 5 (health-context reframe) — qualitative cross-signal notes built
 *  only from fields RecoveryPayload already carries (pain_state/pain_score,
 *  executive_function, compensation_load, stimulation_state,
 *  capacity_balance, latest_capacity_state). Framed as
 *  association/decision-support, never a stop/go verdict, a diagnosis, or a
 *  fabricated combined score — each note only renders when its own real
 *  signal(s) actually support it, so an ordinary day (all fields
 *  null/typical) renders none of these. */
function contributingContextNotes(data: RecoveryPayload): { key: string; title: string; text: string }[] {
  const notes: { key: string; title: string; text: string }[] = [];

  // Pain in context — pain_state already encodes current-vs-baseline
  // (low/baseline/elevated/high); never shown as a bare number implying
  // "high pain = stop". Paired with executive function / stimulation
  // rather than shown in isolation, where those signals are also present.
  if (data.pain_state === 'elevated' || data.pain_state === 'high') {
    const efNote = data.executive_function === 'difficult' || data.executive_function === 'very_difficult'
      ? ' Executive function is also reading as harder than usual today — these often move together without one necessarily causing the other.'
      : '';
    const stimNote = data.stimulation_state === 'high'
      ? ' Stimulation is also reading high, which can make pain feel more prominent without pain itself having changed.'
      : '';
    notes.push({
      key: 'pain',
      title: 'Pain in Context',
      text: `Pain compared with your usual baseline today: ${PAIN_LABEL[data.pain_state] ?? data.pain_state}${data.pain_score != null ? ` (older 0–10 record: ${data.pain_score}/10)` : ''}. This is one input among several, not a standalone stop/go signal.${efNote}${stimNote}`,
    });
  }

  // Compensation / masking — elevated from a minor tile to a real
  // interpretive line, only when high compensation shows up alongside a
  // capacity reading that isn't itself high.
  const highCompensation = data.compensation_load === 'high' || data.compensation_load === 'extreme';
  const capacityNotHigh = data.latest_capacity_state === 'orange' || data.latest_capacity_state === 'red' || data.capacity_balance === 'too_much';
  if (highCompensation && capacityNotHigh) {
    notes.push({
      key: 'compensation',
      title: 'Compensation / Masking',
      text: 'You may be maintaining more output than today’s accessible capacity would normally support, which may increase later recovery requirement.',
    });
  }

  // Recovery Cost — a qualitative combination of existing negative signals
  // only, never a fabricated numeric score. Decision support, not a hard
  // block on acting.
  const negativeSignalCount = [
    data.stimulation_state === 'high',
    data.pain_state === 'elevated' || data.pain_state === 'high',
    highCompensation,
  ].filter(Boolean).length;
  if (negativeSignalCount >= 3) {
    notes.push({
      key: 'recovery-cost',
      title: 'Recovery Cost',
      text: 'Several signals are pointing the same way today — sensory load, pain, and/or compensation. Pushing through everything on the list today may cost more to recover from than usual. This is decision support, not a rule against acting.',
    });
  }

  return notes;
}

/** ── WHAT IS DRIVING IT (spec §7) ── */
export function WhatIsDrivingItCard({ data }: { data: RecoveryPayload }) {
  const contextNotes = contributingContextNotes(data);
  return (
    <Card title="What Is Driving It">
      {data.active_loads_today.length === 0 ? (
        <p className="text-wb-body text-wb-ink2">No active loads recorded today.</p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {data.active_loads_today.map((l, i) => (
            <Badge key={l.label} status={i === 0 ? 'warning' : 'neutral'}>
              {l.label} · {l.count}/{data.checkins_today || l.count}
            </Badge>
          ))}
        </div>
      )}
      {contextNotes.length > 0 && (
        <div className="mt-3 flex flex-col gap-2">
          {contextNotes.map((n) => (
            <div key={n.key} className="rounded-md border border-wb-line bg-wb-bg p-3">
              <div className="text-wb-label font-semibold uppercase tracking-wide text-wb-ink2">{n.title}</div>
              <p className="mt-1 text-wb-body leading-relaxed text-wb-ink">{n.text}</p>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

/** ── WHAT MY SYSTEM NEEDS (spec §9) ── */
export function WhatMySystemNeedsCard({ data }: { data: RecoveryPayload }) {
  return (
    <Card title="What My System Needs">
      {data.identified_needs_latest.length === 0 ? (
        <p className="text-wb-body text-wb-ink2">No current need recorded.</p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {data.identified_needs_latest.map((n) => (
            <Badge key={n} status="info">{n}</Badge>
          ))}
        </div>
      )}
    </Card>
  );
}

/** ── MY NEXT MOVE (spec §10) ── */
export function MyNextMoveCard({ data }: { data: RecoveryPayload }) {
  const nm = data.next_move;
  const hasNextMove = !!(nm.intervention_title);
  return (
    <Card title="My Next Move">
      {!hasNextMove ? (
        <p className="text-wb-body text-wb-ink2">No action logged yet today. Use /capacity or /helpme on the Capacity Bot to get one.</p>
      ) : (
        <>
          {nm.lever && (
            <div className="text-wb-label font-semibold uppercase tracking-[0.12em] text-wb-ink2">{LEVER_LABEL[nm.lever] ?? nm.lever}</div>
          )}
          <p className="mt-1 text-wb-lead leading-relaxed text-wb-ink">{nm.intervention_description ?? nm.intervention_title}</p>
          {nm.accepted_at && (
            <p className="mt-2 text-wb-label text-wb-ink2">
              Last tried {new Date(nm.accepted_at).toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' })}
              {nm.outcome && nm.outcome !== 'unknown' && (
                <> — <span className="font-medium capitalize text-wb-ink">{nm.outcome.replace('_', ' ')}</span></>
              )}
            </p>
          )}
        </>
      )}
    </Card>
  );
}

/** ── SYSTEM LEARNING (spec §17, renamed from Wellness Intelligence) —
 *  also reused as the PATTERNS tab's content (Human Systems redesign
 *  Phase 2/3: this is the "possible pattern" / experiment-tracking layer,
 *  a natural home for a Patterns tab). */
export function SystemLearningSection({ data, className = 'md:col-span-2' }: { data: RecoveryPayload; className?: string }) {
  // V3 Mission 4 (§15/§19) — a structured experiment takes over from the
  // narrative worthTesting() heuristic once one exists (proposed/active).
  // Most-recently-started-or-proposed wins when more than one is somehow
  // open at once (experiments are ordered newest-created-first from the
  // API, so [0] among the proposed/active ones is the newest).
  const currentExperiment = data.experiments.find((e) => e.status === 'proposed' || e.status === 'active') ?? null;
  const testingSuggestion = currentExperiment ? null : worthTesting(data);
  // Most recently finished experiment that actually has a result to show —
  // one without a result yet (e.g. marked stopped with no note) has
  // nothing for "What Changed" to say.
  const changedExperiment = data.experiments.find((e) => (e.status === 'completed' || e.status === 'stopped') && e.result) ?? null;

  return (
    <CollapsibleSection title="Patterns" className={className}>
      <div className="flex flex-col gap-3">
        <div>
          <div className="text-wb-label font-semibold uppercase tracking-[0.1em] text-wb-ink2">What I Know</div>
          <p className="mt-1 text-wb-body text-wb-ink">
            {data.checkins_last_7d} check-in{data.checkins_last_7d === 1 ? '' : 's'} recorded in the last 7 days.
          </p>
        </div>

        {(data.wellness.narrative || data.wellness.risk_flags.length > 0 || data.wellness.positive_flags.length > 0) && (
          <div>
            <div className="text-wb-label font-semibold uppercase tracking-[0.1em] text-wb-ink2">Possible Pattern</div>
            {data.wellness.narrative && (
              <p className="mt-1 text-wb-body leading-relaxed text-wb-ink2">{data.wellness.narrative}</p>
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

        {/* Phase 10 (recovery-brief consolidation, 2026-09-06) — "Wins This
            Week" was real content in the retired recovery-brief page's
            Wellness Intelligence section (health_insights.wins_this_week,
            already carried through as data.wellness.wins) but had no home
            in NOW/WHAT HELPS/PATTERNS after the tab split. Sits next to
            Possible Pattern as the positive counterpart, only rendered
            when real wins exist. */}
        {data.wellness.wins.length > 0 && (
          <div>
            <div className="text-wb-label font-semibold uppercase tracking-[0.1em] text-wb-ink2">Wins This Week</div>
            <div className="mt-1 flex flex-col gap-1">
              {data.wellness.wins.map((w, i) => (
                <div key={i} className="rounded-md border border-wb-line bg-wb-bg p-2 text-wb-body text-wb-ink">
                  {w}
                </div>
              ))}
            </div>
          </div>
        )}

        {currentExperiment && (
          <div>
            <div className="flex items-center justify-between gap-2">
              <div className="text-wb-label font-semibold uppercase tracking-[0.1em] text-wb-ink2">Worth Testing</div>
              <Badge status={currentExperiment.status === 'active' ? 'info' : 'neutral'}>
                {EXPERIMENT_STATUS_LABEL[currentExperiment.status]}
              </Badge>
            </div>
            <ExperimentCard experiment={currentExperiment} />
          </div>
        )}

        {!currentExperiment && testingSuggestion && (
          <div>
            <div className="text-wb-label font-semibold uppercase tracking-[0.1em] text-wb-ink2">Worth Testing</div>
            <p className="mt-1 text-wb-body leading-relaxed text-wb-ink2">{testingSuggestion}</p>
          </div>
        )}

        {/* V3 doc §19 fourth layer — only once an experiment has actually
            finished and left a result behind. */}
        {changedExperiment && (
          <div>
            <div className="text-wb-label font-semibold uppercase tracking-[0.1em] text-wb-ink2">What Changed</div>
            <p className="mt-1 text-wb-body leading-relaxed text-wb-ink">{changedExperiment.hypothesis}</p>
            <p className="mt-1 text-wb-body leading-relaxed text-wb-ink2">{changedExperiment.result}</p>
            <p className="mt-1 text-wb-label text-wb-ink2">
              {changedExperiment.status === 'stopped' ? 'Stopped' : 'Completed'}
              {changedExperiment.confidence ? ` · Confidence — ${changedExperiment.confidence}` : ''}
              {changedExperiment.completed_at
                ? ` · ${new Date(changedExperiment.completed_at).toLocaleDateString('en-AU')}`
                : ''}
            </p>
          </div>
        )}
      </div>
    </CollapsibleSection>
  );
}

// The composite RecoveryView() that used to wrap CapacityTodayCard +
// BurnoutRecoveryCard + CapacityBalanceCard + WhatIsDrivingItCard +
// WhatMySystemNeedsCard + MyNextMoveCard + SystemLearningSection +
// WhatHelpsMeCard + RevsPositionSection was deleted 2026-09-06 (Human
// Systems redesign final-validation cleanup): page.tsx never rendered the
// composite (only the extracted cards/sections above, individually, from
// NowView.tsx/WhatHelpsView.tsx/PatternsView.tsx), and its last caller was
// its own unit test — a dead exported function kept alive only to keep an
// old test green. See __tests__/SystemLearningSection.experiments.test.tsx,
// which now exercises SystemLearningSection directly.

/** V3 doc §15 — the structured experiment object, replacing the narrative
 *  string for the "Worth Testing" subsection whenever a proposed/active
 *  capacity_experiments row exists. Copy is deliberately framed as
 *  reversible/stoppable, never as a commitment (§15: experiments must "be
 *  reversible where practical" and "be stoppable if worse" — and must
 *  never masquerade as medical treatment). Created/updated only via the
 *  Capacity Bot's /experiment command. */
function ExperimentCard({ experiment: e }: { experiment: CapacityExperiment }) {
  return (
    <div className="mt-2 rounded-md border border-wb-line bg-wb-bg p-3">
      <p className="text-wb-body leading-relaxed text-wb-ink">
        <span className="font-medium">Hypothesis — </span>
        {e.hypothesis}
      </p>
      <p className="mt-2 text-wb-body leading-relaxed text-wb-ink2">
        <span className="font-medium text-wb-ink">Trying — </span>
        {e.proposed_change}
      </p>
      {e.baseline_window && (
        <p className="mt-2 text-wb-label leading-relaxed text-wb-ink2">
          <span className="font-medium text-wb-ink">Baseline — </span>
          {e.baseline_window}
        </p>
      )}
      {e.trial_window && (
        <p className="mt-2 text-wb-label leading-relaxed text-wb-ink2">
          <span className="font-medium text-wb-ink">Trial — </span>
          {e.trial_window}
        </p>
      )}
      {e.outcome_measures.length > 0 && (
        <div className="mt-2">
          <div className="text-wb-label font-medium text-wb-ink">Watching:</div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {e.outcome_measures.map((m) => (
              <Badge key={m} status="neutral">{m}</Badge>
            ))}
          </div>
        </div>
      )}
      <p className="mt-3 text-wb-label italic text-wb-ink2">
        Worth testing, not a commitment — stop it anytime with /experiment on the Capacity Bot if it makes things worse.
      </p>
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
