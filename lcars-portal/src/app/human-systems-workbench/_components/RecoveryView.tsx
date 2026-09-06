'use client';

import { Badge, Card } from '@/components/ui';
import { CollapsibleSection } from './CollapsibleSection';
import { WhatHelpsMeCard } from './WhatHelpsMeCard';
import {
  CAPACITY_BALANCE_LABEL,
  CAPACITY_STATE_LABEL as CAPACITY_LABEL,
  capacityStateStatus,
  EXPERIMENT_STATUS_LABEL,
  RECOVERY_STAGE_LABEL,
  STRATEGIC_POSTURE_LABEL,
  strategicPostureStatus,
  SYSTEM_TRAJECTORY_LABEL,
  systemTrajectoryStatus,
  USER_BURNOUT_FRAMING_LABEL,
  type CapacityExperiment,
  type InterventionEffectiveness,
  type RecoveryPayload,
  type RecoveryStage,
} from './types';

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

// ── REVS V3 (V3 doc §9) — RECOGNISE -> REGULATE -> RECOVER -> REBUILD ->
// REDESIGN. "These are not completion stages. They are management
// orientations that can overlap." current_recovery_stage (from the
// Burnout Trajectory engine, burnout_trajectory.py / computeStrategicPosture())
// has 6 values (protect/stabilise/recover/re_engage/rebuild/redesign) —
// more granular than REVS's 5 stages, so this maps each onto the REVS
// stage it most directly corresponds to for the purpose of highlighting
// "current priority": protect/stabilise are both early-stage load
// reduction and condition-stabilising work, which REVS has no dedicated
// stage for — REGULATE is the closest existing orientation. re_engage
// sits between recover and rebuild; REBUILD is the closer of the two
// (both gate against over-claiming readiness).
const RECOVERY_STAGE_TO_REVS: Record<RecoveryStage, 'regulate' | 'recover' | 'rebuild' | 'redesign'> = {
  protect: 'regulate',
  stabilise: 'regulate',
  recover: 'recover',
  re_engage: 'rebuild',
  rebuild: 'rebuild',
  redesign: 'redesign',
};

type RevsKey = 'recognise' | 'regulate' | 'recover' | 'rebuild' | 'redesign';
const REVS_STAGES: { key: RevsKey; label: string }[] = [
  { key: 'recognise', label: 'Recognise' },
  { key: 'regulate', label: 'Regulate' },
  { key: 'recover', label: 'Recover' },
  { key: 'rebuild', label: 'Rebuild' },
  { key: 'redesign', label: 'Redesign' },
];

/** No active trajectory stage (system_trajectory 'stable' or
 *  'insufficient_data', current_recovery_stage null) — Regulate stays the
 *  default day-to-day orientation, same as this card's previous
 *  always-hardcoded behaviour, so the common no-sustained-strain case
 *  still reads exactly as it always has. */
function activeRevsStage(stage: RecoveryStage | null): RevsKey {
  return stage ? RECOVERY_STAGE_TO_REVS[stage] : 'regulate';
}

/** Status text per REVS tile (V3 doc §9 worked example during burnout:
 *  Recognise=Ongoing, Regulate=Supportive, Recover=Current priority,
 *  Rebuild=Gated, Redesign=Active where recurring strain is clear —
 *  simplified here to "As patterns emerge" for the non-active default
 *  since this view has no redesign-candidate count to ground a stronger
 *  claim; see MedicalPayload.redesign_candidates for that, a different
 *  tab). */
function revsStatusText(key: RevsKey, active: RevsKey): string {
  if (key === 'recognise') return 'Ongoing';
  if (key === active) return 'Current priority';
  switch (key) {
    case 'regulate': return 'Supportive';
    case 'recover': return 'Gated';
    case 'rebuild': return 'Gated';
    case 'redesign': return 'As patterns emerge';
    default: return '';
  }
}

function StateTile({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="rounded-md border border-wb-line bg-wb-bg p-3">
      <div className="text-[11px] uppercase tracking-wide text-wb-ink2">{label}</div>
      <div className="mt-1 text-[13px] text-wb-ink">{value ?? 'Not recorded'}</div>
    </div>
  );
}

/** No current-day check-in — a single consolidated message rather than a
 *  hero card plus a grid of five individually-"Not recorded" tiles (Human
 *  Systems redesign Phase 4). Distinguishes "no check-in today" from
 *  "insufficient history" (system_trajectory === 'insufficient_data' gets
 *  its own distinct sentence, never folded into "your recent pattern still
 *  suggests…" — that phrase requires an actual pattern to point to). When
 *  there IS a recent pattern, names it via strategic_posture_message so
 *  the honest claim is "HQ will not assume you're recovered just because
 *  you didn't check in" rather than fabricating a specific state. */
function NoCurrentCheckinMessage({ data }: { data: RecoveryPayload }) {
  const insufficientHistory = data.system_trajectory === 'insufficient_data';
  return (
    <Card className="md:col-span-2">
      <div className="text-[11px] uppercase tracking-[0.12em] text-wb-ink2">Capacity Today</div>
      <p className="mt-2 text-[14px] leading-relaxed text-wb-ink">
        No current check-in.{' '}
        {insufficientHistory
          ? "There isn't enough recent history yet to infer a pattern either — this is an early-data gap, not a settled read."
          : `Your recent pattern still suggests: ${data.strategic_posture_message} HQ will not assume you are recovered simply because you have not checked in today.`}
      </p>
      <p className="mt-2 text-[13px] text-wb-ink2">
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
  if (!data.data_available) return <NoCurrentCheckinMessage data={data} />;

  return (
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
  );
}

/** ── BURNOUT & RECOVERY (V3 doc §5/§18) — the TRAJECTORY signal, never
 *  collapsed into the NOW capacity/posture above (V3 doc §2). Always
 *  rendered, even when trajectory_confidence is low/insufficient — Rule F
 *  requires SAYING so, not hiding the card. */
export function BurnoutRecoveryCard({ data }: { data: RecoveryPayload }) {
  return (
    <Card className="md:col-span-2">
      <div className="flex items-start justify-between gap-3">
        <div className="text-[11px] uppercase tracking-[0.12em] text-wb-ink2">Burnout &amp; Recovery</div>
        <Badge status={strategicPostureStatus(data.strategic_posture)}>
          {STRATEGIC_POSTURE_LABEL[data.strategic_posture]}
        </Badge>
      </div>

      {data.user_burnout_framing && (
        <p className="mt-2 text-[13px] text-wb-ink2">
          <span className="font-medium text-wb-ink">User framing — </span>
          {USER_BURNOUT_FRAMING_LABEL[data.user_burnout_framing]}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Badge status={systemTrajectoryStatus(data.system_trajectory)}>
          {SYSTEM_TRAJECTORY_LABEL[data.system_trajectory]}
        </Badge>
        {data.current_recovery_stage && (
          <span className="text-[12px] text-wb-ink2">
            Recovery stage: {RECOVERY_STAGE_LABEL[data.current_recovery_stage]}
          </span>
        )}
      </div>

      <p className="mt-3 text-[14px] leading-relaxed text-wb-ink">{data.strategic_posture_message}</p>

      {/* Rule F — say "insufficient data" explicitly rather than hiding
          the card or fabricating confidence. */}
      <p className="mt-3 text-[12px] text-wb-ink2">
        Confidence — {data.trajectory_confidence === 'low' ? 'Low' : data.trajectory_confidence === 'moderate' ? 'Moderate' : 'High'}
        {data.system_trajectory === 'insufficient_data'
          ? '. Not enough recent check-ins yet to read a sustained-strain trend.'
          : data.trajectory_confidence === 'low'
            ? '. Based on a small number of recent check-ins — an early read, not a settled pattern.'
            : '.'}
      </p>
    </Card>
  );
}

/** ── CAPACITY BALANCE (spec §11) ── */
export function CapacityBalanceCard({ data }: { data: RecoveryPayload }) {
  return (
    <Card title="Capacity Balance">
      <div className="flex items-center justify-between gap-2 text-[12px] font-medium uppercase tracking-wide">
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
      <p className="mt-3 text-[12px] text-wb-ink2">{CAPACITY_BALANCE_LABEL[data.capacity_balance]} — regulation may mean reducing input or adding the right input.</p>
    </Card>
  );
}

/** ── WHAT IS DRIVING IT (spec §7) ── */
export function WhatIsDrivingItCard({ data }: { data: RecoveryPayload }) {
  return (
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
  );
}

/** ── WHAT MY SYSTEM NEEDS (spec §9) ── */
export function WhatMySystemNeedsCard({ data }: { data: RecoveryPayload }) {
  return (
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
  );
}

/** ── MY NEXT MOVE (spec §10) ── */
export function MyNextMoveCard({ data }: { data: RecoveryPayload }) {
  const nm = data.next_move;
  const hasNextMove = !!(nm.intervention_title);
  return (
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
    <CollapsibleSection title="System Learning" className={className}>
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

        {currentExperiment && (
          <div>
            <div className="flex items-center justify-between gap-2">
              <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-wb-ink2">Worth Testing</div>
              <Badge status={currentExperiment.status === 'active' ? 'info' : 'neutral'}>
                {EXPERIMENT_STATUS_LABEL[currentExperiment.status]}
              </Badge>
            </div>
            <ExperimentCard experiment={currentExperiment} />
          </div>
        )}

        {!currentExperiment && testingSuggestion && (
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-wb-ink2">Worth Testing</div>
            <p className="mt-1 text-[13px] leading-relaxed text-wb-ink2">{testingSuggestion}</p>
          </div>
        )}

        {/* V3 doc §19 fourth layer — only once an experiment has actually
            finished and left a result behind. */}
        {changedExperiment && (
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-wb-ink2">What Changed</div>
            <p className="mt-1 text-[13px] leading-relaxed text-wb-ink">{changedExperiment.hypothesis}</p>
            <p className="mt-1 text-[13px] leading-relaxed text-wb-ink2">{changedExperiment.result}</p>
            <p className="mt-1 text-[12px] text-wb-ink2">
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

/** ── MY REVS POSITION (V3 doc §9) — RECOGNISE -> REGULATE -> RECOVER ->
 *  REBUILD -> REDESIGN, dynamic from the Burnout Trajectory engine's
 *  current_recovery_stage instead of hardcoding Regulate as always-current.
 *  Orientation, not a maturity score. */
export function RevsPositionSection({ data, className = 'md:col-span-2' }: { data: RecoveryPayload; className?: string }) {
  const activeRevs = activeRevsStage(data.current_recovery_stage);
  return (
    <CollapsibleSection title="My REVS Position" className={className}>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        {REVS_STAGES.map(({ key, label }) => {
          const status = revsStatusText(key, activeRevs);
          const isCurrent = status === 'Current priority';
          return (
            <div
              key={key}
              className={
                isCurrent
                  ? 'rounded-md border-2 border-wb-sage-deep bg-wb-sage-deep/10 p-3 text-center'
                  : 'rounded-md border border-wb-line bg-wb-bg p-3 text-center'
              }
            >
              <div className={isCurrent ? 'text-[11px] font-semibold uppercase tracking-wide text-wb-sage-deep' : 'text-[11px] uppercase tracking-wide text-wb-ink2'}>
                {label}
              </div>
              <div className={isCurrent ? 'mt-1 text-[12px] font-medium text-wb-ink' : 'mt-1 text-[12px] text-wb-ink2'}>
                {status}
              </div>
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-[12px] text-wb-ink2">
        A management orientation, not a completion score — these can overlap. See &ldquo;What May Need to Change&rdquo; for redesign candidates.
      </p>
    </CollapsibleSection>
  );
}

/** Recovery tab — "What does my system need today?" VNext consolidation
 *  (Human_Systems_Workbench_VNext_Consolidation_Mission_Scope.md WP02-04):
 *  leads with Capacity Today, the current-state grid, Capacity Balance,
 *  what's driving it, what the system needs, compensation cost, and the
 *  next recommended move — in that order, matching the doc's
 *  STATE→INFLUENCES→NEED→ACTION model (§3).
 *
 *  Human Systems redesign (2026-09-06): the page no longer renders this
 *  composite directly (it's been decomposed into the exported cards/
 *  sections above, assembled by NowView.tsx/PatternsView.tsx per the new
 *  NOW/WHAT HELPS/PATTERNS/TRENDS tab structure) — kept here, unchanged in
 *  behaviour, because __tests__/RecoveryView.experiments.test.tsx still
 *  exercises it as a unit. */
export function RecoveryView({ data, interventionEffectiveness }: { data: RecoveryPayload; interventionEffectiveness: InterventionEffectiveness[] }) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <CapacityTodayCard data={data} />
      <BurnoutRecoveryCard data={data} />
      <CapacityBalanceCard data={data} />
      <WhatIsDrivingItCard data={data} />
      <WhatMySystemNeedsCard data={data} />
      <MyNextMoveCard data={data} />
      <SystemLearningSection data={data} />
      <WhatHelpsMeCard data={interventionEffectiveness} />
      <RevsPositionSection data={data} />
    </div>
  );
}

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
      <p className="text-[13px] leading-relaxed text-wb-ink">
        <span className="font-medium">Hypothesis — </span>
        {e.hypothesis}
      </p>
      <p className="mt-2 text-[13px] leading-relaxed text-wb-ink2">
        <span className="font-medium text-wb-ink">Trying — </span>
        {e.proposed_change}
      </p>
      {e.baseline_window && (
        <p className="mt-2 text-[12px] leading-relaxed text-wb-ink2">
          <span className="font-medium text-wb-ink">Baseline — </span>
          {e.baseline_window}
        </p>
      )}
      {e.trial_window && (
        <p className="mt-2 text-[12px] leading-relaxed text-wb-ink2">
          <span className="font-medium text-wb-ink">Trial — </span>
          {e.trial_window}
        </p>
      )}
      {e.outcome_measures.length > 0 && (
        <div className="mt-2">
          <div className="text-[12px] font-medium text-wb-ink">Watching:</div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {e.outcome_measures.map((m) => (
              <Badge key={m} status="neutral">{m}</Badge>
            ))}
          </div>
        </div>
      )}
      <p className="mt-3 text-[11px] italic text-wb-ink2">
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
