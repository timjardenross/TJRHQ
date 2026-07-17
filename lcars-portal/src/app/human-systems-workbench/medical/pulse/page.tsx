'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Shell } from '@/app/human-systems-workbench/_components/Shell';
import { Card, Badge, Button, Input, Textarea } from '@/components/ui';

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
  // Colour carries the day-progression identity of each pulse (morning→evening),
  // so a glance distinguishes them. `tone` = selected container, `accent` = the
  // time label colour. wb tokens only.
  tone: string;
  accent: string;
  fields: ('energy' | 'mood' | 'stress' | 'readiness' | 'pain' | 'notes')[];
}[] = [
  {
    type: 'morning',
    label: 'Morning Readiness',
    time: 'Morning',
    purpose: 'Mission planning · Daily posture determination',
    tone: 'border-wb-ok bg-wb-ok/15',
    accent: 'text-wb-ok-on',
    fields: ['energy', 'mood', 'readiness', 'pain', 'notes'],
  },
  {
    type: 'midday',
    label: 'Midday Status',
    time: 'Midday',
    purpose: 'Course correction · Workload protection',
    tone: 'border-wb-warn bg-wb-warn/15',
    accent: 'text-wb-warn-on',
    fields: ['stress', 'readiness', 'pain', 'notes'],
  },
  {
    type: 'end_of_day',
    label: 'End of Workday',
    time: 'End of day',
    purpose: 'Transition to recovery mode',
    tone: 'border-wb-crit bg-wb-crit/15',
    accent: 'text-wb-crit-on',
    fields: ['energy', 'stress', 'readiness', 'pain', 'notes'],
  },
  {
    type: 'evening',
    label: 'Evening Recovery',
    time: 'Evening',
    purpose: 'Recovery completion loop',
    tone: 'border-wb-sage-deep bg-wb-sage/15',
    accent: 'text-wb-sage-deep',
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
      <p className="text-[12px] font-medium text-wb-ink2">{label}</p>
      {hint && <p className="text-[11px] italic text-wb-ink2">{hint}</p>}
      <div className="flex flex-wrap gap-2">
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            aria-pressed={value === opt.value}
            className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
              value === opt.value
                ? 'bg-wb-sage-deep text-white'
                : 'border border-wb-line bg-wb-surface text-wb-ink2 hover:bg-wb-line'
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
          <Input
            type="number"
            label="Body signals (0 = none · 10 = severe)"
            hint="Context only — not a recovery metric."
            value={pain}
            onChange={(e) => setPain(e.target.value)}
            min={0} max={10} step={0.5}
            placeholder="0–10"
            className="w-32"
          />
        </div>
      )}
      {pulse.fields.includes('notes') && (
        <Textarea
          label={pulse.type === 'evening' ? 'Reflection notes' : 'Notes'}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          placeholder={
            pulse.type === 'evening'    ? 'Recovery activities completed. How did the day land?' :
            pulse.type === 'end_of_day' ? 'Progress made. What needs to carry over tomorrow?' :
            pulse.type === 'midday'     ? 'Anything shifting? Capacity concerns?' :
            'Anything the Medical Officer should know.'
          }
          className="resize-none"
        />
      )}

      {error && (
        <p className="rounded-md border border-wb-crit/40 bg-wb-crit/10 px-4 py-3 text-sm text-wb-crit-on">
          {error}
        </p>
      )}

      <Button
        variant="primary"
        onClick={handleSubmit}
        disabled={saving}
        className="w-full py-3"
      >
        {saving ? 'Logging pulse…' : `Log ${pulse.label}`}
      </Button>
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
      const res = await fetch('/api/human-systems/pulse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      const resBody = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(resBody.error ?? 'Failed to save pulse.');
      setSavedLabel(activePulse?.label ?? 'Pulse');
      setSaved(true);
      setTimeout(() => router.push('/human-systems-workbench?domain=medical'), 1800);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save pulse.');
    } finally {
      setSaving(false);
    }
  }

  if (saved) {
    return (
      <Shell title="Recovery Pulse" eyebrow="Health Tracking" back={{ href: '/human-systems-workbench?domain=medical', label: 'Medical' }}>
        <div className="flex flex-col items-center justify-center gap-4 py-16">
          <div className="flex h-14 w-14 items-center justify-center rounded-full border border-wb-ok bg-wb-ok/10">
            <span aria-hidden className="text-2xl text-wb-ok-on">✓</span>
          </div>
          <p className="font-serif text-lg font-bold text-wb-ok-on">{savedLabel} logged</p>
          <p className="text-sm text-wb-ink2">Returning to Medical…</p>
        </div>
      </Shell>
    );
  }

  return (
    <Shell title="Recovery Pulse" eyebrow="Health Tracking" back={{ href: '/human-systems-workbench?domain=medical', label: 'Medical' }}>
      <div className="flex flex-col gap-4">
        <Card title={`D-055 · ${now.toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long' })}`}>
          <p className="text-xs leading-relaxed text-wb-ink2">
            Four pulses per day build a complete picture of recovery state.
            Each pulse takes under 60 seconds. Missing pulses reduce readiness confidence — not recovery itself.
          </p>
        </Card>

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
                aria-pressed={isSelected}
                className={`rounded-lg p-4 text-left transition-all ${
                  isSelected
                    ? `border-2 ${p.tone}`
                    : 'border border-wb-line bg-wb-surface hover:bg-wb-line'
                }`}
              >
                <div className="mb-1 flex items-start justify-between gap-2">
                  <p className={`text-xs font-bold uppercase tracking-wider ${isSelected ? p.accent : 'text-wb-ink2'}`}>
                    {p.time}
                  </p>
                  {isSuggested && <Badge status="info">Now</Badge>}
                </div>
                <p className="text-sm font-semibold text-wb-ink">{p.label}</p>
                <p className="mt-1 text-[10px] leading-snug text-wb-ink2">{p.purpose}</p>
              </button>
            );
          })}
        </div>

        {/* Pulse form */}
        {activePulse && (
          <Card title={activePulse.label}>
            <div className="mb-3 flex items-center justify-between gap-2">
              <p className="text-[11px] uppercase tracking-[0.12em] text-wb-ink2">{activePulse.purpose}</p>
              <Badge status="info">{activePulse.time}</Badge>
            </div>
            {error && (
              <p className="mb-4 rounded-md border border-wb-crit/40 bg-wb-crit/10 px-4 py-3 text-sm text-wb-crit-on">
                {error}
              </p>
            )}
            <PulseForm pulse={activePulse} onSubmit={handleSubmit} saving={saving} />
          </Card>
        )}
      </div>
    </Shell>
  );
}
