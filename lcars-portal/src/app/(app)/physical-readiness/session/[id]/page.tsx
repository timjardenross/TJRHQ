'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { publishEvent } from '@/lib/core-events';
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

const ENERGY_AFTER_OPTIONS: { value: EnergyState; label: string }[] = [
  { value: 'green', label: 'Green' },
  { value: 'yellow', label: 'Yellow' },
  { value: 'orange', label: 'Orange' },
  { value: 'red', label: 'Red' },
];

const MOOD_OPTIONS = ['Worse', 'Same', 'Better'];

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
    const supabase = createSupabaseBrowserClient();
    const isTimed = TIMED_PATTERNS.has(currentStep.plan.exercise.movement_pattern);
    await supabase.from('physical_workout_exercise_logs').insert({
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
    const supabase = createSupabaseBrowserClient();
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

    await supabase
      .from('physical_workout_sessions')
      .update({
        status,
        completed_at: new Date().toISOString(),
        duration_minutes: durationMinutes,
        energy_after: energyAfter || null,
        pain_after_json: { back_pain: painAfterBack, general_pain: painAfterGeneral },
        mood_after: moodAfter || null,
        notes: completionNotes || null,
      })
      .eq('id', sessionRow.id);

    await publishEvent(supabase, {
      eventType: 'physical_readiness.workout_completed',
      domain: 'physical-readiness',
      source: 'lcars-portal/physical-readiness',
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
    });

    setSaving(false);
    setPhase('done');
  }

  if (loading) {
    return <p className="p-6 text-center text-sm text-lcars-muted">Loading session…</p>;
  }
  if (error || !plan || !sessionRow) {
    return (
      <div className="flex flex-col gap-3">
        <p className="rounded-lcars border border-operations/40 bg-operations/10 px-4 py-3 text-sm text-operations-on">
          {error ?? 'Session could not be loaded.'}
        </p>
        <Link href="/physical-readiness" className="text-sm text-medical-on underline">
          Back to Physical Readiness
        </Link>
      </div>
    );
  }

  if (phase === 'done') {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-16">
        <div className="flex h-14 w-14 items-center justify-center rounded-full border border-status bg-status/10">
          <span className="font-lcars text-2xl text-status-on">✓</span>
        </div>
        <p className="font-lcars text-lg font-bold text-status-on">Session logged</p>
        <Link
          href="/physical-readiness"
          className="rounded-lcars bg-medical px-4 py-2 text-sm font-bold uppercase tracking-wider text-white"
        >
          Back to Physical Readiness
        </Link>
      </div>
    );
  }

  if (phase === 'completion') {
    return (
      <div className="flex flex-col gap-4">
        <LCARSPanel title="Finishing Up" accent="medical" eyebrow={SESSION_TYPE_LABELS[plan.sessionType]}>
          <p className="text-xs text-lcars-muted">
            {completedCount} done, {skippedCount} skipped{wasStopped ? ' · session stopped early' : ''}.
          </p>
        </LCARSPanel>

        <LCARSPanel title="Energy After" accent="medical">
          <div className="grid grid-cols-4 gap-2">
            {ENERGY_AFTER_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setEnergyAfter(opt.value)}
                className={`rounded-lcars border py-2 text-xs font-bold uppercase transition-colors ${
                  energyAfter === opt.value ? 'border-medical bg-medical/20 text-medical-on' : 'border-edge bg-space/40 text-lcars-muted'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </LCARSPanel>

        <LCARSPanel title="Pain After" accent="medical">
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <label className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted">Back pain</label>
              <span className="font-lcars text-sm font-bold">{painAfterBack}/10</span>
            </div>
            <input type="range" min={0} max={10} value={painAfterBack} onChange={(e) => setPainAfterBack(Number(e.target.value))} className="w-full accent-medical" />
            <div className="flex items-center justify-between">
              <label className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted">General pain</label>
              <span className="font-lcars text-sm font-bold">{painAfterGeneral}/10</span>
            </div>
            <input type="range" min={0} max={10} value={painAfterGeneral} onChange={(e) => setPainAfterGeneral(Number(e.target.value))} className="w-full accent-medical" />
          </div>
        </LCARSPanel>

        <LCARSPanel title="Mood After" accent="medical">
          <div className="flex gap-2">
            {MOOD_OPTIONS.map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMoodAfter(m)}
                className={`flex-1 rounded-lcars border py-2 text-xs font-semibold uppercase transition-colors ${
                  moodAfter === m ? 'border-medical bg-medical/20 text-medical-on' : 'border-edge bg-space/40 text-lcars-muted'
                }`}
              >
                {m}
              </button>
            ))}
          </div>
        </LCARSPanel>

        <LCARSPanel title="Notes" accent="medical" eyebrow="Optional">
          <textarea
            value={completionNotes}
            onChange={(e) => setCompletionNotes(e.target.value)}
            rows={2}
            className="w-full rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text resize-none focus:border-medical focus:outline-none"
          />
        </LCARSPanel>

        <button
          onClick={handleSubmitCompletion}
          disabled={saving}
          className="w-full rounded-lcars bg-medical px-4 py-4 font-lcars text-base font-bold uppercase tracking-[0.2em] text-white disabled:opacity-40"
        >
          {saving ? 'Saving…' : 'Finish & Log Session'}
        </button>
      </div>
    );
  }

  if (phase === 'overview') {
    return (
      <div className="flex flex-col gap-4">
        <LCARSPanel
          title={SESSION_TYPE_LABELS[plan.sessionType]}
          accent="medical"
          eyebrow={`~${plan.estimatedDurationMinutes} min`}
          actions={plan.leaveGymPermission ? <StatusBadge label="Leave-gym OK" tone="operations" /> : undefined}
        >
          <p className="text-xs text-lcars-muted leading-relaxed">{plan.reason}</p>
        </LCARSPanel>

        <LCARSPanel title="Plan" accent="medical">
          <ul className="flex flex-col gap-2">
            {plan.warmup && (
              <li className="rounded-lcars border border-edge bg-space/40 px-3 py-2 text-sm text-lcars-text">
                <span className="text-[10px] uppercase tracking-widest text-lcars-muted">Warm-up · </span>
                {plan.warmup.exercise.name}
              </li>
            )}
            {plan.exercises.map((e, i) => (
              <li key={e.exercise.id + i} className="rounded-lcars border border-edge bg-space/40 px-3 py-2 text-sm text-lcars-text">
                {e.exercise.name}{' '}
                <span className="text-lcars-muted">
                  ({e.sets}x{e.reps || '—'})
                </span>
              </li>
            ))}
            {plan.cooldown && (
              <li className="rounded-lcars border border-edge bg-space/40 px-3 py-2 text-sm text-lcars-text">
                <span className="text-[10px] uppercase tracking-widest text-lcars-muted">Cooldown · </span>
                {plan.cooldown.exercise.name}
              </li>
            )}
          </ul>
          {plan.exercises.length > 1 && (
            <button
              onClick={handleOverviewMakeShorter}
              className="mt-3 w-full rounded-lcars border border-edge px-3 py-2 text-xs font-semibold uppercase tracking-wider text-lcars-muted hover:border-medical/60"
            >
              Make Session Shorter
            </button>
          )}
        </LCARSPanel>

        <button
          onClick={beginWorkout}
          className="w-full rounded-lcars bg-medical px-4 py-4 font-lcars text-base font-bold uppercase tracking-[0.2em] text-white hover:opacity-80"
        >
          Begin Workout
        </button>
        <Link href="/physical-readiness" className="text-center text-xs text-lcars-muted underline">
          Not now — back to Physical Readiness
        </Link>
      </div>
    );
  }

  // phase === 'exercise'
  if (!currentStep) return null;
  const ex = currentStep.plan.exercise;
  const isTimed = TIMED_PATTERNS.has(ex.movement_pattern);
  const videoUrl = ex.preferred_video_url || youtubeSearchUrl(ex.video_search_query);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted">
          Step {stepIndex + 1} of {steps.length}
        </span>
        <button onClick={handleStopSession} className="text-xs font-semibold uppercase tracking-wider text-operations-on">
          Stop Session
        </button>
      </div>

      <LCARSPanel title={ex.name} accent="medical" eyebrow={ex.equipment}>
        <p className="mb-2 font-lcars text-2xl font-bold text-lcars-text">{currentStep.plan.beginnerTarget}</p>
        <p className="text-xs text-lcars-muted leading-relaxed">{currentStep.plan.why}</p>
        {currentStep.plan.painCaution && (
          <p className="mt-2 rounded-lcars border border-operations/30 bg-operations/10 px-3 py-2 text-xs text-operations-on">
            {currentStep.plan.painCaution}
          </p>
        )}
      </LCARSPanel>

      <LCARSPanel title="How to do it" accent="medical">
        <div className="flex flex-col gap-2 text-xs">
          <p><span className="text-lcars-muted uppercase tracking-wider">Setup: </span>{currentStep.plan.setupCues.join(' ')}</p>
          <p><span className="text-lcars-muted uppercase tracking-wider">Form: </span>{currentStep.plan.formCues.join(' · ')}</p>
          <p><span className="text-lcars-muted uppercase tracking-wider">Avoid: </span>{currentStep.plan.commonMistakes.join(' · ')}</p>
        </div>
        <a
          href={videoUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 inline-block rounded-lcars border border-edge px-3 py-2 text-xs font-semibold uppercase tracking-wider text-lcars-muted hover:border-medical/60"
        >
          Find Guide Video ↗
        </a>
      </LCARSPanel>

      <LCARSPanel title="Log This One" accent="medical">
        {!isTimed && (
          <div className="grid grid-cols-3 gap-2 mb-3">
            <div className="flex flex-col gap-1">
              <label className="text-[10px] uppercase tracking-widest text-lcars-muted">Sets</label>
              <input
                type="number" min={0} value={setsCompleted} onChange={(e) => setSetsCompleted(e.target.value)}
                className="rounded-lcars border border-edge bg-space px-2 py-2 text-sm text-lcars-text focus:border-medical focus:outline-none"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] uppercase tracking-widest text-lcars-muted">Reps</label>
              <input
                type="number" min={0} value={repsCompleted} onChange={(e) => setRepsCompleted(e.target.value)}
                className="rounded-lcars border border-edge bg-space px-2 py-2 text-sm text-lcars-text focus:border-medical focus:outline-none"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] uppercase tracking-widest text-lcars-muted">Weight</label>
              <input
                type="text" value={weightUsed} onChange={(e) => setWeightUsed(e.target.value)} placeholder="e.g. 15kg"
                className="rounded-lcars border border-edge bg-space px-2 py-2 text-sm text-lcars-text focus:border-medical focus:outline-none"
              />
            </div>
          </div>
        )}
        <div className="flex flex-col gap-3">
          <div>
            <div className="flex items-center justify-between">
              <label className="text-[10px] uppercase tracking-widest text-lcars-muted">Effort</label>
              <span className="font-lcars text-sm font-bold">{effortScore}/10</span>
            </div>
            <input type="range" min={1} max={10} value={effortScore} onChange={(e) => setEffortScore(Number(e.target.value))} className="w-full accent-medical" />
          </div>
          <div>
            <div className="flex items-center justify-between">
              <label className="text-[10px] uppercase tracking-widest text-lcars-muted">Pain during</label>
              <span className="font-lcars text-sm font-bold">{painDuring}/10</span>
            </div>
            <input type="range" min={0} max={10} value={painDuring} onChange={(e) => setPainDuring(Number(e.target.value))} className="w-full accent-medical" />
          </div>
        </div>
      </LCARSPanel>

      <div className="grid grid-cols-2 gap-2">
        <button onClick={handleSwap} className="rounded-lcars border border-edge px-3 py-3 text-xs font-semibold uppercase tracking-wider text-lcars-muted hover:border-medical/60">
          Swap Exercise
        </button>
        <button onClick={handleMakeEasier} className="rounded-lcars border border-edge px-3 py-3 text-xs font-semibold uppercase tracking-wider text-lcars-muted hover:border-medical/60">
          Make Easier
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <button onClick={handleSkip} className="rounded-lcars border border-operations/40 bg-operations/10 px-3 py-4 font-lcars text-sm font-bold uppercase tracking-wider text-operations-on">
          Skip
        </button>
        <button onClick={handleDone} className="rounded-lcars bg-medical px-3 py-4 font-lcars text-sm font-bold uppercase tracking-wider text-white hover:opacity-80">
          Done
        </button>
      </div>
    </div>
  );
}
