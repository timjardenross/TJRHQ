'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

type ActivityType = 'walk' | 'swim' | 'physio' | 'stretch' | 'strength' | 'cycle' | 'yoga' | 'other';
type Intensity    = 'light' | 'moderate' | 'vigorous';

const ACTIVITY_OPTIONS: { value: ActivityType; label: string; icon: string }[] = [
  { value: 'walk',     label: 'Walk',          icon: '🚶' },
  { value: 'swim',     label: 'Swim',          icon: '🏊' },
  { value: 'physio',   label: 'Physio',        icon: '🩺' },
  { value: 'stretch',  label: 'Stretch',       icon: '🧘' },
  { value: 'strength', label: 'Strength',      icon: '💪' },
  { value: 'cycle',    label: 'Cycle',         icon: '🚴' },
  { value: 'yoga',     label: 'Yoga',          icon: '🧘' },
  { value: 'other',    label: 'Other',         icon: '⚡' },
];

const INTENSITY_OPTIONS: { value: Intensity; label: string; note: string }[] = [
  { value: 'light',    label: 'Light',    note: 'Easy, minimal effort' },
  { value: 'moderate', label: 'Moderate', note: 'Comfortable challenge' },
  { value: 'vigorous', label: 'Vigorous', note: 'High effort, elevated HR' },
];

export default function LogActivityPage() {
  const router = useRouter();
  const today  = new Date().toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long' });

  const [activityType, setActivityType] = useState<ActivityType | null>(null);
  const [intensity,    setIntensity]    = useState<Intensity | null>(null);
  const [duration,     setDuration]     = useState('');
  const [notes,        setNotes]        = useState('');
  const [saving,       setSaving]       = useState(false);
  const [saved,        setSaved]        = useState(false);
  const [error,        setError]        = useState<string | null>(null);

  async function handleSubmit() {
    if (!activityType) {
      setError('Select an activity type.');
      return;
    }
    setError(null);
    setSaving(true);

    const payload: Record<string, unknown> = {
      log_date:      new Date().toISOString().slice(0, 10),
      activity_type: activityType,
      source:        'manual',
      completed:     true,
    };
    if (intensity) payload.intensity          = intensity;
    if (duration)  payload.duration_minutes   = parseInt(duration, 10);
    if (notes)     payload.notes              = notes;

    try {
      const supabase = createSupabaseBrowserClient();
      const { error: dbErr } = await supabase.from('activity_logs').insert(payload);
      if (dbErr) throw new Error(dbErr.message);
      setSaved(true);
      setTimeout(() => router.push('/medical'), 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save activity.');
    } finally {
      setSaving(false);
    }
  }

  if (saved) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-16">
        <div className="flex h-14 w-14 items-center justify-center rounded-full border border-status bg-status/10">
          <span className="font-lcars text-2xl text-status-on">✓</span>
        </div>
        <p className="font-lcars text-lg font-bold text-status-on">Activity logged</p>
        <p className="text-sm text-lcars-muted">Returning to Medical Bay…</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel title="Log Activity" accent="medical" eyebrow={today}>
        <p className="text-xs text-lcars-muted leading-relaxed">
          Movement is medicine. Log any activity — physio counts. Context for the Wellness Officer,
          not a performance target.
        </p>
      </LCARSPanel>

      {/* Activity type */}
      <LCARSPanel title="Activity Type" accent="medical" eyebrow="Required">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {ACTIVITY_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setActivityType(opt.value)}
              className={`rounded-lcars border p-3 text-left transition-colors ${
                activityType === opt.value
                  ? 'border-status bg-status/10 text-status-on'
                  : 'border-edge bg-space/40 text-lcars-muted hover:border-status/40'
              }`}
            >
              <span className="block text-lg mb-1">{opt.icon}</span>
              <span className="text-xs font-semibold">{opt.label}</span>
            </button>
          ))}
        </div>
      </LCARSPanel>

      {/* Intensity */}
      <LCARSPanel title="Intensity" accent="medical" eyebrow="Optional">
        <div className="flex flex-col gap-2">
          {INTENSITY_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setIntensity(intensity === opt.value ? null : opt.value)}
              className={`rounded-lcars border px-4 py-3 text-left transition-colors ${
                intensity === opt.value
                  ? 'border-command bg-command/10 text-command-on'
                  : 'border-edge bg-space/40 hover:border-command/40'
              }`}
            >
              <span className={`text-xs font-bold uppercase tracking-wider ${intensity === opt.value ? 'text-command-on' : 'text-lcars-muted'}`}>
                {opt.label}
              </span>
              <span className="ml-3 text-xs text-lcars-muted/80">{opt.note}</span>
            </button>
          ))}
        </div>
      </LCARSPanel>

      {/* Duration */}
      <LCARSPanel title="Duration" accent="medical" eyebrow="Optional">
        <div className="flex items-center gap-3">
          <input
            type="number"
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
            min={1}
            max={600}
            placeholder="e.g. 30"
            className="w-32 rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-command focus:outline-none"
          />
          <span className="text-sm text-lcars-muted">minutes</span>
        </div>
      </LCARSPanel>

      {/* Notes */}
      <LCARSPanel title="Notes" accent="medical" eyebrow="Optional">
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          placeholder="How did it feel? Any post-activity signals?"
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
        disabled={saving || !activityType}
        className="w-full rounded-lcars bg-status px-4 py-3 font-lcars text-sm font-bold uppercase tracking-[0.2em] text-white transition-opacity hover:opacity-80 disabled:opacity-40"
      >
        {saving ? 'Logging activity…' : 'Log Activity'}
      </button>
    </div>
  );
}
