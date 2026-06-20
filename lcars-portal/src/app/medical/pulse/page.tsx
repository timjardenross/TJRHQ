'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

// ── Types ─────────────────────────────────────────────────────────────────────

type PulseType = 'morning' | 'midday' | 'end_of_day' | 'evening';
type EnergyLevel = 'low' | 'moderate' | 'high';
type MoodLevel = 'low' | 'stable' | 'positive';
type StressLevel = 'low' | 'moderate' | 'high';
type ReadinessLevel = 'low' | 'moderate' | 'high';

// ── Pulse config ──────────────────────────────────────────────────────────────

const PULSES: {
  type: PulseType;
  label: string;
  time: string;
  purpose: string;
  tone: string;
  fields: ('energy' | 'mood' | 'stress' | 'readiness' | 'pain' | 'notes')[];
}[] = [
  {
    type: 'morning',
    label: 'Morning Readiness',
    time: 'Morning',
    purpose: 'Mission planning · Daily posture determination',
    tone: 'border-status/40 bg-status/5 text-status',
    fields: ['energy', 'mood', 'readiness', 'pain', 'notes'],
  },
  {
    type: 'midday',
    label: 'Midday Status',
    time: 'Midday',
    purpose: 'Course correction · Workload protection',
    tone: 'border-command/40 bg-command/5 text-command',
    fields: ['stress', 'readiness', 'pain', 'notes'],
  },
  {
    type: 'end_of_day',
    label: 'End of Workday',
    time: 'End of day',
    purpose: 'Transition to recovery mode',
    tone: 'border-operations/40 bg-operations/5 text-operations',
    fields: ['energy', 'stress', 'readiness', 'pain', 'notes'],
  },
  {
    type: 'evening',
    label: 'Evening Recovery',
    time: 'Evening',
    purpose: 'Recovery completion loop',
    tone: 'border-medical/40 bg-medical/5 text-medical',
    fields: ['mood', 'stress', 'readiness', 'notes'],
  },
];

// ── Shared field components ───────────────────────────────────────────────────

function SegmentField<T extends string>({
  label, value, onChange, options, hint
}: {
  label: string;
  value: T | '';
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
  hint?: string;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted">{label}</p>
      {hint && <p className="text-[11px] text-lcars-muted/70 italic">{hint}</p>}
      <div className="flex flex-wrap gap-2">
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={`rounded-lcars border px-3 py-1.5 text-xs font-semibold transition-colors ${
              value === opt.value
                ? 'border-medical bg-medical/20 text-medical'
                : 'border-edge bg-space/40 text-lcars-muted hover:border-medical/40'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Pulse form ────────────────────────────────────────────────────────────────

function PulseForm({
  pulse,
  onSubmit,
  saving,
}: {
  pulse: typeof PULSES[number];
  onSubmit: (data: Record<string, unknown>) => void;
  saving: boolean;
}) {
  const [energy,    setEnergy]    = useState<EnergyLevel | ''>('');
  const [mood,      setMood]      = useState<MoodLevel | ''>('');
  const [stress,    setStress]    = useState<StressLevel | ''>('');
  const [readiness, setReadiness] = useState<ReadinessLevel | ''>('');
  const [pain,      setPain]      = useState('');
  const [notes,     setNotes]     = useState('');
  const [error,     setError]     = useState<string | null>(null);

  function handleSubmit() {
    // At least one telemetry field required
    if (!energy && !mood && !stress && !readiness && !pain) {
      setError('Please fill in at least one field.');
      return;
    }
    setError(null);
    const data: Record<string, unknown> = {
      log_date:   new Date().toISOString().slice(0, 10),
      pulse_type: pulse.type,
      source:     'manual',
    };
    if (energy)    data.energy     = energy;
    if (mood)      data.mood       = mood;
    if (stress)    data.stress     = stress;
    if (readiness) data.readiness  = readiness;
    if (pain)      data.pain_score = parseFloat(pain);
    if (notes)     data.notes      = notes;
    onSubmit(data);
  }

  return (
    <div className="flex flex-col gap-4">
      {pulse.fields.includes('energy') && (
        <SegmentField
          label="Energy"
          value={energy}
          onChange={setEnergy}
          options={[
            { value: 'low',      label: 'Low' },
            { value: 'moderate', label: 'Moderate' },
            { value: 'high',     label: 'High' },
          ]}
        />
      )}
      {pulse.fields.includes('mood') && (
        <SegmentField
          label={pulse.type === 'evening' ? 'Nervous system / mood' : 'Mood'}
          value={mood}
          onChange={setMood}
          options={[
            { value: 'low',      label: 'Low' },
            { value: 'stable',   label: 'Stable' },
            { value: 'positive', label: 'Positive' },
          ]}
        />
      )}
      {pulse.fields.includes('stress') && (
        <SegmentField
          label={pulse.type === 'midday' ? 'Stress level' : pulse.type === 'end_of_day' ? 'Recovery debt / fatigue' : 'Stress'}
          value={stress}
          onChange={setStress}
          options={[
            { value: 'low',      label: 'Low' },
            { value: 'moderate', label: 'Moderate' },
            { value: 'high',     label: 'High' },
          ]}
        />
      )}
      {pulse.fields.includes('readiness') && (
        <SegmentField
          label={
            pulse.type === 'midday'      ? 'Remaining capacity' :
            pulse.type === 'end_of_day'  ? 'Current posture' :
            pulse.type === 'evening'     ? 'Recovery readiness for tomorrow' :
            'Readiness'
          }
          value={readiness}
          onChange={setReadiness}
          options={[
            { value: 'low',      label: 'Low' },
            { value: 'moderate', label: 'Moderate' },
            { value: 'high',     label: 'High' },
          ]}
        />
      )}
      {pulse.fields.includes('pain') && (
        <div className="flex flex-col gap-1.5">
          <p className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted">
            Body signals (0 = none · 10 = severe)
          </p>
          <p className="text-[11px] text-lcars-muted/70 italic">Context only — not a recovery metric.</p>
          <input
            type="number"
            value={pain}
            onChange={(e) => setPain(e.target.value)}
            min={0} max={10} step={0.5}
            placeholder="0–10"
            className="w-32 rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-medical focus:outline-none"
          />
        </div>
      )}
      {pulse.fields.includes('notes') && (
        <div className="flex flex-col gap-1.5">
          <p className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted">
            {pulse.type === 'evening' ? 'Reflection notes' : 'Notes'}
          </p>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            placeholder={
              pulse.type === 'evening'    ? 'Recovery activities completed. How did the day land?' :
              pulse.type === 'end_of_day' ? 'Progress made. What needs to carry over tomorrow?' :
              pulse.type === 'midday'     ? 'Anything shifting? Capacity concerns?' :
              'Anything the Medical Officer should know.'
            }
            className="w-full rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-medical focus:outline-none resize-none"
          />
        </div>
      )}

      {error && (
        <p className="rounded-lcars border border-operations/40 bg-operations/10 px-4 py-3 text-sm text-operations">
          {error}
        </p>
      )}

      <button
        onClick={handleSubmit}
        disabled={saving}
        className="w-full rounded-lcars bg-medical px-4 py-3 font-lcars text-sm font-bold uppercase tracking-[0.2em] text-space transition-opacity hover:opacity-80 disabled:opacity-40"
      >
        {saving ? 'Logging pulse…' : `Log ${pulse.label}`}
      </button>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function RecoveryPulsePage() {
  const router = useRouter();
  const [selectedPulse, setSelectedPulse] = useState<PulseType | null>(null);
  const [saving,  setSaving]  = useState(false);
  const [saved,   setSaved]   = useState(false);
  const [savedLabel, setSavedLabel] = useState('');
  const [error,   setError]   = useState<string | null>(null);

  const now = new Date();
  const hour = now.getHours();
  const suggestedPulse: PulseType =
    hour < 11 ? 'morning' :
    hour < 14 ? 'midday' :
    hour < 18 ? 'end_of_day' : 'evening';

  const activePulse = PULSES.find(p => p.type === (selectedPulse ?? suggestedPulse));

  async function handleSubmit(data: Record<string, unknown>) {
    setSaving(true);
    setError(null);
    try {
      const supabase = createSupabaseBrowserClient();
      const { error: dbError } = await supabase
        .from('recovery_pulses')
        .upsert(data, { onConflict: 'log_date,pulse_type' });
      if (dbError) throw new Error(dbError.message);
      setSavedLabel(activePulse?.label ?? 'Pulse');
      setSaved(true);
      setTimeout(() => router.push('/medical'), 1800);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save pulse.');
    } finally {
      setSaving(false);
    }
  }

  if (saved) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-16">
        <div className="flex h-14 w-14 items-center justify-center rounded-full border border-medical bg-medical/10">
          <span className="font-lcars text-2xl text-medical">✓</span>
        </div>
        <p className="font-lcars text-lg font-bold text-medical">{savedLabel} logged</p>
        <p className="text-sm text-lcars-muted">Returning to Medical Bay…</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel
        title="Recovery Pulse"
        accent="medical"
        eyebrow={`D-055 · ${now.toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long' })}`}
      >
        <p className="text-xs text-lcars-muted leading-relaxed">
          Four pulses per day build a complete picture of recovery state.
          Each pulse takes under 60 seconds. Missing pulses reduce readiness confidence — not recovery itself.
        </p>
      </LCARSPanel>

      {/* Pulse selector */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {PULSES.map((p) => {
          const isSelected = (selectedPulse ?? suggestedPulse) === p.type;
          const isSuggested = suggestedPulse === p.type && !selectedPulse;
          return (
            <button
              key={p.type}
              type="button"
              onClick={() => setSelectedPulse(p.type)}
              className={`rounded-lcars border p-4 text-left transition-all ${
                isSelected
                  ? `${p.tone} border-2`
                  : 'border-edge bg-space/40 hover:border-edge/80'
              }`}
            >
              <div className="flex items-start justify-between gap-2 mb-1">
                <p className={`font-lcars text-xs font-bold uppercase tracking-wider ${isSelected ? p.tone.split(' ')[2] : 'text-lcars-muted'}`}>
                  {p.time}
                </p>
                {isSuggested && <StatusBadge label="Now" tone="medical" />}
              </div>
              <p className="text-sm font-semibold text-lcars-text">{p.label}</p>
              <p className="text-[10px] text-lcars-muted mt-1 leading-snug">{p.purpose}</p>
            </button>
          );
        })}
      </div>

      {/* Pulse form */}
      {activePulse && (
        <LCARSPanel
          title={activePulse.label}
          accent="medical"
          eyebrow={activePulse.purpose}
          actions={<StatusBadge label={activePulse.time} tone="medical" />}
        >
          {error && (
            <p className="mb-4 rounded-lcars border border-operations/40 bg-operations/10 px-4 py-3 text-sm text-operations">
              {error}
            </p>
          )}
          <PulseForm pulse={activePulse} onSubmit={handleSubmit} saving={saving} />
        </LCARSPanel>
      )}
    </div>
  );
}
