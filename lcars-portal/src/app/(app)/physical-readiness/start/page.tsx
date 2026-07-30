'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { LCARSPanel } from '@/components/LCARSPanel';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import {
  generateSession,
  type EnergyState,
  type ExerciseRow,
  type ReadinessInput,
  type SessionIntent,
  type TimeAvailableMinutes,
} from '@/lib/physical-readiness';

const ENERGY_OPTIONS: { value: EnergyState; label: string; hint: string; tone: string }[] = [
  { value: 'green', label: 'Green', hint: 'Good energy', tone: 'border-status bg-status/15 text-status-on' },
  { value: 'yellow', label: 'Yellow', hint: 'Manageable but tired', tone: 'border-command bg-command/15 text-command-on' },
  { value: 'orange', label: 'Orange', hint: 'Low energy / stressed / sore', tone: 'border-engineering bg-engineering/15 text-engineering-on' },
  { value: 'red', label: 'Red', hint: 'Not suitable for training', tone: 'border-operations bg-operations/15 text-operations-on' },
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
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <label className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted">{label}</label>
        <span className="font-lcars text-sm font-bold text-lcars-text">{value}/10</span>
      </div>
      <input
        type="range"
        min={0}
        max={10}
        step={1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-medical"
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

    router.push(`/physical-readiness/session/${session.id}`);
  }

  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel title="Today's Readiness" accent="medical" eyebrow="30 seconds, no wrong answers">
        <p className="text-xs text-lcars-muted">
          This decides today&apos;s session — not a grade, not a target to beat.
        </p>
      </LCARSPanel>

      <LCARSPanel title="Energy" accent="medical" eyebrow="Required">
        <div className="grid grid-cols-2 gap-2">
          {ENERGY_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setEnergyState(opt.value)}
              className={`flex flex-col items-start gap-0.5 rounded-lcars border px-3 py-2.5 text-left transition-colors ${
                energyState === opt.value ? opt.tone : 'border-edge bg-space/40 text-lcars-muted hover:border-lcars-muted'
              }`}
            >
              <span className="font-lcars text-sm font-bold uppercase tracking-wider">{opt.label}</span>
              <span className="text-[11px] opacity-80">{opt.hint}</span>
            </button>
          ))}
        </div>
      </LCARSPanel>

      {energyState === 'red' && (
        <p className="rounded-lcars border border-operations/40 bg-operations/10 px-4 py-3 text-sm text-operations-on">
          Red state noted. The next screen will only offer breathing, a gentle walk, light mobility,
          or permission to leave the gym — no normal workout will be generated.
        </p>
      )}

      <LCARSPanel title="Pain Areas" accent="medical" eyebrow="0 = none, 10 = severe">
        <div className="flex flex-col gap-4">
          {PAIN_FIELDS.map((f) => (
            <PainSlider key={f.key} label={f.label} value={painValues[f.key]} onChange={painSetters[f.key]} />
          ))}
        </div>
      </LCARSPanel>

      <LCARSPanel title="Time Available" accent="medical" eyebrow="Required">
        <div className="grid grid-cols-4 gap-2">
          {TIME_OPTIONS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTimeAvailableMinutes(t)}
              className={`rounded-lcars border py-3 text-center font-lcars text-base font-bold transition-colors ${
                timeAvailableMinutes === t
                  ? 'border-medical bg-medical/20 text-medical-on'
                  : 'border-edge bg-space/40 text-lcars-muted hover:border-medical/50'
              }`}
            >
              {t}m
            </button>
          ))}
        </div>
      </LCARSPanel>

      <LCARSPanel title="Session Intent" accent="medical" eyebrow="Required">
        <div className="flex flex-wrap gap-2">
          {INTENT_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setSessionIntent(opt.value)}
              className={`rounded-lcars border px-3 py-2 text-xs font-semibold transition-colors ${
                sessionIntent === opt.value
                  ? 'border-medical bg-medical/20 text-medical-on'
                  : 'border-edge bg-space/40 text-lcars-muted hover:border-medical/50'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </LCARSPanel>

      <LCARSPanel title="Notes" accent="medical" eyebrow="Optional">
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          placeholder="Anything else worth noting before training."
          className="w-full rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-medical focus:outline-none resize-none"
        />
      </LCARSPanel>

      {error && (
        <p className="rounded-lcars border border-operations/40 bg-operations/10 px-4 py-3 text-sm text-operations-on">
          {error}
        </p>
      )}

      <button
        onClick={handleSubmit}
        disabled={generating}
        className="w-full rounded-lcars bg-medical px-4 py-4 font-lcars text-base font-bold uppercase tracking-[0.2em] text-white transition-opacity hover:opacity-80 disabled:opacity-40"
      >
        {generating ? 'Building session…' : 'Generate Session'}
      </button>
    </div>
  );
}
