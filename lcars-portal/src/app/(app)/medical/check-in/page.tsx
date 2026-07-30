'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { LCARSPanel } from '@/components/LCARSPanel';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

type NSState = 'calm' | 'activated' | 'dysregulated';
type EnergyLevel = 'low' | 'moderate' | 'high';
type MoodLevel = 'low' | 'stable' | 'positive';
type SleepQuality = 'poor' | 'fair' | 'good';
type WorkloadConstraint = 'normal' | 'modified' | 'reduced' | 'unknown';

function SelectField<T extends string>({
  label, value, onChange, options, hint
}: {
  label: string;
  value: T | '';
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
  hint?: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted">{label}</label>
      {hint && <p className="text-[11px] text-lcars-muted/70 italic">{hint}</p>}
      <div className="flex flex-wrap gap-2">
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={`rounded-lcars border px-3 py-1.5 text-xs font-semibold transition-colors ${
              value === opt.value
                ? 'border-command bg-command/20 text-command-on'
                : 'border-edge bg-space/40 text-lcars-muted hover:border-command/50'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function NumberField({
  label, value, onChange, placeholder, min, max, step = 1
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted">{label}</label>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        min={min}
        max={max}
        step={step}
        className="w-full rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-command focus:outline-none"
      />
    </div>
  );
}

export default function HealthCheckInPage() {
  const router = useRouter();
  const today = new Date().toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long' });

  const [nsState, setNsState]           = useState<NSState | ''>('');
  const [energy, setEnergy]             = useState<EnergyLevel | ''>('');
  const [mood, setMood]                 = useState<MoodLevel | ''>('');
  const [sleepHours, setSleepHours]     = useState('');
  const [sleepQuality, setSleepQuality] = useState<SleepQuality | ''>('');
  const [cpapUsed, setCpapUsed]         = useState<'yes' | 'no' | ''>('');
  const [cpapHours, setCpapHours]       = useState('');
  const [bodySignals, setBodySignals]   = useState('');
  const [sittingTol, setSittingTol]     = useState('');
  const [workload, setWorkload]         = useState<WorkloadConstraint | ''>('');
  const [notes, setNotes]               = useState('');
  const [saving, setSaving]             = useState(false);
  const [saved, setSaved]               = useState(false);
  const [error, setError]               = useState<string | null>(null);

  async function handleSubmit() {
    if (!nsState || !energy || !mood || !sleepQuality) {
      setError('Please fill in nervous system, energy, mood, and sleep quality.');
      return;
    }
    setSaving(true);
    setError(null);

    const payload: Record<string, unknown> = {
      log_date:             new Date().toISOString().slice(0, 10),
      source:               'manual',
      nervous_system_state: nsState,
      energy,
      mood,
      sleep_quality:        sleepQuality,
      workload_constraint:  workload || 'unknown',
    };
    if (sleepHours)   payload.sleep_hours               = parseFloat(sleepHours);
    if (cpapUsed)     payload.cpap_used                 = cpapUsed === 'yes';
    if (cpapHours)    payload.cpap_hours                = parseFloat(cpapHours);
    if (bodySignals)  payload.pain_score                = Math.min(10, Math.max(0, parseInt(bodySignals, 10)));
    if (sittingTol)   payload.sitting_tolerance_minutes = parseInt(sittingTol, 10);
    if (notes)        payload.notes                     = notes;

    const supabase = createSupabaseBrowserClient();
    const { error: dbError } = await supabase
      .from('health_daily_logs')
      .upsert(payload, { onConflict: 'log_date' });

    setSaving(false);
    if (dbError) {
      setError(dbError.message);
    } else {
      setSaved(true);
      setTimeout(() => router.push('/medical'), 1500);
    }
  }

  if (saved) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-16">
        <div className="flex h-14 w-14 items-center justify-center rounded-full border border-status bg-status/10">
          <span className="font-lcars text-2xl text-status-on">✓</span>
        </div>
        <p className="font-lcars text-lg font-bold text-status-on">Check-in logged</p>
        <p className="text-sm text-lcars-muted">Returning to Medical Bay…</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel
        title="Daily Check-In"
        accent="medical"
        eyebrow={today}
      >
        <p className="text-xs text-lcars-muted">
          The Captain is not broken. Recovery is not repair.
          The nervous system is doing its job.{' '}
          <em>The conditions around it need to change, not the Captain.</em>
        </p>
      </LCARSPanel>

      <LCARSPanel title="Nervous System" accent="medical" eyebrow="Required">
        <SelectField
          label="How does your nervous system feel right now?"
          hint="No right or wrong answer. This is data, not a grade."
          value={nsState}
          onChange={setNsState}
          options={[
            { value: 'calm',         label: 'Calm — settled, present' },
            { value: 'activated',    label: 'Activated — alert, some urgency' },
            { value: 'dysregulated', label: 'Dysregulated — overwhelmed, high activation' },
          ]}
        />
      </LCARSPanel>

      <LCARSPanel title="Energy & Mood" accent="medical" eyebrow="Required">
        <div className="flex flex-col gap-4">
          <SelectField
            label="Energy level"
            value={energy}
            onChange={setEnergy}
            options={[
              { value: 'low',      label: 'Low' },
              { value: 'moderate', label: 'Moderate' },
              { value: 'high',     label: 'High' },
            ]}
          />
          <SelectField
            label="Mood"
            value={mood}
            onChange={setMood}
            options={[
              { value: 'low',      label: 'Low' },
              { value: 'stable',   label: 'Stable' },
              { value: 'positive', label: 'Positive' },
            ]}
          />
        </div>
      </LCARSPanel>

      <LCARSPanel title="Sleep" accent="medical" eyebrow="Required">
        <div className="flex flex-col gap-4">
          <SelectField
            label="Sleep quality"
            value={sleepQuality}
            onChange={setSleepQuality}
            options={[
              { value: 'poor', label: 'Poor' },
              { value: 'fair', label: 'Fair' },
              { value: 'good', label: 'Good' },
            ]}
          />
          <NumberField
            label="Sleep hours"
            value={sleepHours}
            onChange={setSleepHours}
            placeholder="e.g. 7.5"
            min={0} max={24} step={0.5}
          />
          <SelectField
            label="CPAP used?"
            value={cpapUsed}
            onChange={setCpapUsed}
            options={[
              { value: 'yes', label: 'Yes' },
              { value: 'no',  label: 'No' },
            ]}
          />
          {cpapUsed === 'yes' && (
            <NumberField
              label="CPAP hours"
              value={cpapHours}
              onChange={setCpapHours}
              placeholder="e.g. 6"
              min={0} max={24} step={0.5}
            />
          )}
        </div>
      </LCARSPanel>

      <LCARSPanel title="Capacity" accent="medical" eyebrow="Optional">
        <div className="flex flex-col gap-4">
          <NumberField
            label="Body signals (0 = none, 10 = severe)"
            value={bodySignals}
            onChange={setBodySignals}
            placeholder="0–10"
            min={0} max={10}
          />
          <NumberField
            label="Max sitting tolerance (minutes)"
            value={sittingTol}
            onChange={setSittingTol}
            placeholder="e.g. 45"
            min={0} max={600}
          />
          <SelectField
            label="Workload constraint today"
            value={workload}
            onChange={setWorkload}
            options={[
              { value: 'normal',   label: 'Normal' },
              { value: 'modified', label: 'Modified' },
              { value: 'reduced',  label: 'Reduced' },
              { value: 'unknown',  label: 'Unknown' },
            ]}
          />
        </div>
      </LCARSPanel>

      <LCARSPanel title="Notes" accent="medical" eyebrow="Optional">
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          placeholder="Anything else the Medical Officer should know today."
          className="w-full rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-command focus:outline-none resize-none"
        />
      </LCARSPanel>

      {error && (
        <p className="rounded-lcars border border-operations/40 bg-operations/10 px-4 py-3 text-sm text-operations-on">
          {error}
        </p>
      )}

      <button
        onClick={handleSubmit}
        disabled={saving}
        className="w-full rounded-lcars bg-medical px-4 py-3 font-lcars text-sm font-bold uppercase tracking-[0.2em] text-white transition-opacity hover:opacity-80 disabled:opacity-40"
      >
        {saving ? 'Logging check-in…' : 'Log Check-In'}
      </button>
    </div>
  );
}
