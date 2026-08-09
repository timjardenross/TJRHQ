'use client';

import { useId, useState } from 'react';
import { useRouter } from 'next/navigation';
import { WorkbenchShell, Card, Button, Textarea } from '@/components/ui';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import {
  generateSession,
  type EnergyState,
  type ExerciseRow,
  type ReadinessInput,
  type SessionIntent,
  type TimeAvailableMinutes,
} from '@/lib/physical-readiness';

// Energy is a good→bad state scale, so its colour carries meaning (not
// decoration): green=ok, yellow/orange=warn (orange deeper), red=crit. Selection
// affordance = the semantic tone; unselected stays neutral. wb tokens only.
const ENERGY_OPTIONS: { value: EnergyState; label: string; hint: string; tone: string }[] = [
  { value: 'green', label: 'Green', hint: 'Good energy', tone: 'border-wb-ok bg-wb-ok/15 text-wb-ok-on' },
  { value: 'yellow', label: 'Yellow', hint: 'Manageable but tired', tone: 'border-wb-warn bg-wb-warn/15 text-wb-warn-on' },
  { value: 'orange', label: 'Orange', hint: 'Low energy / stressed / sore', tone: 'border-wb-warn bg-wb-warn/30 text-wb-warn-on' },
  { value: 'red', label: 'Red', hint: 'Not suitable for training', tone: 'border-wb-crit bg-wb-crit/15 text-wb-crit-on' },
];

const TIME_OPTIONS: TimeAvailableMinutes[] = [15, 25, 35, 45];

const INTENT_OPTIONS: { value: SessionIntent; label: string }[] = [
  { value: 'move_gently', label: 'Move gently' },
  { value: 'build_strength', label: 'Build strength' },
  { value: 'reduce_stress', label: 'Reduce stress' },
  { value: 'improve_energy', label: 'Improve energy' },
  { value: 'maintain_habit', label: 'Maintain habit' },
];

const PAIN_FIELDS: { key: 'backPain' | 'kneePain' | 'anklePain' | 'neckShoulderPain' | 'generalPain'; label: string }[] = [
  { key: 'backPain', label: 'Back pain' },
  { key: 'kneePain', label: 'Left knee pain' },
  { key: 'anklePain', label: 'Left ankle pain' },
  { key: 'neckShoulderPain', label: 'Neck / shoulder pain' },
  { key: 'generalPain', label: 'General pain' },
];

function PainSlider({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <label htmlFor={id} className="text-[10px] uppercase tracking-[0.25em] text-wb-ink2">{label}</label>
        <span className="font-serif text-sm font-bold text-wb-ink">{value}/10</span>
      </div>
      <input
        id={id}
        type="range"
        min={0}
        max={10}
        step={1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-wb-sage-deep"
      />
    </div>
  );
}

export default function ReadinessCheckInPage() {
  const router = useRouter();

  const [energyState, setEnergyState] = useState<EnergyState | ''>('');
  const [backPain, setBackPain] = useState(0);
  const [kneePain, setKneePain] = useState(0);
  const [anklePain, setAnklePain] = useState(0);
  const [neckShoulderPain, setNeckShoulderPain] = useState(0);
  const [generalPain, setGeneralPain] = useState(0);
  const [timeAvailableMinutes, setTimeAvailableMinutes] = useState<TimeAvailableMinutes | ''>('');
  const [sessionIntent, setSessionIntent] = useState<SessionIntent | ''>('');
  const [notes, setNotes] = useState('');
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const painValues: Record<string, number> = { backPain, kneePain, anklePain, neckShoulderPain, generalPain };
  const painSetters: Record<string, (v: number) => void> = {
    backPain: setBackPain, kneePain: setKneePain, anklePain: setAnklePain,
    neckShoulderPain: setNeckShoulderPain, generalPain: setGeneralPain,
  };

  async function handleSubmit() {
    if (!energyState || !timeAvailableMinutes || !sessionIntent) {
      setError('Pick your energy, time available, and session intent.');
      return;
    }
    setGenerating(true);
    setError(null);

    const supabase = createSupabaseBrowserClient();
    const input: ReadinessInput = {
      energyState,
      backPain, kneePain, anklePain, neckShoulderPain, generalPain,
      timeAvailableMinutes,
      sessionIntent,
      notes: notes || undefined,
    };

    const { data: checkin, error: checkinError } = await supabase
      .from('physical_readiness_checkins')
      .insert({
        energy_state: energyState,
        back_pain: backPain,
        knee_pain: kneePain,
        ankle_pain: anklePain,
        neck_shoulder_pain: neckShoulderPain,
        general_pain: generalPain,
        time_available_minutes: timeAvailableMinutes,
        session_intent: sessionIntent,
        notes: notes || null,
      })
      .select('id')
      .single();

    if (checkinError || !checkin) {
      setGenerating(false);
      setError(checkinError?.message ?? 'Could not save check-in.');
      return;
    }

    const { data: exercises, error: exercisesError } = await supabase
      .from('physical_exercises')
      .select('*')
      .in('status', ['active', 'needs_review']);

    if (exercisesError || !exercises) {
      setGenerating(false);
      setError(exercisesError?.message ?? 'Could not load exercise library.');
      return;
    }

    const plan = generateSession(input, exercises as ExerciseRow[]);

    const { data: session, error: sessionError } = await supabase
      .from('physical_workout_sessions')
      .insert({
        readiness_checkin_id: checkin.id,
        session_type: plan.sessionType,
        generated_plan_json: plan,
        status: 'in_progress',
      })
      .select('id')
      .single();

    setGenerating(false);
    if (sessionError || !session) {
      setError(sessionError?.message ?? 'Could not create workout session.');
      return;
    }

    router.push(`/human-systems-workbench/readiness/session/${session.id}`);
  }

  return (
    <WorkbenchShell
      title="Today's Readiness"
      eyebrow="Fitness Readiness"
      tagline="USS TJR · Human Systems · Recovery · Medical · Readiness · Evidence-informed, non-diagnostic"
      back={{ href: '/human-systems-workbench?domain=readiness', label: 'Readiness' }}
    >
      <div className="flex flex-col gap-4">
        <Card>
          <p className="text-[13px] leading-relaxed text-wb-ink2">
            30 seconds, no wrong answers. This decides today&apos;s session — not a grade, not a target to beat.
          </p>
        </Card>

        <Card title="Energy">
          <p className="mb-3 text-[11px] uppercase tracking-[0.12em] text-wb-ink2">Required</p>
          <div className="grid grid-cols-2 gap-2">
            {ENERGY_OPTIONS.map((opt) => {
              const selected = energyState === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => setEnergyState(opt.value)}
                  className={`flex flex-col items-start gap-0.5 rounded-md px-3 py-2.5 text-left transition-colors ${
                    selected
                      ? `border-2 ${opt.tone}`
                      : 'border border-wb-line bg-wb-surface text-wb-ink2 hover:bg-wb-line'
                  }`}
                >
                  <span className="text-sm font-bold uppercase tracking-wider">{opt.label}</span>
                  <span className="text-[11px] opacity-80">{opt.hint}</span>
                </button>
              );
            })}
          </div>
        </Card>

        {energyState === 'red' && (
          <div className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 px-4 py-3 text-[13px] text-wb-crit-on">
            Red state noted. The next screen will only offer breathing, a gentle walk, light mobility,
            or permission to leave the gym — no normal workout will be generated.
          </div>
        )}

        <Card title="Pain Areas">
          <p className="mb-3 text-[11px] uppercase tracking-[0.12em] text-wb-ink2">0 = none, 10 = severe</p>
          <div className="flex flex-col gap-4">
            {PAIN_FIELDS.map((f) => (
              <PainSlider key={f.key} label={f.label} value={painValues[f.key]} onChange={painSetters[f.key]} />
            ))}
          </div>
        </Card>

        <Card title="Time Available">
          <p className="mb-3 text-[11px] uppercase tracking-[0.12em] text-wb-ink2">Required</p>
          <div className="grid grid-cols-4 gap-2">
            {TIME_OPTIONS.map((t) => {
              const selected = timeAvailableMinutes === t;
              return (
                <button
                  key={t}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => setTimeAvailableMinutes(t)}
                  className={`rounded-md border py-3 text-center text-base font-bold transition-colors ${
                    selected
                      ? 'bg-wb-sage-deep text-white'
                      : 'border border-wb-line bg-wb-surface text-wb-ink2 hover:bg-wb-line'
                  }`}
                >
                  {t}m
                </button>
              );
            })}
          </div>
        </Card>

        <Card title="Session Intent">
          <p className="mb-3 text-[11px] uppercase tracking-[0.12em] text-wb-ink2">Required</p>
          <div className="flex flex-wrap gap-2">
            {INTENT_OPTIONS.map((opt) => {
              const selected = sessionIntent === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => setSessionIntent(opt.value)}
                  className={`rounded-md border px-3 py-2 text-xs font-semibold transition-colors ${
                    selected
                      ? 'bg-wb-sage-deep text-white'
                      : 'border border-wb-line bg-wb-surface text-wb-ink2 hover:bg-wb-line'
                  }`}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        </Card>

        <Card title="Notes">
          <p className="mb-3 text-[11px] uppercase tracking-[0.12em] text-wb-ink2">Optional</p>
          <Textarea
            aria-label="Notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            placeholder="Anything else worth noting before training."
            className="resize-none"
          />
        </Card>

        {error && (
          <div className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 px-4 py-3 text-[13px] text-wb-crit-on">
            {error}
          </div>
        )}

        <Button
          variant="primary"
          onClick={handleSubmit}
          disabled={generating}
          className="w-full py-4 text-base font-bold uppercase tracking-[0.2em]"
        >
          {generating ? 'Building session…' : 'Generate Session'}
        </Button>
      </div>
    </WorkbenchShell>
  );
}
