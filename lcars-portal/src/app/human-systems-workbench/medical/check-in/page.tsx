'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { WorkbenchShell, Card, Button, Input, Textarea } from '@/components/ui';

type NSState = 'calm' | 'activated' | 'dysregulated';
type EnergyLevel = 'low' | 'moderate' | 'high';
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
    <div className="flex flex-col gap-1.5">
      <div className="text-[12px] font-medium text-wb-ink2">{label}</div>
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
    <Input
      type="number"
      label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      min={min}
      max={max}
      step={step}
    />
  );
}

export default function HealthCheckInPage() {
  const router = useRouter();
  const today = new Date().toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long' });

  const [nsState, setNsState]           = useState<NSState | ''>('');
  const [energy, setEnergy]             = useState<EnergyLevel | ''>('');
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
    if (!nsState || !energy || !sleepQuality) {
      setError('Please fill in nervous system, energy, and sleep quality.');
      return;
    }
    setSaving(true);
    setError(null);

    const payload: Record<string, unknown> = {
      log_date:             new Date().toISOString().slice(0, 10),
      source:               'manual',
      nervous_system_state: nsState,
      energy,
      sleep_quality:        sleepQuality,
      workload_constraint:  workload || 'unknown',
    };
    if (sleepHours)   payload.sleep_hours               = parseFloat(sleepHours);
    if (cpapUsed)     payload.cpap_used                 = cpapUsed === 'yes';
    if (cpapHours)    payload.cpap_hours                = parseFloat(cpapHours);
    if (bodySignals)  payload.pain_score                = Math.min(10, Math.max(0, parseInt(bodySignals, 10)));
    if (sittingTol)   payload.sitting_tolerance_minutes = parseInt(sittingTol, 10);
    if (notes)        payload.notes                     = notes;

    const res = await fetch('/api/human-systems/check-in', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const resBody = await res.json().catch(() => ({}));

    setSaving(false);
    if (!res.ok) {
      setError(resBody.error ?? 'Failed to save check-in.');
    } else {
      setSaved(true);
      setTimeout(() => router.push('/human-systems-workbench?domain=medical'), 1500);
    }
  }

  if (saved) {
    return (
      <WorkbenchShell title="Daily Check-In" eyebrow="Health Tracking" tagline="USS TJR · Human Systems · Recovery · Medical · Readiness · Evidence-informed, non-diagnostic" back={{ href: '/human-systems-workbench?domain=medical', label: 'Medical' }}>
        <div className="flex flex-col items-center justify-center gap-4 py-16">
          <div className="flex h-14 w-14 items-center justify-center rounded-full border border-wb-ok bg-wb-ok/10">
            <span aria-hidden className="text-2xl text-wb-ok-on">✓</span>
          </div>
          <p className="font-serif text-lg font-bold text-wb-ok-on">Check-in logged</p>
          <p className="text-sm text-wb-ink2">Returning to Medical…</p>
        </div>
      </WorkbenchShell>
    );
  }

  return (
    <WorkbenchShell title="Daily Check-In" eyebrow="Health Tracking" tagline="USS TJR · Human Systems · Recovery · Medical · Readiness · Evidence-informed, non-diagnostic" back={{ href: '/human-systems-workbench?domain=medical', label: 'Medical' }}>
      <div className="flex flex-col gap-4">
        <Card title={today}>
          <p className="text-xs text-wb-ink2">
            The Captain is not broken. Recovery is not repair.
            The nervous system is doing its job.{' '}
            <em>The conditions around it need to change, not the Captain.</em>
          </p>
        </Card>

        <Card title="Nervous System">
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
        </Card>

        <Card title="Energy">
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
            <p className="text-[11px] italic text-wb-ink2">
              Mood is now captured via Recovery Pulse (Telegram) — the platform&rsquo;s single manual
              health-data capture mechanism. This form no longer records mood separately.
            </p>
          </div>
        </Card>

        <Card title="Sleep">
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
        </Card>

        <Card title="Capacity">
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
        </Card>

        <Card title="Notes">
          <Textarea
            label="Notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            placeholder="Anything else the Medical Officer should know today."
            className="resize-none"
          />
        </Card>

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
          {saving ? 'Logging check-in…' : 'Log Check-In'}
        </Button>
      </div>
    </WorkbenchShell>
  );
}
