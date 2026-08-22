'use client';

import { useEffect, useId, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { WorkbenchShell, Card, Badge, Button, Input } from '@/components/ui';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import {
  makeEasier,
  makeShorter,
  swapExercise,
  youtubeSearchUrl,
  SESSION_TYPE_LABELS,
  type EnergyState,
  type ExerciseRow,
  type GeneratedSession,
  type PlanExercise,
  type ReadinessInput,
} from '@/lib/physical-readiness';

const TIMED_PATTERNS = new Set(['cardio', 'mobility', 'breathing']);

type Step = { slot: 'warmup' | 'exercise' | 'cooldown'; index: number; plan: PlanExercise };

function buildSteps(plan: GeneratedSession): Step[] {
  const steps: Step[] = [];
  if (plan.warmup) steps.push({ slot: 'warmup', index: -1, plan: plan.warmup });
  plan.exercises.forEach((e, i) => steps.push({ slot: 'exercise', index: i, plan: e }));
  if (plan.cooldown) steps.push({ slot: 'cooldown', index: -1, plan: plan.cooldown });
  return steps;
}

function recomputeDuration(plan: GeneratedSession): number {
  return (
    (plan.warmup?.durationMinutes ?? 0) +
    plan.exercises.reduce((sum, e) => sum + e.durationMinutes, 0) +
    (plan.cooldown?.durationMinutes ?? 0)
  );
}

// Semantic colour scale (good→bad), wb tokens only — mirrors the check-in energy selector.
const ENERGY_AFTER_OPTIONS: { value: EnergyState; label: string; tone: string }[] = [
  { value: 'green', label: 'Green', tone: 'border-wb-ok bg-wb-ok/15 text-wb-ok-on' },
  { value: 'yellow', label: 'Yellow', tone: 'border-wb-warn bg-wb-warn/15 text-wb-warn-on' },
  { value: 'orange', label: 'Orange', tone: 'border-wb-warn bg-wb-warn/30 text-wb-warn-on' },
  { value: 'red', label: 'Red', tone: 'border-wb-crit bg-wb-crit/15 text-wb-crit-on' },
];

const MOOD_OPTIONS = ['Worse', 'Same', 'Better'];

function LabeledRange({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
}) {
  const id = useId();
  return (
    <div>
      <div className="flex items-center justify-between">
        <label htmlFor={id} className="text-[10px] uppercase tracking-widest text-wb-ink2">{label}</label>
        <span className="font-serif text-sm font-bold text-wb-ink">{value}/10</span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-wb-sage-deep"
      />
    </div>
  );
}

export default function WorkoutRunnerPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.id as string;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sessionRow, setSessionRow] = useState<{ id: string; started_at: string; session_type: string } | null>(null);
  const [plan, setPlan] = useState<GeneratedSession | null>(null);
  const [readinessInput, setReadinessInput] = useState<ReadinessInput | null>(null);
  const [allExercises, setAllExercises] = useState<ExerciseRow[]>([]);

  const [phase, setPhase] = useState<'overview' | 'exercise' | 'completion' | 'done'>('overview');
  const [stepIndex, setStepIndex] = useState(0);
  const [completedCount, setCompletedCount] = useState(0);
  const [skippedCount, setSkippedCount] = useState(0);
  const [wasStopped, setWasStopped] = useState(false);

  // per-step logging draft
  const [setsCompleted, setSetsCompleted] = useState('');
  const [repsCompleted, setRepsCompleted] = useState('');
  const [weightUsed, setWeightUsed] = useState('');
  const [effortScore, setEffortScore] = useState(5);
  const [painDuring, setPainDuring] = useState(0);
  const [stepNotes, setStepNotes] = useState('');

  // completion draft
  const [energyAfter, setEnergyAfter] = useState<EnergyState | ''>('');
  const [moodAfter, setMoodAfter] = useState('');
  const [painAfterBack, setPainAfterBack] = useState(0);
  const [painAfterGeneral, setPainAfterGeneral] = useState(0);
  const [completionNotes, setCompletionNotes] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const supabase = createSupabaseBrowserClient();
    (async () => {
      const { data: session, error: sessionErr } = await supabase
        .from('physical_workout_sessions')
        .select('id, started_at, session_type, generated_plan_json, readiness_checkin_id')
        .eq('id', sessionId)
        .single();

      if (sessionErr || !session) {
        setError(sessionErr?.message ?? 'Session not found.');
        setLoading(false);
        return;
      }
      setSessionRow({ id: session.id, started_at: session.started_at, session_type: session.session_type });
      setPlan(session.generated_plan_json as GeneratedSession);

      if (session.readiness_checkin_id) {
        const { data: checkin } = await supabase
          .from('physical_readiness_checkins')
          .select('*')
          .eq('id', session.readiness_checkin_id)
          .single();
        if (checkin) {
          setReadinessInput({
            energyState: checkin.energy_state,
            backPain: checkin.back_pain,
            kneePain: checkin.knee_pain,
            anklePain: checkin.ankle_pain,
            neckShoulderPain: checkin.neck_shoulder_pain,
            generalPain: checkin.general_pain,
            timeAvailableMinutes: checkin.time_available_minutes,
            sessionIntent: checkin.session_intent,
          });
        }
      }

      const { data: exercises } = await supabase
        .from('physical_exercises')
        .select('*')
        .in('status', ['active', 'needs_review']);
      setAllExercises((exercises as ExerciseRow[]) ?? []);

      setLoading(false);
    })();
  }, [sessionId]);

  const steps = useMemo(() => (plan ? buildSteps(plan) : []), [plan]);
  const currentStep = steps[stepIndex] ?? null;

  function resetStepDraft(step: Step) {
    setSetsCompleted(String(step.plan.sets || ''));
    setRepsCompleted(String(step.plan.reps || ''));
    setWeightUsed('');
    setEffortScore(5);
    setPainDuring(0);
    setStepNotes('');
  }

  function beginWorkout() {
    if (steps.length === 0) return;
    resetStepDraft(steps[0]);
    setStepIndex(0);
    setPhase('exercise');
  }

  function updatePlanSlot(step: Step, updated: PlanExercise) {
    setPlan((prev) => {
      if (!prev) return prev;
      const next: GeneratedSession = { ...prev };
      if (step.slot === 'warmup') next.warmup = updated;
      else if (step.slot === 'cooldown') next.cooldown = updated;
      else next.exercises = prev.exercises.map((e, i) => (i === step.index ? updated : e));
      next.estimatedDurationMinutes = recomputeDuration(next);
      return next;
    });
  }

  function handleMakeEasier() {
    if (!currentStep) return;
    const updated = makeEasier(currentStep.plan);
    updatePlanSlot(currentStep, updated);
    setSetsCompleted(String(updated.sets || ''));
    setRepsCompleted(String(updated.reps || ''));
  }

  function handleSwap() {
    if (!currentStep || !plan || !readinessInput) return;
    const alt = swapExercise(currentStep.plan, plan, allExercises, readinessInput);
    if (!alt) return;
    updatePlanSlot(currentStep, alt);
    resetStepDraft({ ...currentStep, plan: alt });
  }

  function handleOverviewMakeShorter() {
    setPlan((prev) => (prev ? makeShorter(prev) : prev));
  }

  async function logCurrentStep(skipped: boolean) {
    if (!currentStep || !sessionRow) return;
    const isTimed = TIMED_PATTERNS.has(currentStep.plan.exercise.movement_pattern);
    await fetch('/api/human-systems/readiness/exercise-log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        workout_session_id: sessionRow.id,
        exercise_id: currentStep.plan.exercise.id,
        planned_sets: currentStep.plan.sets,
        planned_reps: currentStep.plan.reps,
        completed_sets: skipped ? 0 : isTimed ? 1 : Number(setsCompleted) || 0,
        completed_reps: skipped ? 0 : isTimed ? 0 : Number(repsCompleted) || 0,
        weight_used: skipped ? null : weightUsed || null,
        effort_score: skipped ? null : effortScore,
        pain_during: skipped ? null : painDuring,
        skipped,
        skip_reason: skipped ? stepNotes || 'Not specified' : null,
        notes: skipped ? null : stepNotes || null,
      }),
    });
    if (skipped) setSkippedCount((c) => c + 1);
    else setCompletedCount((c) => c + 1);
  }

  async function handleDone() {
    await logCurrentStep(false);
    advance();
  }

  async function handleSkip() {
    await logCurrentStep(true);
    advance();
  }

  function advance() {
    const nextIndex = stepIndex + 1;
    if (nextIndex >= steps.length) {
      setPhase('completion');
      return;
    }
    resetStepDraft(steps[nextIndex]);
    setStepIndex(nextIndex);
  }

  function handleStopSession() {
    setWasStopped(true);
    setPhase('completion');
  }

  async function handleSubmitCompletion() {
    if (!sessionRow) return;
    setSaving(true);
    const startedAtMs = new Date(sessionRow.started_at).getTime();
    const durationMinutes = Math.max(1, Math.round((Date.now() - startedAtMs) / 60000));
    const totalSteps = steps.length;
    const loggedSteps = completedCount + skippedCount;
    const status = wasStopped
      ? loggedSteps === 0
        ? 'stopped'
        : 'partially_completed'
      : loggedSteps < totalSteps
        ? 'partially_completed'
        : 'completed';

    await fetch(`/api/human-systems/readiness/session/${sessionRow.id}/complete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        status,
        completed_at: new Date().toISOString(),
        duration_minutes: durationMinutes,
        energy_after: energyAfter || null,
        pain_after_json: { back_pain: painAfterBack, general_pain: painAfterGeneral },
        mood_after: moodAfter || null,
        notes: completionNotes || null,
      }),
    });

    // core_events has RLS with no anon/authenticated policies (service_role
    // only) — must go through a server route, not the browser client.
    await fetch('/api/physical-readiness/complete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sessionType: sessionRow.session_type,
        metrics: {
          session_type: sessionRow.session_type,
          duration_minutes: durationMinutes,
          completion_status: status,
          energy_before: readinessInput?.energyState ?? null,
          energy_after: energyAfter || null,
          pain_before: readinessInput
            ? {
                back_pain: readinessInput.backPain,
                knee_pain: readinessInput.kneePain,
                ankle_pain: readinessInput.anklePain,
                neck_shoulder_pain: readinessInput.neckShoulderPain,
                general_pain: readinessInput.generalPain,
              }
            : null,
          pain_after: { back_pain: painAfterBack, general_pain: painAfterGeneral },
          exercises_completed: completedCount,
          exercises_skipped: skippedCount,
          notes: completionNotes || null,
        },
      }),
    }).catch(() => { /* non-blocking, matches publishEvent's own contract */ });

    setSaving(false);
    setPhase('done');
  }

  const shellBack = { href: '/human-systems-workbench?domain=readiness', label: 'Readiness' };

  if (loading) {
    return (
      <WorkbenchShell title="Session" eyebrow="Fitness Readiness" tagline="USS TJR · Human Systems · Recovery · Medical · Readiness · Evidence-informed, non-diagnostic" back={shellBack}>
        <p className="p-6 text-center text-sm text-wb-ink2">Loading session…</p>
      </WorkbenchShell>
    );
  }
  if (error || !plan || !sessionRow) {
    return (
      <WorkbenchShell title="Session" eyebrow="Fitness Readiness" tagline="USS TJR · Human Systems · Recovery · Medical · Readiness · Evidence-informed, non-diagnostic" back={shellBack}>
        <div className="flex flex-col gap-3">
          <div className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 px-4 py-3 text-sm text-wb-crit-on">
            {error ?? 'Session could not be loaded.'}
          </div>
          <Link href="/human-systems-workbench?domain=readiness" className="text-sm text-wb-sage-deep underline">
            Back to Readiness
          </Link>
        </div>
      </WorkbenchShell>
    );
  }

  if (phase === 'done') {
    return (
      <WorkbenchShell title="Session" eyebrow="Fitness Readiness" tagline="USS TJR · Human Systems · Recovery · Medical · Readiness · Evidence-informed, non-diagnostic" back={shellBack}>
        <div className="flex flex-col items-center justify-center gap-4 py-16">
          <div className="flex h-14 w-14 items-center justify-center rounded-full border border-wb-ok bg-wb-ok/10">
            <span aria-hidden className="font-serif text-2xl text-wb-ok-on">✓</span>
          </div>
          <p className="font-serif text-lg font-bold text-wb-ok-on">Session logged</p>
          <Link
            href="/human-systems-workbench?domain=readiness"
            className="rounded-md bg-wb-sage-deep px-4 py-2 text-sm font-bold uppercase tracking-wider text-white transition hover:opacity-90"
          >
            Back to Readiness
          </Link>
        </div>
      </WorkbenchShell>
    );
  }

  if (phase === 'completion') {
    return (
      <WorkbenchShell title="Session" eyebrow="Fitness Readiness" tagline="USS TJR · Human Systems · Recovery · Medical · Readiness · Evidence-informed, non-diagnostic" back={shellBack}>
        <div className="flex flex-col gap-4">
          <Card title="Finishing Up">
            <p className="mb-2 text-[11px] uppercase tracking-[0.12em] text-wb-ink2">{SESSION_TYPE_LABELS[plan.sessionType]}</p>
            <p className="text-xs text-wb-ink2">
              {completedCount} done, {skippedCount} skipped{wasStopped ? ' · session stopped early' : ''}.
            </p>
          </Card>

          <Card title="Energy After">
            <div className="grid grid-cols-4 gap-2">
              {ENERGY_AFTER_OPTIONS.map((opt) => {
                const selected = energyAfter === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => setEnergyAfter(opt.value)}
                    className={`rounded-md py-2 text-xs font-bold uppercase transition-colors ${
                      selected
                        ? `border-2 ${opt.tone}`
                        : 'border border-wb-line bg-wb-surface text-wb-ink2 hover:bg-wb-line'
                    }`}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </Card>

          <Card title="Pain After">
            <div className="flex flex-col gap-3">
              <LabeledRange label="Back pain" value={painAfterBack} min={0} max={10} onChange={setPainAfterBack} />
              <LabeledRange label="General pain" value={painAfterGeneral} min={0} max={10} onChange={setPainAfterGeneral} />
            </div>
          </Card>

          <Card title="Mood After">
            <div className="flex gap-2">
              {MOOD_OPTIONS.map((m) => {
                const selected = moodAfter === m;
                return (
                  <button
                    key={m}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => setMoodAfter(m)}
                    className={`flex-1 rounded-md border py-2 text-xs font-semibold uppercase transition-colors ${
                      selected
                        ? 'bg-wb-sage-deep text-white'
                        : 'border border-wb-line bg-wb-surface text-wb-ink2 hover:bg-wb-line'
                    }`}
                  >
                    {m}
                  </button>
                );
              })}
            </div>
          </Card>

          <Card title="Notes">
            <p className="mb-3 text-[11px] uppercase tracking-[0.12em] text-wb-ink2">Optional</p>
            <textarea
              aria-label="Completion notes"
              value={completionNotes}
              onChange={(e) => setCompletionNotes(e.target.value)}
              rows={2}
              className="w-full resize-none rounded-md border border-wb-line bg-wb-surface px-3 py-2 text-sm text-wb-ink placeholder:text-wb-ink2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
            />
          </Card>

          <Button
            variant="primary"
            onClick={handleSubmitCompletion}
            disabled={saving}
            className="w-full py-4 text-base font-bold uppercase tracking-[0.2em]"
          >
            {saving ? 'Saving…' : 'Finish & Log Session'}
          </Button>
        </div>
      </WorkbenchShell>
    );
  }

  if (phase === 'overview') {
    return (
      <WorkbenchShell title="Session" eyebrow="Fitness Readiness" tagline="USS TJR · Human Systems · Recovery · Medical · Readiness · Evidence-informed, non-diagnostic" back={shellBack}>
        <div className="flex flex-col gap-4">
          <Card title={SESSION_TYPE_LABELS[plan.sessionType]}>
            <div className="mb-2 flex items-center justify-between gap-3">
              <p className="text-[11px] uppercase tracking-[0.12em] text-wb-ink2">~{plan.estimatedDurationMinutes} min</p>
              {plan.leaveGymPermission && <Badge status="warning">Leave-gym OK</Badge>}
            </div>
            <p className="text-xs leading-relaxed text-wb-ink2">{plan.reason}</p>
          </Card>

          <Card title="Plan">
            <ul className="flex flex-col gap-2">
              {plan.warmup && (
                <li className="rounded-md border border-wb-line bg-wb-bg px-3 py-2 text-sm text-wb-ink">
                  <span className="text-[10px] uppercase tracking-widest text-wb-ink2">Warm-up · </span>
                  {plan.warmup.exercise.name}
                </li>
              )}
              {plan.exercises.map((e, i) => (
                <li key={e.exercise.id + i} className="rounded-md border border-wb-line bg-wb-bg px-3 py-2 text-sm text-wb-ink">
                  {e.exercise.name}{' '}
                  <span className="text-wb-ink2">
                    ({e.sets}x{e.reps || '—'})
                  </span>
                </li>
              ))}
              {plan.cooldown && (
                <li className="rounded-md border border-wb-line bg-wb-bg px-3 py-2 text-sm text-wb-ink">
                  <span className="text-[10px] uppercase tracking-widest text-wb-ink2">Cooldown · </span>
                  {plan.cooldown.exercise.name}
                </li>
              )}
            </ul>
            {plan.exercises.length > 1 && (
              <button
                type="button"
                onClick={handleOverviewMakeShorter}
                className="mt-3 w-full rounded-md border border-wb-line px-3 py-2 text-xs font-semibold uppercase tracking-wider text-wb-ink2 transition hover:bg-wb-line"
              >
                Make Session Shorter
              </button>
            )}
          </Card>

          <Button
            variant="primary"
            onClick={beginWorkout}
            className="w-full py-4 text-base font-bold uppercase tracking-[0.2em]"
          >
            Begin Workout
          </Button>
          <Link href="/human-systems-workbench?domain=readiness" className="text-center text-xs text-wb-ink2 underline">
            Not now — back to Readiness
          </Link>
        </div>
      </WorkbenchShell>
    );
  }

  // phase === 'exercise'
  if (!currentStep) return null;
  const ex = currentStep.plan.exercise;
  const isTimed = TIMED_PATTERNS.has(ex.movement_pattern);
  const videoUrl = ex.preferred_video_url || youtubeSearchUrl(ex.video_search_query);

  return (
    <WorkbenchShell title="Session" eyebrow="Fitness Readiness" tagline="USS TJR · Human Systems · Recovery · Medical · Readiness · Evidence-informed, non-diagnostic" back={shellBack}>
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-[0.25em] text-wb-ink2">
            Step {stepIndex + 1} of {steps.length}
          </span>
          <button
            type="button"
            onClick={handleStopSession}
            className="text-xs font-semibold uppercase tracking-wider text-wb-crit-on"
          >
            Stop Session
          </button>
        </div>

        <Card title={ex.name}>
          <p className="mb-2 text-[11px] uppercase tracking-[0.12em] text-wb-ink2">{ex.equipment}</p>
          <p className="mb-2 font-serif text-2xl font-bold text-wb-ink">{currentStep.plan.beginnerTarget}</p>
          <p className="text-xs leading-relaxed text-wb-ink2">{currentStep.plan.why}</p>
          {currentStep.plan.painCaution && (
            <p className="mt-2 rounded-md border border-wb-crit/30 bg-wb-crit/10 px-3 py-2 text-xs text-wb-crit-on">
              {currentStep.plan.painCaution}
            </p>
          )}
        </Card>

        <Card title="How to do it">
          <div className="flex flex-col gap-2 text-xs">
            <p><span className="uppercase tracking-wider text-wb-ink2">Setup: </span>{currentStep.plan.setupCues.join(' ')}</p>
            <p><span className="uppercase tracking-wider text-wb-ink2">Form: </span>{currentStep.plan.formCues.join(' · ')}</p>
            <p><span className="uppercase tracking-wider text-wb-ink2">Avoid: </span>{currentStep.plan.commonMistakes.join(' · ')}</p>
          </div>
          <a
            href={videoUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-3 inline-block rounded-md border border-wb-line px-3 py-2 text-xs font-semibold uppercase tracking-wider text-wb-ink2 transition hover:bg-wb-line"
          >
            Find Guide Video ↗
          </a>
        </Card>

        <Card title="Log This One">
          {!isTimed && (
            <div className="mb-3 grid grid-cols-3 gap-2">
              <Input
                label="Sets"
                type="number"
                min={0}
                value={setsCompleted}
                onChange={(e) => setSetsCompleted(e.target.value)}
              />
              <Input
                label="Reps"
                type="number"
                min={0}
                value={repsCompleted}
                onChange={(e) => setRepsCompleted(e.target.value)}
              />
              <Input
                label="Weight"
                type="text"
                value={weightUsed}
                onChange={(e) => setWeightUsed(e.target.value)}
                placeholder="e.g. 15kg"
              />
            </div>
          )}
          <div className="flex flex-col gap-3">
            <LabeledRange label="Effort" value={effortScore} min={1} max={10} onChange={setEffortScore} />
            <LabeledRange label="Pain during" value={painDuring} min={0} max={10} onChange={setPainDuring} />
          </div>
        </Card>

        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={handleSwap}
            className="rounded-md border border-wb-line px-3 py-3 text-xs font-semibold uppercase tracking-wider text-wb-ink2 transition hover:bg-wb-line"
          >
            Swap Exercise
          </button>
          <button
            type="button"
            onClick={handleMakeEasier}
            className="rounded-md border border-wb-line px-3 py-3 text-xs font-semibold uppercase tracking-wider text-wb-ink2 transition hover:bg-wb-line"
          >
            Make Easier
          </button>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={handleSkip}
            className="rounded-md border border-wb-crit/40 bg-wb-crit/10 px-3 py-4 text-sm font-bold uppercase tracking-wider text-wb-crit-on transition hover:bg-wb-crit/20"
          >
            Skip
          </button>
          <button
            type="button"
            onClick={handleDone}
            className="rounded-md bg-wb-sage-deep px-3 py-4 text-sm font-bold uppercase tracking-wider text-white transition hover:opacity-90"
          >
            Done
          </button>
        </div>
      </div>
    </WorkbenchShell>
  );
}
